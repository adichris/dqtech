import secrets
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render,redirect,get_object_or_404
from django.views.decorators.http import require_POST
from .models import Product,ShopSettings,Wishlist
from .services import checkout
from .discovery import catalogue
from .delivery import DeliveryAddressForm,ensure_cod,delivery_fee
from .geography import REGIONS
from django.conf import settings
from .address_views import checkout_addresses,save_address
from django.db import transaction
from .baskets import read_cart,write_cart,clear_cart,basket_map
from .security import ratelimit

def context(request):
    cart=read_cart(request);groups={};totals={};subtotals={};fees={};valid=True;count=0
    products=list(Product.objects.filter(pk__in=cart).select_related('shop'))
    existing={str(p.pk) for p in products}
    if set(cart)-existing:
        cart={k:v for k,v in cart.items() if k in existing};write_cart(request,cart)
        messages.warning(request,'A product that is no longer listed was removed from your bag.')
    for p in products:
        qty=cart[str(p.pk)];subtotal=p.price*qty;count+=qty
        available=p.active and p.shop.active and not p.classified and qty<=p.stock
        valid=valid and available
        group=groups.setdefault(p.shop_id,{'shop':p.shop,'items':[],'subtotal':Decimal('0')})
        group['items'].append({'p':p,'qty':qty,'subtotal':subtotal,'available':available});group['subtotal']+=subtotal
    addresses=checkout_addresses(request)
    destination=request.POST if request.method=='POST' else addresses['address_form'].initial
    for group in groups.values():
        group['cod']=ensure_cod(group['shop'])
        config=ShopSettings.objects.filter(shop=group['shop']).first()
        group['collection_available']=config.collection_available if config else True
        group['collection_address']=config.collection_address if config else ''
        group['regional_rates']=config.regional_delivery_fees if config else {}
        group['base_delivery_fee']=config.delivery_fee if config else Decimal('0')
        group['delivery_fee']=delivery_fee(config,'delivery',destination)
        group['total']=group['subtotal']+group['delivery_fee'];currency=group['shop'].currency
        totals[currency]=totals.get(currency,Decimal('0'))+group['total']
        subtotals[currency]=subtotals.get(currency,Decimal('0'))+group['subtotal']
        fees[currency]=fees.get(currency,Decimal('0'))+group['delivery_fee']
    request.session.setdefault('checkout_key',secrets.token_hex(24))
    return {**addresses,'delivery_regions':REGIONS,'delivery_rates':{str(g['shop'].pk):g['regional_rates'] for g in groups.values()},'geo_url':settings.GEO_LOOKUP_URL,'groups':list(groups.values()),'totals':list(totals.items()),'summaries':[{'currency':key,'subtotal':subtotals[key],'fee':fees[key],'total':total} for key,total in totals.items()],'item_count':count,'can_checkout':bool(groups) and valid,'products':catalogue().exclude(pk__in=cart).order_by('-rating_count','-pk')[:4]}
@ratelimit('checkout',20,600,key='user')
@transaction.atomic
def basket(request):
    data=context(request)
    address_form=DeliveryAddressForm(request.POST) if request.method=='POST' else data['address_form']
    data.update(address_form=address_form,delivery_regions=REGIONS,geo_url=settings.GEO_LOOKUP_URL)
    if request.method=='POST':
        if not request.user.is_authenticated:return redirect('/login/?next=/bag/')
        try:
            methods={str(g['shop'].pk):request.POST.get('method_'+str(g['shop'].pk)) for g in data['groups']}
            fulfilments={str(g['shop'].pk):request.POST.get('fulfilment_'+str(g['shop'].pk),'delivery') for g in data['groups']}
            if not address_form.is_valid():raise ValueError('Please check the highlighted address fields.')
            checkout(request.user,read_cart(request),address_form.formatted(),methods,request.session['checkout_key'],fulfilments=fulfilments,delivery_address=address_form.cleaned_data,basket_ids=basket_map(request))
            if request.POST.get('save_address')=='on' and all(address_form.cleaned_data.get(field) for field in ['street','city','region']):
                save_address(request.user,address_form.cleaned_data,request.POST.get('address_label','Home'),request.POST.get('default_address')=='on')
            clear_cart(request);request.session.pop('checkout_key',None)
            messages.success(request,'Your orders are placed. Cash on Delivery is payable on arrival or collection; other payments follow the seller instructions.');return redirect('orders')
        except (ValueError,TypeError) as e:messages.error(request,str(e))
    return render(request,'bag_content.html' if request.headers.get('HX-Request')=='true' else 'bag.html',data)
@require_POST
def update_quantity(request,pk):
    p=get_object_or_404(Product,pk=pk);cart=read_cart(request)
    try:qty=int(request.POST.get('quantity',''))
    except (ValueError,TypeError):qty=0
    error=None
    if str(pk) not in cart:error='This product is not in your bag.'
    elif not p.active or not p.shop.active or p.classified:error='This product is no longer available.'
    elif qty<1 or qty>min(p.stock,99):error='Choose a quantity between 1 and '+str(min(p.stock,99))+'.'
    else:cart[str(pk)]=qty;write_cart(request,cart)
    if error:messages.error(request,error)
    if request.headers.get('HX-Request')=='true':
        data=context(request);data['basket_error']=error
        return render(request,'bag_content.html',data,status=422 if error else 200)
    return redirect('bag')
@require_POST
def remove_item(request,pk):
    cart=read_cart(request);cart.pop(str(pk),None);write_cart(request,cart)
    if request.headers.get('HX-Request')=='true':return render(request,'bag_content.html',context(request))
    return redirect('bag')
@login_required
@require_POST
def save_for_later(request,pk):
    p=get_object_or_404(Product,pk=pk,active=True,shop__active=True)
    from .favourites import save_find
    save_find(request.user,p)
    cart=read_cart(request);cart.pop(str(pk),None);write_cart(request,cart)
    messages.success(request,'Saved to your favourites.');return redirect('bag')
