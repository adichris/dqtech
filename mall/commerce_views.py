from django.utils import timezone
import json
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError,transaction
from django.http import HttpResponse,HttpResponseBadRequest
from django.shortcuts import get_object_or_404,render,redirect
from django.views.decorators.http import require_POST,require_GET
from django.views.decorators.csrf import csrf_exempt
from .models import *
from .forms import GatewayForm,SettingsForm,VerificationForm
from .gateway_crypto import encrypt_secret,valid_signature
from .gateway_services import begin,reconcile,secret_for,platform_secret,platform_available,save_mall_pay
from .eligibility import own_gateway_eligibility,may_save_own_gateway
from .paystack import GatewayError
from .order_actions import cancel,request_return,decide_return
@login_required
def gateway(request):
    shop=get_object_or_404(Shop,owner=request.user);form=GatewayForm(request.POST or None)
    connection=GatewayConnection.objects.filter(shop=shop).first()
    eligibility=own_gateway_eligibility(shop);allowed=may_save_own_gateway(shop,connection)
    if request.method=='POST' and not allowed:
        messages.error(request,'Your store does not meet the requirements for a seller-owned Paystack account yet. Use Mall Pay meanwhile.');return redirect('gateway')
    if request.method=='POST' and form.is_valid():
        key=settings.GATEWAY_ENCRYPTION_KEY
        if not key:form.add_error(None,'The platform administrator must configure GATEWAY_ENCRYPTION_KEY first.')
        elif (shop.country,shop.currency) not in [('GH','GHS'),('NG','NGN')]:form.add_error(None,'Paystack is currently supported here for Ghana/GHS and Nigeria/NGN stores.')
        else:
            with transaction.atomic():
                connection,_=GatewayConnection.objects.update_or_create(shop=shop,defaults={'mode':GatewayConnection.OWN,'encrypted_secret':encrypt_secret(form.cleaned_data['secret'],key),'test_mode':form.cleaned_data['test_mode'],'active':form.cleaned_data['active']})
                PaymentMethod.objects.update_or_create(shop=shop,kind='online',defaults={'label':'Paystack '+('test' if connection.test_mode else 'online'),'instructions':'Pay securely through your seller’s Paystack account.','active':connection.active})
                AuditEvent.objects.create(shop=shop,actor=request.user,action='Gateway configuration changed',detail='paystack test='+str(connection.test_mode))
            messages.success(request,'Your gateway connection was saved. Run a test transaction before enabling live payments.');return redirect('gateway')
    return render(request,'gateway.html',{'form':form,'shop':shop,'connection':connection,'public_base':settings.PUBLIC_BASE_URL,'eligibility':eligibility,'allowed':allowed,'grandfathered':allowed and not eligibility['eligible'],'mall_pay_available':platform_available(shop)})
@login_required
@require_POST
def pay(request,pk):
    get_object_or_404(Order,pk=pk,buyer=request.user)
    try:return redirect(begin(pk,request.user))
    except GatewayError as e:messages.error(request,str(e));return redirect('orders')
@login_required
@require_GET
def callback(request):
    attempt=get_object_or_404(PaymentAttempt,reference=request.GET.get('reference',''),order__buyer=request.user)
    try:
        order=reconcile(attempt.pk)
        messages.success(request,'Payment verified.' if order.status=='Paid' else 'Payment was received for review. Please contact your seller.')
    except GatewayError as e:messages.warning(request,str(e))
    return redirect('orders')
@csrf_exempt
@require_POST
def webhook(request,gateway_id):
    if len(request.body)>1000000:return HttpResponseBadRequest('Payload too large')
    connection=get_object_or_404(GatewayConnection,pk=gateway_id)
    try:secret=secret_for(connection)
    except GatewayError:return HttpResponse('Gateway unavailable',status=503)
    if not valid_signature(request.body,request.headers.get('X-Paystack-Signature',''),secret):return HttpResponse('Invalid signature',status=401)
    try:payload=json.loads(request.body)
    except (ValueError,UnicodeDecodeError):return HttpResponseBadRequest('Invalid JSON')
    if not isinstance(payload,dict):return HttpResponseBadRequest('Invalid event')
    if payload.get('event')!='charge.success':return HttpResponse(status=200)
    data=payload.get('data',{})
    if not isinstance(data,dict):return HttpResponseBadRequest('Invalid data')
    attempt=PaymentAttempt.objects.filter(gateway=connection,platform=False,reference=data.get('reference')).first()
    return _reconcile_event(attempt)
def _reconcile_event(attempt):
    if not attempt:return HttpResponse(status=200)
    try:reconcile(attempt.pk)
    except GatewayError:return HttpResponse('Verification pending',status=503)
    return HttpResponse(status=200)
@csrf_exempt
@require_POST
def platform_webhook(request):
    """Mall Pay events, signed with the marketplace Paystack secret."""
    if len(request.body)>1000000:return HttpResponseBadRequest('Payload too large')
    try:secret=platform_secret()
    except GatewayError:return HttpResponse('Gateway unavailable',status=503)
    if not valid_signature(request.body,request.headers.get('X-Paystack-Signature',''),secret):return HttpResponse('Invalid signature',status=401)
    try:payload=json.loads(request.body)
    except (ValueError,UnicodeDecodeError):return HttpResponseBadRequest('Invalid JSON')
    if not isinstance(payload,dict) or not isinstance(payload.get('data',{}),dict):return HttpResponseBadRequest('Invalid event')
    if payload.get('event')!='charge.success':return HttpResponse(status=200)
    return _reconcile_event(PaymentAttempt.objects.filter(platform=True,reference=payload['data'].get('reference')).first())
