"""Oscar baskets, split by seller so currencies and settlement stay independent.

The session stores private basket IDs and a compatibility count cache. Quantities
and product selections are read from Oscar basket lines, not from that cache.
"""
from django.db import transaction
from django.contrib.auth import get_user_model
from oscar.core.loading import get_model,get_class

def basket_map(request):
    return request.session.get('oscar_baskets',{})

def read_cart(request):
    if hasattr(request,'_mall_cart'):return request._mall_cart.copy()
    refs=basket_map(request)
    if 'oscar_baskets' not in request.session and request.session.get('cart'):
        write_cart(request,request.session['cart']);return request._mall_cart.copy()
    cart={};valid={}
    for sid,pk in refs.items():
        basket=get_model('basket','Basket').objects.filter(pk=pk,status='Open').first()
        if not basket or (basket.owner_id is not None and (not request.user.is_authenticated or basket.owner_id!=request.user.pk)):continue
        if request.user.is_authenticated and basket.owner_id is None:
            basket.owner=request.user;basket.save(update_fields=['owner'])
        valid[sid]=pk
        for line in basket.lines.select_related('product__tenant_listing'):
            listing=getattr(line.product,'tenant_listing',None)
            if listing and str(listing.shop_id)==sid:cart[str(listing.pk)]=line.quantity
    request.session['oscar_baskets']=valid;request.session['cart']=cart
    request._mall_cart=cart;return cart.copy()

@transaction.atomic
def write_cart(request,cart):
    from .models import Product
    if request.user.is_authenticated:get_user_model().objects.select_for_update().get(pk=request.user.pk)
    groups={}
    for product in Product.objects.filter(pk__in=cart).select_related('shop','oscar_product'):
        quantity=cart[str(product.pk)]
        if not isinstance(quantity,int) or not 1<=quantity<=99:raise ValueError('Invalid basket quantity.')
        groups.setdefault(str(product.shop_id),[]).append((product,quantity))
    refs=basket_map(request);updated={};cache={}
    Basket=get_model('basket','Basket')
    for sid,items in groups.items():
        basket=Basket.objects.select_for_update().filter(pk=refs.get(sid),status=Basket.OPEN).first()
        if basket and basket.owner_id is not None and (not request.user.is_authenticated or basket.owner_id!=request.user.pk):basket=None
        if not basket:basket=Basket.objects.create(owner=request.user if request.user.is_authenticated else None)
        elif request.user.is_authenticated and basket.owner_id is None:basket.owner=request.user;basket.save(update_fields=['owner'])
        basket.strategy=get_class('partner.strategy','Selector')().strategy(request=request)
        wanted={p.oscar_product_id for p,q in items};basket.lines.exclude(product_id__in=wanted).delete()
        for product,quantity in items:
            line=basket.lines.filter(product=product.oscar_product).first()
            if line:line.quantity=quantity;line.save(update_fields=['quantity'])
            else:basket.add_product(product.oscar_product,quantity=quantity)
            cache[str(product.pk)]=quantity
        basket.reset_offer_applications();updated[sid]=basket.pk
    for sid,pk in refs.items():
        if sid not in updated:
            basket=Basket.objects.select_for_update().filter(pk=pk,status=Basket.OPEN).first()
            if basket and (basket.owner_id is None or request.user.is_authenticated and basket.owner_id==request.user.pk):basket.lines.all().delete()
    request.session['oscar_baskets']=updated;request.session['cart']=cache;request._mall_cart=cache

def clear_cart(request):
    request.session['oscar_baskets']={};request.session['cart']={};request._mall_cart={}
