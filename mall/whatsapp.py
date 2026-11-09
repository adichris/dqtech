"""Seller-owned WhatsApp Cloud API integration; never sends unsolicited text."""
import hashlib
import hmac
import json
import re
from datetime import datetime,timedelta,timezone as dt_timezone
from urllib.request import Request,urlopen
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .gateway_crypto import decrypt_secret
from .models import SellerWhatsAppSettings,WhatsAppContact,WhatsAppInbound,WhatsAppStatusReport,OutboundMessage


def template_payload(config,recipient,template,order,status):
    link=settings.PUBLIC_BASE_URL.rstrip('/')+f'/orders/{order.pk}/track/'
    return {'messaging_product':'whatsapp','recipient_type':'individual','to':recipient,'type':'template','template':{'name':template,'language':{'code':config.language},'components':[{'type':'body','parameters':[{'type':'text','text':str(order.pk)},{'type':'text','text':status},{'type':'text','text':link}]}]}}


def queue_whatsapp(event):
    from .messaging import normalize_phone
    order=event.order
    config=SellerWhatsAppSettings.objects.filter(shop=order.shop,active=True).first()
    if not config:return
    address=order.delivery_address or {}
    buyer=normalize_phone(address.get('phone',''),address.get('country','GH'))
    if buyer and address.get('whatsapp_opt_in') and not WhatsAppContact.objects.filter(shop=order.shop,phone=buyer,opted_out=True).exists():
        OutboundMessage.objects.get_or_create(event=event,channel='whatsapp',audience='buyer',defaults={'recipient':buyer,'subject':event.title,'body':f'Order #{order.pk}: {event.title}','payload':template_payload(config,buyer,config.order_template,order,event.title)})
    if event.title=='Order placed' and config.seller_opt_in and config.seller_phone and config.seller_template:
        if not WhatsAppContact.objects.filter(shop=order.shop,phone=config.seller_phone,opted_out=True).exists():
            OutboundMessage.objects.get_or_create(event=event,channel='whatsapp',audience='seller',defaults={'recipient':config.seller_phone,'subject':'New order','body':f'New order #{order.pk}','payload':template_payload(config,config.seller_phone,config.seller_template,order,'New order received')})


def service_window(shop,phone):
    return WhatsAppContact.objects.filter(shop=shop,phone=phone,opted_out=False,last_inbound__gt=timezone.now()-timedelta(hours=24)).exists()


def send_whatsapp(config,message):
    if WhatsAppContact.objects.filter(shop=config.shop,phone=message.recipient,opted_out=True).exists():raise ValueError('Recipient opted out.')
    payload=message.payload
    if payload.get('type')=='text' and not service_window(config.shop,message.recipient):raise ValueError('The WhatsApp customer service window has closed. Use an approved template.')
    if payload.get('type') not in ['template','text'] or payload.get('to')!=message.recipient:raise ValueError('Invalid WhatsApp message payload.')
    token=decrypt_secret(config.encrypted_token,settings.GATEWAY_ENCRYPTION_KEY)
    version=settings.WHATSAPP_GRAPH_VERSION
    if not re.fullmatch(r'v\d+\.\d+',version) or not re.fullmatch(r'\d{5,40}',config.phone_number_id):raise ValueError('Invalid WhatsApp API configuration.')
    request=Request(f'https://graph.facebook.com/{version}/{config.phone_number_id}/messages',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},method='POST')
    from .messaging import SendUncertain
    with urlopen(request,timeout=15) as response:
        try:result=json.loads(response.read(262144).decode())
        except (ValueError,UnicodeError):raise SendUncertain() from None
    if not isinstance(result,dict):raise SendUncertain()
    if result.get('error'):raise ValueError('WhatsApp rejected the message.')
    try:provider_id=result['messages'][0]['id']
    except (KeyError,IndexError,TypeError):raise SendUncertain() from None
    if not provider_id:raise SendUncertain()
    return str(provider_id)[:150]


@transaction.atomic
def apply_reports(shop,reference):
    ranks={'queued':0,'sending':0,'accepted':1,'sent':2,'failed':3,'delivered':4,'read':5}
    reports=WhatsAppStatusReport.objects.filter(shop=shop,provider_reference=reference)
    for report in reports:
        for message in OutboundMessage.objects.select_for_update().filter(channel='whatsapp',event__order__shop=shop,provider_reference=reference,recipient=report.recipient).exclude(provider_reference=''):
            if report.status in ranks and ranks[report.status]>ranks.get(message.state,-1):
                message.state=report.status
                message.error='WhatsApp reported delivery failure. Review your business account report.' if report.status=='failed' else ''
                message.save()


@transaction.atomic
def process_webhook(config,body):
    from .messaging import normalize_phone
    data=json.loads(body)
    for entry in data.get('entry',[]):
        for change in entry.get('changes',[]):
            value=change.get('value',{})
            if str(value.get('metadata',{}).get('phone_number_id',''))!=config.phone_number_id:continue
            for incoming in value.get('messages',[]):
                phone=normalize_phone('+'+str(incoming.get('from','')).lstrip('+'),'')
                if not phone or not incoming.get('id'):continue
                try:created=datetime.fromtimestamp(int(incoming['timestamp']),tz=dt_timezone.utc)
                except (ValueError,KeyError,OverflowError,OSError):continue
                if created>timezone.now()+timedelta(minutes=5):continue
                text=str(incoming.get('text',{}).get('body',''))[:4000]
                row,new=WhatsAppInbound.objects.get_or_create(provider_id=incoming['id'],defaults={'shop':config.shop,'phone':phone,'text':text,'created':created})
                if not new:continue
                contact,_=WhatsAppContact.objects.select_for_update().get_or_create(shop=config.shop,phone=phone)
                if contact.last_inbound and created<contact.last_inbound:continue
                contact.last_inbound=created
                if text.strip().casefold() in ['stop','unsubscribe']:contact.opted_out=True
                elif text.strip().casefold() in ['start','subscribe']:contact.opted_out=False
                contact.save()
            for status in value.get('statuses',[]):
                # Bind provider ID, tenant and recipient; never accept cross-tenant reports.
                phone=normalize_phone('+'+str(status.get('recipient_id','')).lstrip('+'),'')
                reference=status.get('id','')
                if phone and isinstance(reference,str) and 0<len(reference)<=150 and status.get('status') in ['sent','delivered','read','failed']:
                    WhatsAppStatusReport.objects.get_or_create(shop=config.shop,provider_reference=reference,recipient=phone,status=status['status'])
                    apply_reports(config.shop,reference)
