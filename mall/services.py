from django.db import transaction
from django.utils import timezone
from decimal import Decimal
from .models import Product,Order,OrderLine,CommissionPolicy,PaymentMethod,ShopSettings,Notification
@transaction.atomic
def checkout(buyer,cart,address,method_ids,key,fulfilments=None,delivery_address=None,basket_ids=None):
    from django.contrib.auth import get_user_model
    get_user_model().objects.select_for_update().get(pk=buyer.pk)
    existing=list(Order.objects.filter(buyer=buyer,checkout_key=key))
    if existing: return existing
    if not address.strip() or len(address)>2000: raise ValueError('Enter delivery or collection instructions of up to 2,000 characters.')
    if not cart: raise ValueError('Your bag is empty.')
    products={str(p.pk):p for p in Product.objects.select_for_update().select_related('shop').filter(pk__in=cart).order_by('pk')}
    groups={}
    for pk,qty in cart.items():
        p=products.get(pk)
        if not isinstance(qty,int) or qty<1 or qty>99: raise ValueError('Invalid quantity.')
        if not p or not p.active or not p.shop.active or p.classified or p.stock<qty: raise ValueError('An item is unavailable or has insufficient stock.')
        groups.setdefault(p.shop_id,[]).append((p,qty))
    open_limit_check(buyer,groups)
    policy=CommissionPolicy.objects.filter(effective__lte=timezone.now()).order_by('-effective').first()
    rate=policy.rate if policy else Decimal('0.03')
    if delivery_address and delivery_address.get('whatsapp_opt_in'):
        delivery_address={**delivery_address,'whatsapp_opt_in_at':timezone.now().isoformat()}
    orders=[]
    for sid,items in groups.items():
        from .delivery import ensure_cod
        default_method=ensure_cod(items[0][0].shop)
        method=PaymentMethod.objects.filter(pk=method_ids.get(str(sid)) or default_method.pk,shop_id=sid,active=True).first()
        if not method: raise ValueError('Choose an available payment method for each seller.')
        total=sum((p.price*q for p,q in items),Decimal('0'))
        from .pricing import commission
        fee=commission(total,rate,timezone.localtime(items[0][0].shop.created).date(),timezone.localdate())
        shop=items[0][0].shop
        delivery=ShopSettings.objects.filter(shop=shop).first()
        fulfilment=(fulfilments or {}).get(str(sid),'delivery')
        if fulfilment not in ['delivery','collection']:raise ValueError('Choose delivery or collection.')
        if fulfilment=='collection' and delivery and not delivery.collection_available:raise ValueError('Collection is not available from '+shop.name+'.')
        from .delivery import delivery_fee as quote_delivery
        delivery_fee=quote_delivery(delivery,fulfilment,delivery_address)
        order_address=address
        if fulfilment=='collection':order_address='Collection: '+(delivery.collection_address if delivery else 'Arrange with seller')+' · '+address
        o=Order(buyer=buyer,shop_id=sid,total=total+delivery_fee,commission=fee,fulfilment=fulfilment,currency=shop.currency,delivery_fee=delivery_fee,payment_method=method,address=order_address,delivery_address=delivery_address or {},cash_on_delivery=method.kind=='cod',status='Confirmed' if method.kind=='cod' else 'Awaiting payment',payment_snapshot=method.label+' · '+method.instructions,checkout_key=key)
        from .oscar_bridge import place
        place(o,items,basket_id=(basket_ids or {}).get(str(sid)))
        from .messaging import record_event
        record_event(o,'Order placed',actor=buyer)
        Notification.objects.create(recipient=shop.owner,subject='New order #'+str(o.pk),body='/seller/')
        orders.append(o)
    return orders


OPEN_UNPAID=['Awaiting payment','Confirmed']
def open_unpaid_orders(buyer):
    """Orders that still hold stock without any verified payment or seller preparation."""
    from .models import Receipt
    return Order.objects.filter(buyer=buyer,oscar_order__status__in=OPEN_UNPAID).exclude(pk__in=Receipt.objects.values('order_id'))
def open_limit_check(buyer,groups):
    from django.conf import settings
    total_limit=getattr(settings,'MAX_OPEN_UNPAID_ORDERS',10)
    shop_limit=getattr(settings,'MAX_OPEN_UNPAID_ORDERS_PER_SHOP',3)
    current=open_unpaid_orders(buyer)
    if current.count()+len(groups)>total_limit:
        raise ValueError(f'You already have {current.count()} unpaid orders reserving stock. Pay for or cancel some of them (My orders) before placing more.')
    for sid in groups:
        if current.filter(shop_id=sid).count()+1>shop_limit:
            raise ValueError('You have too many unpaid orders with one of these sellers. Pay for or cancel an existing order first.')

def expire_unpaid_orders(now=None):
    """Cancel online/manual-payment orders left unpaid past the hold period, releasing their stock.

    Cash on Delivery orders are excluded: the seller decides on them (and can cancel them).
    Orders where the buyer submitted a payment reference wait for the seller to verify it.
    """
    from datetime import timedelta
    from django.conf import settings
    from .order_actions import cancel
    hours=getattr(settings,'UNPAID_ORDER_HOLD_HOURS',48)
    if not hours:return []
    cutoff=(now or timezone.now())-timedelta(hours=hours)
    from .models import PaymentAttempt
    recent_attempts=PaymentAttempt.objects.filter(created__gte=cutoff).values('order_id')
    stale=Order.objects.filter(oscar_order__status='Awaiting payment',cash_on_delivery=False,oscar_order__date_placed__lt=cutoff,payment_reference='').exclude(pk__in=recent_attempts)
    expired=[]
    for pk in stale.values_list('pk',flat=True):
        try:cancel(pk,None,f'Not paid within {hours} hours; reserved stock released automatically.');expired.append(pk)
        except ValueError:pass
    return expired
