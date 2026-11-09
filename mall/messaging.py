"""Transactional order outbox. Sending is performed by dispatch_notifications.

Never log provider responses/keys. Ambiguous network failures require review,
because automatic retries could send the same SMS/email twice.
"""
import json
import re
import smtplib
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from django.conf import settings
from oscar.core.loading import get_model,get_class
from django.template.loader import render_to_string
from django.db import transaction
from django.utils import timezone
from .gateway_crypto import decrypt_secret
from .models import TrackingEvent,OutboundMessage,SellerSMSSettings,Notification,Receipt

class SendUncertain(Exception):pass


def normalize_phone(value,country):
    raw=re.sub(r'[\s()\-]','',value or '')
    if raw.startswith('00'):raw='+'+raw[2:]
    if country=='GH' and re.fullmatch(r'0\d{9}',raw):raw='+233'+raw[1:]
    elif country=='NG' and re.fullmatch(r'0\d{10}',raw):raw='+234'+raw[1:]
    if not re.fullmatch(r'\+[1-9]\d{6,14}',raw):return ''
    return raw

def payment_summary(order):
    if order.status=='Refunded':return 'Refund recorded by your seller'
    if order.status=='Cancelled':return 'Order cancelled - no payment due'
    receipt=Receipt.objects.filter(order=order).first()
    if receipt:return 'Cash collected' if order.cash_on_delivery else 'Payment confirmed'
    return 'Cash due on arrival or collection' if order.cash_on_delivery else 'See order payment instructions'


@transaction.atomic
def record_event(order,title,actor=None,note='',location='',latitude=None,longitude=None,notify=True):
    communication=None
    if order.oscar_order_id:
        from oscar.core.loading import get_model
        from django.utils.text import slugify
        kind,_=get_model('communication','CommunicationEventType').objects.get_or_create(code='MARKETPLACE_'+slugify(title).replace('-','_').upper(),defaults={'name':title})
        communication=get_model('order','CommunicationEvent').objects.create(order=order.oscar_order,event_type=kind)
    event=TrackingEvent.objects.create(communication_event=communication,order=order,actor=actor,title=title,status=order.status,note=note,location=location,latitude=latitude,longitude=longitude)
    if notify:
        Notification.objects.create(recipient=order.buyer,subject=f'Order #{order.pk}: {title}',body=f'/orders/{order.pk}/track/')
        queue_messages(event)
    return event


def queue_messages(event):
    order=event.order
    link=settings.PUBLIC_BASE_URL.rstrip('/')+f'/orders/{order.pk}/track/'
    payment=payment_summary(order)
    destination=order.delivery_address or {}
    area=', '.join(filter(None,[destination.get('city'),destination.get('region')]))
    location=f'\nSeller-reported location: {event.location}' if event.location else ''
    detail=f'\n{event.note}' if event.note else ''
    subject=f'Order #{order.pk}: {event.title}'
    html=render_to_string('emails/order_update.html',{'system_name':settings.SYSTEM_NAME,'order':order,'event':event,'payment':payment,'tracking_url':link})
    body=f'{settings.SYSTEM_NAME}\n{order.shop.name} · Order #{order.pk}\n{event.title}\nStatus: {order.status}\n{order.currency} {order.total} · {payment}\nDestination: {area or "See order address"}{location}{detail}\nTrack securely: {link}\nLocation updates are reported by your seller; sign in to view full details.'
    if order.buyer.email:
        OutboundMessage.objects.get_or_create(event=event,channel='email',audience='buyer',defaults={'recipient':order.buyer.email,'subject':subject[:180],'body':body,'payload':{'html':html}})
    phone=normalize_phone(destination.get('phone',''),destination.get('country','GH'))
    if phone and SellerSMSSettings.objects.filter(shop=order.shop,active=True).exists():
        # Transactional messages only. Full home addresses and GPS are omitted.
        sms=f'{order.shop.name}: Order #{order.pk} - {event.title}. {order.currency} {order.total}. {payment}. Track: {link}'
        OutboundMessage.objects.get_or_create(event=event,channel='sms',audience='buyer',defaults={'recipient':phone,'subject':subject[:180],'body':sms})

    if event.title=='Order placed' and order.shop.owner.email:
        OutboundMessage.objects.get_or_create(event=event,channel='email',audience='seller',defaults={'recipient':order.shop.owner.email,'subject':subject[:180],'body':body,'payload':{'html':html}})
    from .whatsapp import queue_whatsapp
    queue_whatsapp(event)


