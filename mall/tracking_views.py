from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404,render,redirect
from django.views.decorators.vary import vary_on_headers
from django.views.decorators.http import require_POST
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from .models import Order,Shop,SellerSMSSettings,OutboundMessage
from .gateway_crypto import encrypt_secret
from .messaging import record_event

class TrackingUpdateForm(forms.Form):
    location=forms.CharField(max_length=160,label='Current parcel location',help_text='A location you have confirmed with your courier, e.g. Kumasi sorting hub.')
    note=forms.CharField(max_length=500,widget=forms.Textarea(attrs={'rows':3}),help_text='Customer-facing delivery update. Do not include private staff notes.')
    latitude=forms.DecimalField(required=False,max_digits=9,decimal_places=6,min_value=-90,max_value=90)
    longitude=forms.DecimalField(required=False,max_digits=9,decimal_places=6,min_value=-180,max_value=180)
    def clean(self):
        data=super().clean()
        if (data.get('latitude') is None)!=(data.get('longitude') is None):raise forms.ValidationError('Enter both coordinates, or leave both blank.')
        return data

def can_manage(request,order):
    from .views import access_shop
    return access_shop(request,order.shop.slug,'orders')

@login_required
@vary_on_headers('HX-Request')
def tracking(request,pk):
    order=get_object_or_404(Order.objects.select_related('shop','buyer'),pk=pk)
    managing=False
    if request.user.pk!=order.buyer_id:can_manage(request,order);managing=True
    events=list(order.tracking_events.all())
    stages=['Confirmed','Preparing','Dispatched','Delivered']
    progress=stages.index(order.status) if order.status in stages else (0 if order.status=='Paid' else -1)
    steps=[{'title':'Ready for collection' if title=='Dispatched' and order.fulfilment=='collection' else title,'done':i<=progress} for i,title in enumerate(stages)]
    location=next((event for event in events if event.location),None)
    return render(request,'tracking_content.html' if request.headers.get('HX-Request')=='true' else 'tracking.html',{'order':order,'events':events,'steps':steps,'latest_location':location,'managing':managing,'can_message':request.user.pk==order.shop.owner_id,'update_form':TrackingUpdateForm()})

@login_required
@require_POST
@transaction.atomic
def tracking_update(request,pk):
    order=get_object_or_404(Order.objects.select_for_update(),pk=pk);can_manage(request,order)
    form=TrackingUpdateForm(request.POST)
    if order.status in ['Cancelled','Refunded','Delivered']:messages.error(request,'This order is closed for delivery updates.')
    elif form.is_valid():
        record_event(order,'Delivery update',actor=request.user,**form.cleaned_data);messages.success(request,'Tracking update published and notifications queued.')
    else:messages.error(request,' '.join(str(error) for errors in form.errors.values() for error in errors))
    return redirect('tracking',pk=pk)

class SMSSettingsForm(forms.Form):
    api_key=forms.CharField(required=False,widget=forms.PasswordInput(render_value=False),max_length=500,help_text='Your Arkesel API key. Leave blank to keep the existing encrypted key.')
    sender_id=forms.RegexField(r'^[A-Za-z0-9 ]{1,11}$',max_length=11,help_text='Use the sender ID registered in your own Arkesel account (up to 11 characters).')
    active=forms.BooleanField(required=False,label='Enable transactional order SMS')

@login_required
def sms_settings(request):
    shop=get_object_or_404(Shop,owner=request.user);config=SellerSMSSettings.objects.filter(shop=shop).first()
    form=SMSSettingsForm(request.POST or None,initial={'sender_id':config.sender_id if config else '', 'active':config.active if config else False})
    if request.method=='POST' and form.is_valid():
        data=form.cleaned_data
        if not settings.GATEWAY_ENCRYPTION_KEY:form.add_error(None,'The platform administrator must configure GATEWAY_ENCRYPTION_KEY first.')
        elif not data['api_key'] and (not config or not config.encrypted_key):form.add_error('api_key','Enter your Arkesel API key.')
        else:
            config=config or SellerSMSSettings(shop=shop)
            if data['api_key']:config.encrypted_key=encrypt_secret(data['api_key'],settings.GATEWAY_ENCRYPTION_KEY)
            config.sender_id=data['sender_id'];config.active=data['active'];config.save()
            messages.success(request,'Arkesel SMS settings saved. Messages use your own account and credits.');return redirect('sms_settings')
    return render(request,'seller_form.html',{'title':'Your Arkesel SMS connection','subtitle':'Transactional order notifications are sent through your seller account. Configure your registered sender ID and account credits in Arkesel.','form':form})

@login_required
def message_log(request):
    shop=get_object_or_404(Shop,owner=request.user)
    return render(request,'message_log.html',{'shop':shop,'outbound':OutboundMessage.objects.filter(event__order__shop=shop).select_related('event__order').order_by('-created')[:100]})

@login_required
@require_POST
def retry_message(request,pk):
    message=get_object_or_404(OutboundMessage,pk=pk,event__order__shop__owner=request.user)
    reviewed=message.state in ['uncertain','sending'] and request.POST.get('verified_not_sent')=='on' and message.updated<timezone.now()-timedelta(minutes=5)
    if message.state in ['failed','skipped'] or reviewed:
        OutboundMessage.objects.filter(pk=pk,state=message.state).update(state='queued',error='')
        messages.success(request,'Message queued for another attempt.')
    else:messages.error(request,'Only a known failed or skipped message can be retried. Check provider records for uncertain or interrupted sends.')
    return redirect('message_log')
