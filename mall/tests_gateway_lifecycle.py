import json,hmac,hashlib
from decimal import Decimal
from unittest.mock import patch
from cryptography.fernet import Fernet
from django.test import TestCase,override_settings
from django.contrib.auth import get_user_model
from .models import Shop,Product,PaymentMethod,GatewayConnection,PaymentAttempt,Receipt,Journal
from .services import checkout
from .gateway_crypto import encrypt_secret
from .gateway_services import reconcile
from .paystack import GatewayError
from .order_actions import cancel

@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class GatewayLifecycleTests(TestCase):
    def setUp(self):
        U=get_user_model();self.owner=U.objects.create_user('gateway-owner');self.buyer=U.objects.create_user('gateway-buyer',email='buyer@example.test');self.other=U.objects.create_user('gateway-other')
        self.shop=Shop.objects.create(owner=self.owner,name='Gateway shop',slug='gateway',active=True)
        self.product=Product.objects.create(shop=self.shop,name='Gateway product',description='Example',price=100,stock=10,category='Fashion')
        self.method=PaymentMethod.objects.create(shop=self.shop,kind='online',label='Pay online',instructions='Pay online')
        self.key=Fernet.generate_key().decode();self.secret='sk_test_testing_secret_example'
        self.settings_override=override_settings(GATEWAY_ENCRYPTION_KEY=self.key);self.settings_override.enable();self.addCleanup(self.settings_override.disable)
        self.gateway=GatewayConnection.objects.create(shop=self.shop,encrypted_secret=encrypt_secret(self.secret,self.key),active=True,test_mode=True)
        self.order=checkout(self.buyer,{str(self.product.pk):1},'Accra',{str(self.shop.pk):self.method.pk},'gateway-checkout')[0]
        self.attempt=PaymentAttempt.objects.create(order=self.order,gateway=self.gateway,reference='dq_testing',status='initialized')
    def data(self):return {'id':321,'status':'success','reference':self.attempt.reference,'amount':10000,'currency':'GHS'}
    def test_verified_gateway_payment_posts_once(self):
        with patch('mall.gateway_services.Paystack.verify',return_value=self.data()):reconcile(self.attempt.pk);reconcile(self.attempt.pk)
        self.assertEqual(Receipt.objects.count(),1);self.assertEqual(Journal.objects.filter(key='receipt:'+str(self.order.pk)).count(),1)
        self.order.refresh_from_db();self.assertEqual(self.order.status,'Paid')
    def test_wrong_amount_never_confirms(self):
        data=self.data();data['amount']=9999
        with patch('mall.gateway_services.Paystack.verify',return_value=data):
            with self.assertRaises(GatewayError):reconcile(self.attempt.pk)
        self.assertEqual(Receipt.objects.count(),0)
    def test_wrong_currency_never_confirms(self):
        data=self.data();data['currency']='NGN'
        with patch('mall.gateway_services.Paystack.verify',return_value=data):
            with self.assertRaises(GatewayError):reconcile(self.attempt.pk)
        self.assertEqual(Receipt.objects.count(),0)
    def test_payment_after_cancellation_goes_to_review(self):
        cancel(self.order.pk,self.buyer)
        with patch('mall.gateway_services.Paystack.verify',return_value=self.data()):reconcile(self.attempt.pk)
        self.attempt.refresh_from_db();self.assertEqual(self.attempt.status,'review');self.assertEqual(Receipt.objects.count(),0)
    def test_signed_webhook(self):
        payload=json.dumps({'event':'charge.success','data':{'reference':self.attempt.reference}}).encode();sig=hmac.new(self.secret.encode(),payload,hashlib.sha512).hexdigest()
        with patch('mall.gateway_services.Paystack.verify',return_value=self.data()):response=self.client.post('/webhooks/paystack/'+str(self.gateway.pk)+'/',data=payload,content_type='application/json',HTTP_X_PAYSTACK_SIGNATURE=sig)
        self.assertEqual(response.status_code,200);self.assertEqual(Receipt.objects.count(),1)
    def test_unsigned_webhook_rejected(self):
        response=self.client.post('/webhooks/paystack/'+str(self.gateway.pk)+'/',data=b'{}',content_type='application/json')
        self.assertEqual(response.status_code,401);self.assertEqual(Receipt.objects.count(),0)
    def test_wrong_seller_signature_rejected(self):
        payload=b'{"event":"charge.success"}';sig=hmac.new(b'wrong_seller_key',payload,hashlib.sha512).hexdigest()
        response=self.client.post('/webhooks/paystack/'+str(self.gateway.pk)+'/',data=payload,content_type='application/json',HTTP_X_PAYSTACK_SIGNATURE=sig)
        self.assertEqual(response.status_code,401);self.assertEqual(Receipt.objects.count(),0)
    def test_other_buyer_cannot_verify_callback(self):
        self.client.force_login(self.other);response=self.client.get('/payment/callback/?reference='+self.attempt.reference);self.assertEqual(response.status_code,404)
    def test_seller_form_never_exposes_saved_secret(self):
        self.client.force_login(self.owner);response=self.client.get('/seller/gateway/');self.assertNotContains(response,self.secret);self.assertNotContains(response,self.gateway.encrypted_secret)