def send_arkesel(config,recipient,body):
    secret=decrypt_secret(config.encrypted_key,settings.GATEWAY_ENCRYPTION_KEY)
    request=Request('https://sms.arkesel.com/api/v2/sms/send',data=json.dumps({'sender':config.sender_id,'message':body,'recipients':[recipient]}).encode(),headers={'api-key':secret,'Content-Type':'application/json','Accept':'application/json'},method='POST')
    with urlopen(request,timeout=15) as response:
        try:data=json.loads(response.read(262144).decode())
        except (ValueError,UnicodeError):raise SendUncertain() from None
    if not isinstance(data,dict) or not data.get('status'):raise SendUncertain()
    if data.get('status')!='success':raise ValueError('Arkesel rejected the request. Check account credits, sender ID and API access.')
    payload=data.get('data',{})
    reference=payload.get('id','') if isinstance(payload,dict) else ''
    return str(reference)[:150]


def dispatch_one(message_id):
    with transaction.atomic():
        message=OutboundMessage.objects.select_for_update().select_related('event__order__shop').get(pk=message_id)
        if message.state!='queued':return message.state
        message.state='sending';message.attempts+=1;message.error='';message.save()
    # A process crash while sending leaves 'sending' for explicit operator review.
    state='failed';error='';reference=''
    try:
        if message.channel=='email':
            email=get_class('communication.utils','Dispatcher')().send_email_messages(message.recipient,{'subject':message.subject,'body':message.body,'html':message.payload.get('html'),'sms':None},from_email=settings.DEFAULT_FROM_EMAIL)
            if email is None:raise ValueError('Email backend did not accept the message.')
            recipient=message.event.order.buyer if message.audience=='buyer' else message.event.order.shop.owner
            get_model('communication','Email').objects.create(user=recipient,email=message.recipient,subject=message.subject,body_text=message.body,body_html=message.payload.get('html') or '')
            state='preview' if settings.EMAIL_BACKEND in ['django.core.mail.backends.console.EmailBackend','django.core.mail.backends.locmem.EmailBackend','django.core.mail.backends.filebased.EmailBackend','django.core.mail.backends.dummy.EmailBackend'] else 'sent'
        elif message.channel=='whatsapp':
            from .models import SellerWhatsAppSettings,WhatsAppContact
            from .whatsapp import send_whatsapp,service_window
            config=SellerWhatsAppSettings.objects.filter(shop=message.event.order.shop,active=True).first()
            if not config:state='skipped';error='Seller WhatsApp is disabled.'
            elif WhatsAppContact.objects.filter(shop=config.shop,phone=message.recipient,opted_out=True).exists():state='skipped';error='Recipient opted out.'
            elif message.payload.get('type')=='text' and not service_window(config.shop,message.recipient):state='skipped';error='Customer service window has closed.'
            else:reference=send_whatsapp(config,message);state='accepted'
        else:
            config=SellerSMSSettings.objects.filter(shop=message.event.order.shop,active=True).first()
            if not config:state='skipped';error='Seller SMS is disabled.'
            else:reference=send_arkesel(config,message.recipient,message.body);state='accepted'
    except HTTPError as exc:
        error=f'Messaging provider returned HTTP {exc.code}. Review seller credentials, credits and sender approval.'
        state='uncertain' if exc.code>=500 else 'failed'
    except (SendUncertain,TimeoutError,URLError,ConnectionError,smtplib.SMTPServerDisconnected):
        state='uncertain';error='Connection interrupted. Check provider records before retrying to avoid duplicates.'
    except smtplib.SMTPException:
        error='SMTP rejected the message. Check platform email configuration.'
    except Exception:
        error='Message not sent. Check provider settings, credentials and encryption key.'
    OutboundMessage.objects.filter(pk=message.pk).update(state=state,error=error,provider_reference=reference,updated=timezone.now())
    if message.channel=='whatsapp' and reference:
        from .whatsapp import apply_reports
        apply_reports(message.event.order.shop,reference)
    return state
