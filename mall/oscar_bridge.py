"""Tenant boundary around Oscar catalogue, baskets, orders, stock and payments."""
from decimal import Decimal
from django.db import transaction
from oscar.core.loading import get_model,get_class
from .models import Shop,Product
def sync_product(product):
    """Read Oscar's canonical record; never overwrite it from a shadow stock value."""
    record=get_model('partner','StockRecord').objects.select_for_update().get(product_id=product.oscar_product_id,partner_id=product.shop.oscar_partner_id)
    return product.oscar_product,record
@transaction.atomic
def place(order,items,basket_id=None):
    from oscar.apps.checkout.calculators import OrderTotalCalculator
    from .shipping import MerchantShipping
    from .address_views import address_values
    Selector=get_class('partner.strategy','Selector');OrderCreator=get_class('order.utils','OrderCreator')
    Basket=get_model('basket','Basket')
    if basket_id:
        basket=Basket.objects.select_for_update().get(pk=basket_id,status=Basket.OPEN,owner=order.buyer)
        expected={p.oscar_product_id:q for p,q in items}
        actual={line.product_id:line.quantity for line in basket.lines.all()}
        if actual!=expected:raise ValueError('Your basket changed. Review it before placing your order.')
    else:basket=Basket.objects.create(owner=order.buyer)
    basket.strategy=Selector().strategy(user=order.buyer)
    for product,quantity in items:
        oscar_product,record=sync_product(product)
        if not basket_id:basket.add_product(oscar_product,quantity=quantity)
    method=MerchantShipping(order.shop,order.delivery_fee,order.fulfilment)
    charge=method.calculate(basket);total=OrderTotalCalculator().calculate(basket,charge)
    if total.incl_tax!=order.total or total.currency!=order.currency:raise ValueError('The commerce engine total does not match checkout.')
    basket.freeze()
    data=order.delivery_address.copy()
    data.setdefault('recipient',order.buyer.get_full_name() or order.buyer.username)
    data.setdefault('country',order.shop.country)
    if not data.get('street'):data['street']=order.address
    if data.get('legacy_address') and order.fulfilment=='collection':data['instructions']=data['legacy_address']
    shipping=get_model('order','ShippingAddress')(**address_values(data))
    if order.fulfilment=='collection':
        config=getattr(order.shop,'settings',None)
        shipping.line1=config.collection_address if config and config.collection_address else order.shop.location
    # Oscar copies address-book data into a separate immutable order address.
    user_address=get_model('address','UserAddress').objects.filter(user=order.buyer,hash=str(shipping.generate_hash())).first()
    if user_address:
        user_address.populate_alternative_model(shipping)
        from django.db.models import F
        get_model('address','UserAddress').objects.filter(pk=user_address.pk).update(num_orders_as_shipping_address=F('num_orders_as_shipping_address')+1)
    shipping.save()
    core=OrderCreator().place_order(basket=basket,total=total,shipping_method=method,shipping_charge=charge,shipping_address=shipping,user=order.buyer,order_number='DQ-'+str(order.pk) if order.pk else None,status=order.status)
    basket.submit();order.oscar_order=core;order.save(update_fields=['oscar_order']) if order.pk else order.save()
    for product,quantity in items:
        record=get_model('partner','StockRecord').objects.get(product_id=product.oscar_product_id)
        product._commerce.clear()
    return core

def set_status(order):
    if order.oscar_order_id:
        core=get_model('order','Order').objects.get(pk=order.oscar_order_id)
        get_class('order.processing','EventHandler')(marketplace_internal=True).handle_order_status_change(core,order.status)
        if order.status in ['Preparing','Dispatched','Delivered','Cancelled']:
            event_type,_=get_model('order','ShippingEventType').objects.get_or_create(name=order.status)
            if not core.shipping_events.filter(event_type=event_type).exists():
                lines=list(core.lines.all())
                get_class('order.processing','EventHandler')().handle_shipping_event(core,event_type,lines,[line.quantity for line in lines],reference=order.delivery_reference)

def record_receipt(order,reference,method):
    if not order.oscar_order_id:return
    Source=get_model('payment','Source');SourceType=get_model('payment','SourceType')
    kind,_=SourceType.objects.get_or_create(name=method)
    source,created=Source.objects.get_or_create(order=order.oscar_order,reference=reference,defaults={'source_type':kind,'currency':order.currency,'amount_allocated':order.total})
    if created:source.debit(order.total,reference=reference,status='Confirmed')
    event_type,_=get_model('order','PaymentEventType').objects.get_or_create(name='Payment received')
    if not order.oscar_order.payment_events.filter(event_type=event_type,reference=reference).exists():
        lines=list(order.oscar_order.lines.all())
        get_class('order.processing','EventHandler')().handle_payment_event(order.oscar_order,event_type,order.total,lines,[line.quantity for line in lines],reference=reference)
    set_status(order)

def record_refund(order,reference):
    if not order.oscar_order_id:return
    for source in order.oscar_order.sources.select_for_update():
        amount=source.amount_available_for_refund
        if amount>0:source.refund(amount,reference=reference,status='Externally confirmed')
    event_type,_=get_model('order','PaymentEventType').objects.get_or_create(name='Refund confirmed')
    if not order.oscar_order.payment_events.filter(event_type=event_type,reference=reference).exists():
        lines=list(order.oscar_order.lines.all())
        get_class('order.processing','EventHandler')().handle_payment_event(order.oscar_order,event_type,order.total,lines,[line.quantity for line in lines],reference=reference)

def release_stock(order,mode):
    if not order.oscar_order_id:return False
    StockRecord=get_model('partner','StockRecord')
    list(Product.objects.select_for_update().filter(oscar_product_id__in=order.oscar_order.lines.values('product_id')).order_by('pk'))
    for line in order.oscar_order.lines.select_related('stockrecord').order_by('stockrecord_id'):
        record=StockRecord.objects.select_for_update().get(pk=line.stockrecord_id)
        line.stockrecord=record
        if mode=='dispatch':line.consume_allocation(line.quantity)
        elif mode=='cancel':line.cancel_allocation(line.quantity)
        elif mode=='return':record.num_in_stock+=line.quantity;record.save(update_fields=['num_in_stock'])
        # Availability is read directly from this Oscar stock record.
    return True
