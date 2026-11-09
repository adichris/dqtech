"""Marketplace listing metadata over Oscar's canonical catalogue and stock.

Commerce fields are query aliases/properties, never a second price/inventory
table. Seller forms write through to Oscar Product, Category and StockRecord.
"""
from decimal import Decimal
from django.db import models,transaction
from django.db.models import F,OuterRef,Subquery,Value
from django.db.models.functions import Coalesce
from oscar.core.loading import get_model

COMMERCE_FIELDS={'name','description','active','category','price','stock'}
CATEGORIES=['Fashion','Electronics','Home & Living','Beauty','Food & Grocery','Campus essentials','Art & Crafts']

class ListingManager(models.Manager):
    def get_queryset(self):
        Stock=get_model('partner','StockRecord')
        Category=get_model('catalogue','ProductCategory')
        records=Stock.objects.filter(product_id=OuterRef('oscar_product_id'),partner_id=OuterRef('shop__oscar_partner_id')).order_by('pk')
        categories=Category.objects.filter(product_id=OuterRef('oscar_product_id')).order_by('pk')
        return super().get_queryset().annotate(
            name=F('oscar_product__title'),description=F('oscar_product__description'),active=F('oscar_product__is_public'),
            price=Coalesce(Subquery(records.values('price')[:1]),Value(Decimal('0')),output_field=models.DecimalField(max_digits=12,decimal_places=2)),
            stock=Coalesce(Subquery(records.annotate(available=F('num_in_stock')-Coalesce('num_allocated',0)).values('available')[:1]),0),
            category=Coalesce(Subquery(categories.values('category__name')[:1]),Value('Fashion')))

def get_value(instance,name):
    if name in instance._commerce:return instance._commerce[name]
    if not instance.oscar_product_id:return {'name':'','description':'','active':True,'category':'Fashion','price':Decimal('0'),'stock':0}[name]
    core=instance.oscar_product
    if name in ['name','description','active']:return getattr(core,{'name':'title','description':'description','active':'is_public'}[name])
    if name=='category':return core.categories.values_list('name',flat=True).first() or 'Fashion'
    record=core.stockrecords.filter(partner_id=instance.shop.oscar_partner_id).first()
    if name=='price':return record.price if record else Decimal('0')
    return record.net_stock_level if record else 0

@transaction.atomic
def save_listing(instance,*args,**kwargs):
    from .models import Shop
    updates=instance._commerce.copy()
    requested=kwargs.get('update_fields')
    if requested is not None:updates={k:v for k,v in updates.items() if k in requested}
    shop=Shop.objects.select_for_update().get(pk=instance.shop_id)
    Partner=get_model('partner','Partner');Core=get_model('catalogue','Product');Stock=get_model('partner','StockRecord');Class=get_model('catalogue','ProductClass');Category=get_model('catalogue','Category')
    if not shop.oscar_partner_id:
        shop.oscar_partner=Partner.objects.create(name=shop.name,code='shop-'+str(shop.pk));shop.save(update_fields=['oscar_partner'])
    if instance.oscar_product_id:core=Core.objects.select_for_update().get(pk=instance.oscar_product_id)
    else:
        cls,_=Class.objects.get_or_create(slug='marketplace-product',defaults={'name':'Marketplace product','track_stock':True,'requires_shipping':True})
        core=Core(product_class=cls,title=str(updates.get('name','')),description=str(updates.get('description','')),is_public=updates.get('active',True))
    for key,target in [('name','title'),('description','description'),('active','is_public')]:
        if key in updates:setattr(core,target,updates[key])
    core.save()
    instance.oscar_product=core
    if requested is not None:
        kwargs['update_fields']=[key for key in requested if key not in COMMERCE_FIELDS]
        if 'oscar_product' not in kwargs['update_fields']:kwargs['update_fields'].append('oscar_product')
    # Bypass only this adapter; normal Django model persistence still runs.
    models.Model.save(instance,*args,**kwargs)
    record,_=Stock.objects.get_or_create(product=core,partner=shop.oscar_partner,partner_sku='dq-'+str(instance.pk),defaults={'price':Decimal(str(updates.get('price',0))),'price_currency':shop.currency,'num_in_stock':int(updates.get('stock',0)),'num_allocated':0})
    record=Stock.objects.select_for_update().get(pk=record.pk)
    if 'price' in updates:record.price=Decimal(str(updates['price']))
    if 'stock' in updates:record.num_in_stock=int(updates['stock'])+(record.num_allocated or 0)
    record.price_currency=shop.currency;record.save()
    if 'category' in updates:
        from django.utils.text import slugify
        name=str(updates['category']);category=Category.objects.filter(slug=slugify(name),depth=1).first()
        if not category:category=Category.add_root(name=name,slug=slugify(name))
        core.categories.set([category])
    instance._commerce.clear()

def commerce_property(name):
    return property(lambda self:get_value(self,name),lambda self,value:self._commerce.__setitem__(name,value))