@login_required
@require_POST
def cancel_order(request,pk):
    get_object_or_404(Order,pk=pk,buyer=request.user)
    try:cancel(pk,request.user);messages.success(request,'Order cancelled and stock restored.')
    except ValueError as e:messages.error(request,str(e))
    return redirect('orders')
@login_required
@require_POST
def return_order(request,pk):
    get_object_or_404(Order,pk=pk,buyer=request.user)
    try:request_return(pk,request.user,request.POST.get('reason',''));messages.success(request,'Return request sent to your seller.')
    except ValueError as e:messages.error(request,str(e))
    return redirect('orders')
@login_required
def returns(request):
    shop=get_object_or_404(Shop,owner=request.user)
    if request.method=='POST':
        obj=get_object_or_404(ReturnRequest,pk=request.POST.get('request'),order__shop=shop)
        try:decide_return(obj.pk,request.user,request.POST.get('decision'),request.POST.get('response',''),request.POST.get('reference',''),request.POST.get('restock')=='on');messages.success(request,'Return request updated.')
        except ValueError as e:messages.error(request,str(e))
        return redirect('returns')
    return render(request,'returns.html',{'shop':shop,'requests':ReturnRequest.objects.filter(order__shop=shop).select_related('order')})
@login_required
def store_settings(request):
    shop=get_object_or_404(Shop,owner=request.user);obj,_=ShopSettings.objects.get_or_create(shop=shop);form=SettingsForm(request.POST or None,instance=obj)
    if request.method=='POST' and form.is_valid():form.save();AuditEvent.objects.create(shop=shop,actor=request.user,action='Delivery settings changed',detail='');messages.success(request,'Store settings saved.');return redirect('store_settings')
    return render(request,'seller_form.html',{'form':form,'title':'Delivery, collection & returns','subtitle':'Your delivery fee is added to each order and shown before checkout.'})
@login_required
def verification(request):
    shop=get_object_or_404(Shop,owner=request.user);form=VerificationForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        if VerificationRequest.objects.filter(shop=shop,state='Pending').exists():messages.error(request,'A verification request is already pending.')
        else:
            obj=form.save(commit=False);obj.shop=shop;obj.save();messages.success(request,'Your business details have been submitted for review.')
        return redirect('seller')
    return render(request,'seller_form.html',{'form':form,'title':'Verify your business','subtitle':'A platform administrator will review your details before activating your store.'})
@login_required
def notifications(request):
    if request.method=='POST':Notification.objects.filter(recipient=request.user,date_read__isnull=True).update(date_read=timezone.now());return redirect('notifications')
    return render(request,'notifications.html',{'notifications':Notification.objects.filter(recipient=request.user).order_by('-date_sent')[:100]})
@login_required
def invoice(request,pk):
    order=get_object_or_404(Order,pk=pk)
    if order.buyer_id!=request.user.pk and order.shop.owner_id!=request.user.pk:
        from .views import access_shop
        access_shop(request,order.shop.slug,'finance')
    return render(request,'invoice.html',{'order':order})


from django import forms as _forms
class MallPayForm(_forms.Form):
    business_name=_forms.CharField(max_length=100,label='Business name on settlements')
    settlement_bank=_forms.ChoiceField(label='Bank or mobile-money provider')
    account_number=_forms.RegexField(r'^\d{6,20}$',max_length=20,label='Account or mobile-money number',help_text='Digits only. Payouts for each sale are settled here by Paystack.')
    active=_forms.BooleanField(required=False,initial=True,label='Accept online payments with Mall Pay')
    def __init__(self,*args,banks=(),**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['settlement_bank'].choices=[('','Choose…')]+[(b['code'],b['name']+(' (mobile money)' if b['type']=='mobile_money' else '')) for b in banks]

def settlement_banks(currency):
    from django.core.cache import cache
    from .paystack import Paystack
    key='paystack-banks:'+currency;banks=cache.get(key)
    if banks is None:
        banks=Paystack(platform_secret()).banks(currency);cache.set(key,banks,86400)
    return banks

@login_required
def mall_pay(request):
    """Mall Pay: the marketplace Paystack account takes payment and splits it to the seller automatically."""
    shop=get_object_or_404(Shop,owner=request.user)
    connection=GatewayConnection.objects.filter(shop=shop).first()
    context={'shop':shop,'connection':connection,'available':platform_available(shop),'configured':bool(settings.PLATFORM_PAYSTACK_SECRET),'rate':None}
    from .models import CommissionPolicy
    policy=CommissionPolicy.objects.filter(effective__lte=timezone.now()).order_by('-effective').first()
    context['rate']=(policy.rate if policy else 0.03)*100
    if not context['available']:return render(request,'mall_pay.html',context)
    try:banks=settlement_banks(shop.currency)
    except GatewayError as e:
        context['error']=str(e);return render(request,'mall_pay.html',context)
    initial={'business_name':shop.name,'active':True}
    if connection and connection.is_platform:initial.update(settlement_bank=connection.settlement_bank,active=connection.active)
    form=MallPayForm(request.POST or None,banks=banks,initial=initial)
    if request.method=='POST' and form.is_valid():
        data=form.cleaned_data;names={b['code']:b['name'] for b in banks}
        try:
            save_mall_pay(shop,request.user,data['business_name'],data['settlement_bank'],names.get(data['settlement_bank'],''),data['account_number'],data['active'])
            messages.success(request,'Mall Pay is set up. Customers can now pay online and Paystack settles each sale to your account.');return redirect('mall_pay')
        except GatewayError as e:form.add_error(None,str(e))
    context['form']=form
    return render(request,'mall_pay.html',context)
