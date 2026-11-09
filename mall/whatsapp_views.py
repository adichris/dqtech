import hashlib
import hmac
import json
import re
from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404,render,redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods,require_POST
from .models import Shop,Order,SellerWhatsAppSettings,OutboundMessage,WhatsAppInbound
from .gateway_crypto import encrypt_secret,decrypt_secret
from .messaging import normalize_phone
from .whatsapp import process_webhook,service_window

class WhatsAppSettingsForm(forms.Form):
    phone_number_id=forms.RegexField(r'^\d{5,40}$',label='WhatsApp Business phone number ID',max_length=40,help_text='Meta Cloud API phone number ID, not your mobile telephone number.')
    token=forms.CharField(required=False,max_length=2000,widget=forms.PasswordInput(render_value=False),label='Access token',help_text='System-user token with WhatsApp messaging permission. Blank keeps the current encrypted token.')
    app_secret=forms.CharField(required=False,max_length=500,widget=forms.PasswordInput(render_value=False),help_text='Meta app secret used to verify inbound webhook signatures. Blank keeps the current value.')
    verify_token=forms.CharField(required=False,max_length=200,min_length=20,widget=forms.PasswordInput(render_value=False),help_text='Choose a random verification token of at least 20 characters; enter the same value in Meta webhook setup. Blank keeps the current value.')
    order_template=forms.RegexField(r'^[a-z0-9_]{1,100}$',max_length=100,label='Approved customer order-update template')
    seller_template=forms.RegexField(r'^[a-z0-9_]{1,100}$',max_length=100,required=False,label='Approved seller new-order template')
    language=forms.RegexField(r'^[a-z]{2,3}(?:_[A-Z]{2})?$',max_length=20,initial='en',help_text='Exact language code of your approved templates, e.g. en or en_US.')
    seller_phone=forms.CharField(required=False,max_length=25,label='Your WhatsApp alert recipient',help_text='International format, e.g. +233241234567. Use a recipient number separate from your sending Business number.')
    seller_opt_in=forms.BooleanField(required=False,label='I want new-order WhatsApp alerts at this number')
    active=forms.BooleanField(required=False,label='Enable WhatsApp order notifications')
    def clean(self):
        data=super().clean()
        if data.get('seller_phone'):
            phone=normalize_phone(data['seller_phone'],'')
            if not phone:self.add_error('seller_phone','Use a valid international phone number.')
            else:data['seller_phone']=phone
        if data.get('seller_opt_in') and (not data.get('seller_phone') or not data.get('seller_template')):raise forms.ValidationError('Seller alerts need your recipient number and approved seller template.')
        return data

@login_required
def whatsapp_settings(request):
    shop=get_object_or_404(Shop,owner=request.user);config=SellerWhatsAppSettings.objects.filter(shop=shop).first()
    fields=['phone_number_id','order_template','seller_template','language','seller_phone','seller_opt_in','active']
    initial={field:getattr(config,field) for field in fields} if config else {'language':'en'}
    form=WhatsAppSettingsForm(request.POST or None,initial=initial)
    if request.method=='POST' and form.is_valid():
        data=form.cleaned_data
        if not settings.GATEWAY_ENCRYPTION_KEY:form.add_error(None,'The platform administrator must configure the encryption key first.')
        if SellerWhatsAppSettings.objects.filter(phone_number_id=data['phone_number_id']).exclude(shop=shop).exists():form.add_error('phone_number_id','This business number is already connected to another store.')
        if not config:
            for field in ['token','app_secret','verify_token']:
                if not data.get(field):form.add_error(field,'Required when connecting your WhatsApp Business account.')
        if not form.errors:
            config=config or SellerWhatsAppSettings(shop=shop)
            for field in fields:setattr(config,field,data[field])
            if data['token']:config.encrypted_token=encrypt_secret(data['token'],settings.GATEWAY_ENCRYPTION_KEY)
            if data['app_secret']:config.encrypted_app_secret=encrypt_secret(data['app_secret'],settings.GATEWAY_ENCRYPTION_KEY)
            if data['verify_token']:config.verify_token_hash=hashlib.sha256(data['verify_token'].encode()).hexdigest()
            config.save();messages.success(request,'WhatsApp Business settings saved. Complete webhook setup and template approval in Meta.');return redirect('whatsapp_settings')
    return render(request,'whatsapp_settings.html',{'form':form,'shop':shop,'webhook_url':settings.PUBLIC_BASE_URL.rstrip('/')+f'/webhooks/whatsapp/{shop.pk}/','inbound':WhatsAppInbound.objects.filter(shop=shop).order_by('-created')[:20]})

@csrf_exempt
@require_http_methods(['GET','POST'])
def webhook(request,shop_id):
    config=get_object_or_404(SellerWhatsAppSettings,shop_id=shop_id)
    if request.method=='GET':
        token=request.GET.get('hub.verify_token','')
        if request.GET.get('hub.mode')=='subscribe' and token and hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(),config.verify_token_hash):return HttpResponse(request.GET.get('hub.challenge',''),content_type='text/plain')
        return HttpResponse(status=403)
    if len(request.body)>1048576:return HttpResponse(status=413)
    try:secret=decrypt_secret(config.encrypted_app_secret,settings.GATEWAY_ENCRYPTION_KEY)
    except Exception:return HttpResponse(status=503)
    signature=request.headers.get('X-Hub-Signature-256','')
    expected='sha256='+hmac.new(secret.encode(),request.body,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature,expected):return HttpResponse(status=403)
    try:process_webhook(config,request.body)
    except (ValueError,TypeError,AttributeError):return HttpResponse(status=400)
    return HttpResponse(status=200)

@login_required
@require_POST
def message_customer(request,pk):
    from .messaging import record_event
    order=get_object_or_404(Order,pk=pk,shop__owner=request.user)
    config=get_object_or_404(SellerWhatsAppSettings,shop=order.shop,active=True)
    phone=normalize_phone(order.delivery_address.get('phone',''),order.delivery_address.get('country','GH'))
    text=request.POST.get('message','').strip()
    if not phone or not service_window(order.shop,phone):messages.error(request,'Free-form replies need a customer message within the last 24 hours. Automatic order updates use approved templates.')
    elif not 1<=len(text)<=1000:messages.error(request,'Enter a message of up to 1,000 characters.')
    else:
        from django.db import transaction
        from .models import TrackingEvent
        with transaction.atomic():
            event=record_event(order,'Seller message',actor=request.user,note=text,notify=False)
            OutboundMessage.objects.create(event=event,channel='whatsapp',recipient=phone,subject='Seller message',body=text,payload={'messaging_product':'whatsapp','recipient_type':'individual','to':phone,'type':'text','text':{'body':text}})
        messages.success(request,'WhatsApp reply queued.')
    return redirect('tracking',pk=pk)
