import hashlib,hmac,json
from datetime import timedelta
from unittest.mock import patch,MagicMock
from cryptography.fernet import Fernet
from django.test import TestCase,override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core import mail
from django.core.management import call_command
from .models import *
from .services import checkout
from .messaging import record_event,queue_messages,dispatch_one,normalize_phone,send_arkesel
from .gateway_crypto import encrypt_secret
from .order_actions import advance
from .whatsapp import process_webhook,service_window,send_whatsapp


class NotificationTests(TestCase):
    def setUp(self):
        self.key=Fernet.generate_key().decode()
        self.override=override_settings(GATEWAY_ENCRYPTION_KEY=self.key,EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',PUBLIC_BASE_URL='https://mall.example',WHATSAPP_GRAPH_VERSION='v27.0')
        self.override.enable();self.addCleanup(self.override.disable)
        users=get_user_model();self.owner=users.objects.create_user('merchant',email='seller@example.com');self.buyer=users.objects.create_user('customer',email='customer@example.com');self.stranger=users.objects.create_user('stranger')
        self.shop=Shop.objects.create(owner=self.owner,name='Merchant',slug='merchant',active=True)
        self.product=Product.objects.create(shop=self.shop,name='Parcel',description='Test',category='Fashion',price=100,stock=10)
        self.address={'recipient':'Customer','phone':'0241234567','country':'GH','region':'Greater Accra','city':'Accra','street':'Market Road','whatsapp_opt_in':True}
        self.sms=SellerSMSSettings.objects.create(shop=self.shop,encrypted_key=encrypt_secret('ARKESEL-PRIVATE',self.key),sender_id='MyStore',active=True)
        self.wa=SellerWhatsAppSettings.objects.create(shop=self.shop,phone_number_id='123456789',encrypted_token=encrypt_secret('WHATSAPP-PRIVATE',self.key),encrypted_app_secret=encrypt_secret('APP-SECRET',self.key),verify_token_hash=hashlib.sha256(b'my-long-verification-token').hexdigest(),order_template='order_update',seller_template='new_order',seller_phone='+233201111111',seller_opt_in=True,language='en',active=True)
    def order(self):
        return checkout(self.buyer,{str(self.product.pk):1},'Customer address',{},'key',delivery_address=self.address.copy())[0]
    def webhook_body(self,**value):
        return json.dumps({'entry':[{'changes':[{'value':{'metadata':{'phone_number_id':self.wa.phone_number_id},**value}}]}]}).encode()

    def test_order_queues_buyer_and_seller_channels_once(self):
        order=self.order();event=order.tracking_events.get()
        self.assertEqual(OutboundMessage.objects.count(),5)
        queue_messages(event);self.assertEqual(OutboundMessage.objects.count(),5)
        self.assertEqual(OutboundMessage.objects.get(channel='sms').recipient,'+233241234567')
        buyer=OutboundMessage.objects.get(channel='whatsapp',audience='buyer')
        self.assertEqual(buyer.payload['type'],'template');self.assertEqual(len(buyer.payload['template']['components'][0]['parameters']),3)
        self.assertEqual(buyer.payload['template']['name'],'order_update')
        self.assertTrue(order.delivery_address['whatsapp_opt_in_at'])

    def test_opt_in_required_and_stop_honoured(self):
        self.address['whatsapp_opt_in']=False;order=self.order()
        self.assertFalse(OutboundMessage.objects.filter(channel='whatsapp',audience='buyer').exists())
        WhatsAppContact.objects.create(shop=self.shop,phone='+233241234567',opted_out=True)
        order.delivery_metadata['whatsapp_opt_in']=True;order.save(update_fields=['delivery_metadata'])
        record_event(order,'Preparing');self.assertFalse(OutboundMessage.objects.filter(channel='whatsapp',audience='buyer').exists())

    def test_email_backend_and_idempotent_dispatch(self):
        self.order();message=OutboundMessage.objects.filter(channel='email',audience='buyer').get()
        self.assertEqual(dispatch_one(message.pk),'preview');dispatch_one(message.pk)
        self.assertEqual(len(mail.outbox),1);self.assertEqual(mail.outbox[0].to,['customer@example.com'])
        self.assertIn('https://mall.example/orders/',mail.outbox[0].body)

    def test_arkesel_uses_seller_key_and_v2_payload(self):
        result=MagicMock();result.__enter__.return_value.read.return_value=json.dumps({'status':'success','data':{'id':'ARK-1'}}).encode()
        with patch('mall.messaging.urlopen',return_value=result) as network:
            self.assertEqual(send_arkesel(self.sms,'+233241234567','Parcel ready'),'ARK-1')
        request=network.call_args.args[0]
        self.assertEqual(request.full_url,'https://sms.arkesel.com/api/v2/sms/send')
        self.assertEqual(request.get_header('Api-key'),'ARKESEL-PRIVATE');self.assertEqual(json.loads(request.data)['recipients'],['+233241234567'])

    def test_unknown_send_is_not_retried_automatically(self):
        self.order();message=OutboundMessage.objects.get(channel='sms')
        with patch('mall.messaging.send_arkesel',side_effect=TimeoutError):self.assertEqual(dispatch_one(message.pk),'uncertain')
        with patch('mall.messaging.send_arkesel') as network:dispatch_one(message.pk);network.assert_not_called()
        self.client.force_login(self.owner);self.client.post('/seller/messages/'+str(message.pk)+'/retry/')
        message.refresh_from_db();self.assertEqual(message.state,'uncertain')

    def test_disabled_seller_channel_skips_queued_message(self):
        self.order();message=OutboundMessage.objects.get(channel='sms')
        self.sms.active=False;self.sms.save()
        with patch('mall.messaging.send_arkesel') as network:self.assertEqual(dispatch_one(message.pk),'skipped');network.assert_not_called()

    def test_whatsapp_payload_and_signed_statuses_are_tenant_bound(self):
        self.order();message=OutboundMessage.objects.get(channel='whatsapp',audience='buyer')
        response=MagicMock();response.__enter__.return_value.read.return_value=b'{"messages":[{"id":"wamid.1"}]}'
        with patch('mall.whatsapp.urlopen',return_value=response) as network:self.assertEqual(dispatch_one(message.pk),'accepted')
        request=network.call_args.args[0];self.assertIn('/v27.0/123456789/messages',request.full_url);self.assertEqual(request.get_header('Authorization'),'Bearer WHATSAPP-PRIVATE')
        url='/webhooks/whatsapp/'+str(self.shop.pk)+'/'
        body=self.webhook_body(statuses=[{'id':'wamid.1','recipient_id':'233241234567','status':'delivered'}])
        self.assertEqual(self.client.post(url,body,content_type='application/json').status_code,403)
        signature='sha256='+hmac.new(b'APP-SECRET',body,hashlib.sha256).hexdigest()
        self.assertEqual(self.client.post(url,body,content_type='application/json',HTTP_X_HUB_SIGNATURE_256=signature).status_code,200)
        message.refresh_from_db();self.assertEqual(message.state,'delivered')
        process_webhook(self.wa,self.webhook_body(statuses=[{'id':'wamid.1','recipient_id':'233241234567','status':'sent'}]))
        message.refresh_from_db();self.assertEqual(message.state,'delivered')

    def test_early_delivery_report_is_applied_after_send(self):
        self.order();message=OutboundMessage.objects.get(channel='whatsapp',audience='buyer')
        process_webhook(self.wa,self.webhook_body(statuses=[{'id':'wamid.early','recipient_id':'233241234567','status':'read'}]))
        with patch('mall.whatsapp.send_whatsapp',return_value='wamid.early'):dispatch_one(message.pk)
        message.refresh_from_db();self.assertEqual(message.state,'read')

    def test_verified_inbound_window_replay_and_stop(self):
        self.order();timestamp=str(int(timezone.now().timestamp()))
        incoming={'id':'in-1','from':'233241234567','timestamp':timestamp,'text':{'body':'Where is my parcel?'}}
        body=self.webhook_body(messages=[incoming]);process_webhook(self.wa,body);process_webhook(self.wa,body)
        self.assertEqual(WhatsAppInbound.objects.count(),1);self.assertTrue(service_window(self.shop,'+233241234567'))
        self.client.force_login(self.owner)
        order=Order.objects.get();self.client.post('/seller/orders/'+str(order.pk)+'/whatsapp/',{'message':'It is on the way.'})
        self.assertTrue(OutboundMessage.objects.filter(payload__type='text').exists())
        process_webhook(self.wa,self.webhook_body(messages=[{**incoming,'id':'in-2','text':{'body':'STOP'}}]))
        self.assertFalse(service_window(self.shop,'+233241234567'))
        self.assertTrue(WhatsAppContact.objects.get().opted_out)

    def test_expired_window_prevents_freeform_send(self):
        order=self.order();self.client.force_login(self.owner)
        WhatsAppContact.objects.create(shop=self.shop,phone='+233241234567',last_inbound=timezone.now()-timedelta(hours=25))
        self.client.post('/seller/orders/'+str(order.pk)+'/whatsapp/',{'message':'Cannot send this.'})
        self.assertFalse(OutboundMessage.objects.filter(payload__type='text').exists())

    def test_webhook_verification_and_wrong_business_number(self):
        url='/webhooks/whatsapp/'+str(self.shop.pk)+'/'
        response=self.client.get(url,{'hub.mode':'subscribe','hub.verify_token':'my-long-verification-token','hub.challenge':'abc'})
        self.assertEqual(response.content,b'abc');self.assertEqual(self.client.get(url,{'hub.verify_token':'wrong'}).status_code,403)
        body=json.dumps({'entry':[{'changes':[{'value':{'metadata':{'phone_number_id':'wrong'},'messages':[{'id':'bad','from':'233241234567','timestamp':str(int(timezone.now().timestamp()))}]}}]}]}).encode()
        process_webhook(self.wa,body);self.assertFalse(WhatsAppInbound.objects.exists())

    def test_private_tracking_and_location_validation(self):
        order=self.order();url='/orders/'+str(order.pk)+'/track/'
        self.assertEqual(self.client.get(url).status_code,302)
        self.client.force_login(self.stranger);self.assertEqual(self.client.get(url).status_code,403)
        self.client.force_login(self.buyer);self.assertContains(self.client.get(url),'Follow your finds')
        self.assertEqual(self.client.post('/seller/orders/'+str(order.pk)+'/tracking/',{'location':'Forged','note':'Test'}).status_code,403)
        self.client.force_login(self.owner)
        update='/seller/orders/'+str(order.pk)+'/tracking/'
        self.client.post(update,{'location':'Kumasi hub','note':'Parcel arrived','latitude':'999','longitude':'-1'})
        self.assertEqual(order.tracking_events.count(),1)
        self.client.post(update,{'location':'Kumasi hub','note':'Parcel arrived','latitude':'6.6885','longitude':'-1.6244'})
        self.assertEqual(order.tracking_events.count(),2);self.assertContains(self.client.get(url),'Kumasi hub')
        self.assertContains(self.client.get(url),'openstreetmap.org')

    def test_credentials_not_rendered_and_owner_only_settings(self):
        self.client.force_login(self.owner)
        for url in ['/seller/sms/','/seller/whatsapp/','/seller/messages/']:
            response=self.client.get(url);self.assertEqual(response.status_code,200)
            for secret in ['ARKESEL-PRIVATE','WHATSAPP-PRIVATE','APP-SECRET',self.sms.encrypted_key,self.wa.encrypted_token]:self.assertNotContains(response,secret)
        self.client.force_login(self.stranger)
        for url in ['/seller/sms/','/seller/whatsapp/','/seller/messages/']:self.assertEqual(self.client.get(url).status_code,404)

    def test_rollback_does_not_leave_notification_queue(self):
        with self.assertRaises(ValueError):checkout(self.buyer,{str(self.product.pk):100},'Address',{},'bad',delivery_address=self.address)
        self.assertFalse(OutboundMessage.objects.exists());self.assertFalse(TrackingEvent.objects.exists())

    def test_phone_normalization(self):
        self.assertEqual(normalize_phone('024 123 4567','GH'),'+233241234567')
        self.assertEqual(normalize_phone('00233241234567','GH'),'+233241234567')
        self.assertEqual(normalize_phone('not-a-number','GH'),'')

    def test_malformed_success_response_is_uncertain(self):
        self.order()
        response=MagicMock();response.__enter__.return_value.read.return_value=b'bad gateway response'
        with patch('mall.messaging.urlopen',return_value=response):
            self.assertEqual(dispatch_one(OutboundMessage.objects.get(channel='sms').pk),'uncertain')
        with patch('mall.whatsapp.urlopen',return_value=response):
            self.assertEqual(dispatch_one(OutboundMessage.objects.get(channel='whatsapp',audience='buyer').pk),'uncertain')

    def test_credentials_can_be_updated_without_exposing_or_erasing_keys(self):
        self.client.force_login(self.owner)
        response=self.client.post('/seller/whatsapp/',{'phone_number_id':'123456789','token':'','app_secret':'','verify_token':'','order_template':'order_update_v2','seller_template':'new_order','language':'en','active':'on'})
        self.assertEqual(response.status_code,302);old=self.wa.encrypted_token;self.wa.refresh_from_db()
        self.assertEqual(self.wa.encrypted_token,old);self.assertEqual(self.wa.order_template,'order_update_v2')
        response=self.client.post('/seller/sms/',{'api_key':'NEW-PRIVATE-KEY','sender_id':'Merchant','active':'on'})
        self.assertEqual(response.status_code,302);self.sms.refresh_from_db();self.assertNotEqual(self.sms.encrypted_key,'NEW-PRIVATE-KEY')
        from .gateway_crypto import decrypt_secret
        self.assertEqual(decrypt_secret(self.sms.encrypted_key,self.key),'NEW-PRIVATE-KEY')

    def test_failed_delivery_cannot_regress_to_sent(self):
        self.order();message=OutboundMessage.objects.get(channel='whatsapp',audience='buyer');message.provider_reference='wamid.failed';message.state='accepted';message.save()
        for state in ['failed','sent']:
            process_webhook(self.wa,self.webhook_body(statuses=[{'id':'wamid.failed','recipient_id':'233241234567','status':state}]))
        message.refresh_from_db();self.assertEqual(message.state,'failed')

    def test_tracking_fragment_has_no_public_access_or_full_document(self):
        order=self.order();self.client.force_login(self.buyer)
        response=self.client.get('/orders/'+str(order.pk)+'/track/',HTTP_HX_REQUEST='true')
        self.assertContains(response,'order-tracking');self.assertNotContains(response,'<!doctype html>')
        self.assertIn('HX-Request',response.headers['Vary'])
