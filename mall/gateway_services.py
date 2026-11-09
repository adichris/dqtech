import secrets
from django.conf import settings
from django.db import transaction
from .models import Order,GatewayConnection,PaymentAttempt,AuditEvent
from .gateway_crypto import decrypt_secret,matches_payment
from .paystack import Paystack,GatewayError
from .order_actions import confirm_payment

def platform_secret():
    secret=getattr(settings,'PLATFORM_PAYSTACK_SECRET','')
    if not secret:raise GatewayError('Mall Pay is not configured by the platform administrator.')
    return secret
def platform_available(shop):
    return bool(getattr(settings,'PLATFORM_PAYSTACK_SECRET','')) and shop.currency in getattr(settings,'PLATFORM_PAYSTACK_CURRENCIES',[])
def attempt_secret(attempt):
    """An attempt is always verified with the account it was initialised on, even after a mode switch."""
    return platform_secret() if attempt.platform else secret_for(attempt.gateway)
def secret_for(connection):
    key=getattr(settings,'GATEWAY_ENCRYPTION_KEY','')
    if not key:raise GatewayError('Gateway encryption has not been configured by the platform administrator.')
    try:return decrypt_secret(connection.encrypted_secret,key)
    except Exception:raise GatewayError('Gateway credentials cannot be decrypted. Contact the platform administrator.') from None

def begin(order_id,buyer):
    with transaction.atomic():
        order=Order.objects.select_for_update().select_related('shop','payment_method').get(pk=order_id,buyer=buyer)
        if order.status!='Awaiting payment':raise GatewayError('This order is no longer awaiting payment.')
        if not order.payment_method or order.payment_method.kind!='online':raise GatewayError('This order uses a manual payment method.')
        gateway=GatewayConnection.objects.filter(shop=order.shop,active=True).first()
        if not gateway:raise GatewayError('The seller has no active online gateway.')
        platform=gateway.is_platform
        if platform and (not gateway.subaccount_code or not platform_available(order.shop)):raise GatewayError('Mall Pay is not available for this seller yet.')
        if not platform and not gateway.encrypted_secret:raise GatewayError('The seller has no active online gateway.')
        if not buyer.email:raise GatewayError('Set an email address on your account before paying online.')
        if not settings.PUBLIC_BASE_URL.startswith('https://') and not settings.DEBUG:raise GatewayError('A secure public callback address is required.')
        attempt=PaymentAttempt.objects.filter(order=order,gateway=gateway,platform=platform,status__in=['pending','initialized']).order_by('-created').first()
        if not attempt:attempt=PaymentAttempt.objects.create(order=order,gateway=gateway,platform=platform,platform_commission=order.commission if platform else 0,reference='dq_'+secrets.token_hex(20))
        if attempt.authorization_url:return attempt.authorization_url
    api=Paystack(attempt_secret(attempt))
    callback=settings.PUBLIC_BASE_URL.rstrip('/')+'/payment/callback/'
    url=api.initialize(buyer.email,order.total,order.currency,attempt.reference,callback,subaccount=gateway.subaccount_code if platform else '',platform_charge=attempt.platform_commission)
    with transaction.atomic():
        locked=PaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
        if locked.status=='pending':locked.authorization_url=url;locked.status='initialized';locked.save()
    return url

def reconcile(attempt_id):
    attempt=PaymentAttempt.objects.select_related('gateway','order__shop').get(pk=attempt_id)
    data=Paystack(attempt_secret(attempt)).verify(attempt.reference)
    if not matches_payment(data,attempt.reference,attempt.order.total,attempt.order.currency):raise GatewayError('The provider has not confirmed a matching successful payment.')
    with transaction.atomic():
        # Always lock order before attempt so callback and fulfilment use one lock order.
        order=Order.objects.select_for_update().select_related('shop').get(pk=attempt.order_id)
        attempt=PaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
        if attempt.status=='succeeded':return order
        if order.status!='Awaiting payment':
            attempt.status='review';attempt.provider_transaction=str(data['id']);attempt.save()
            AuditEvent.objects.create(shop=order.shop,actor=order.shop.owner,action='Payment needs reconciliation',detail=attempt.reference)
            return order
        if PaymentAttempt.objects.filter(gateway=attempt.gateway,provider_transaction=str(data['id']),status='succeeded').exclude(pk=attempt.pk).exists():raise GatewayError('This provider transaction has already been used.')
        confirm_payment(order.pk,order.shop.owner,attempt.reference,'mall_pay' if attempt.platform else 'paystack')
        attempt.provider_transaction=str(data['id']);attempt.status='succeeded';attempt.save()
        if attempt.platform and attempt.platform_commission>0:record_collected_commission(order,attempt.platform_commission)
        order.refresh_from_db();return order

def record_collected_commission(order,amount):
    """Mall Pay deducts commission inside the Paystack split, so it is collected, not owed."""
    from .models import BillingInvoice
    from .ledger import post
    BillingInvoice.objects.get_or_create(order=order,defaults={'shop':order.shop,'amount':amount,'currency':order.currency,'state':'Collected'})
    post(order.shop,'commission:'+str(order.pk),'Marketplace commission deducted by Mall Pay',[('commission_expense',amount,0),('seller_receipts',0,amount)])

def save_mall_pay(shop,actor,business_name,bank_code,bank_name,account_number,active):
    """Create/update the seller's Paystack subaccount on the marketplace account and enable Mall Pay."""
    from .models import PaymentMethod
    if not platform_available(shop):raise GatewayError('Mall Pay is not available for '+shop.currency+' stores yet.')
    connection=GatewayConnection.objects.filter(shop=shop).first()
    existing=connection.subaccount_code if connection else ''
    data=Paystack(platform_secret()).save_subaccount(existing,business_name,bank_code,account_number,shop.owner.email)
    code=str(data.get('subaccount_code') or existing)
    if not code.startswith('ACCT_'):raise GatewayError('Paystack did not return a subaccount for these settlement details.')
    with transaction.atomic():
        connection,_=GatewayConnection.objects.update_or_create(shop=shop,defaults={'mode':GatewayConnection.PLATFORM,'subaccount_code':code,'settlement_bank':bank_code,'settlement_bank_name':bank_name[:120],'account_last4':account_number[-4:],'account_name':str(data.get('account_name') or data.get('business_name') or business_name)[:150],'test_mode':platform_secret().startswith('sk_test_'),'active':active})
        PaymentMethod.objects.update_or_create(shop=shop,kind='online',defaults={'label':'Pay online (Mall Pay)','instructions':'Pay securely by card or mobile money through the marketplace checkout.','active':active})
        AuditEvent.objects.create(shop=shop,actor=actor,action='Mall Pay settlement details saved',detail=bank_name[:60]+' ****'+account_number[-4:]+' active='+str(active))
    return connection
