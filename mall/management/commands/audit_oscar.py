import json
from django.core.management.base import BaseCommand,CommandError
from django.db import connection
from django.db.models import F
from oscar.core.loading import get_model
from mall.models import Shop,Product,Order,Receipt,BuyerAddress,Review,Wishlist,Notification,OrderLine,TrackingEvent

class Command(BaseCommand):
    help='Read-only audit of canonical Oscar models, tenant links and price/stock boundaries.'
    def handle(self,*args,**kwargs):
        issues=[]
        mappings={name:model._meta.label for name,model in [('addresses',BuyerAddress),('reviews',Review),('wishlists',Wishlist),('notifications',Notification),('order_lines',OrderLine)]}
        for label in ['mall_buyeraddress','mall_review','mall_wishlist','mall_notification','mall_orderline']:
            if label in connection.introspection.table_names():issues.append('Obsolete commerce table remains: '+label)
        for model,names in [(Product,['name','description','category','price','stock','active']),(Order,['address','delivery_address','status','total','currency','delivery_fee','created'])]:
            fields={field.name for field in model._meta.fields}
            for name in names:
                if name in fields:issues.append(f'Shadow field remains: {model._meta.label}.{name}')
        if Shop.objects.filter(oscar_partner__isnull=True).exists():issues.append('A store has no Oscar partner.')
        if Product.objects.filter(oscar_product__isnull=True).exists():issues.append('A listing has no Oscar product.')
        for listing in Product.objects.select_related('shop'):
            records=get_model('partner','StockRecord').objects.filter(product_id=listing.oscar_product_id,partner_id=listing.shop.oscar_partner_id)
            if records.count()!=1:issues.append(f'Listing #{listing.pk}: expected exactly one merchant stock record.')
            elif records.first().price_currency!=listing.shop.currency:issues.append(f'Listing #{listing.pk}: seller/currency mismatch.')
        if Order.objects.filter(oscar_order__isnull=True).exists():issues.append('A tenant order has no Oscar order.')
        if Order.objects.exclude(buyer_id=F('oscar_order__user_id')).exists():issues.append('An order buyer differs from its Oscar user.')
        if Order.objects.filter(oscar_order__shipping_address__isnull=True).exists():issues.append('An order has no Oscar shipping address.')
        for receipt in Receipt.objects.select_related('order'):
            if not get_model('payment','Source').objects.filter(order_id=receipt.order.oscar_order_id,reference=receipt.reference,currency=receipt.currency,amount_debited=receipt.amount).exists():issues.append(f'Receipt #{receipt.pk}: matching Oscar payment source missing.')
        if TrackingEvent.objects.filter(communication_event__isnull=True).exists():issues.append('Tracking event missing its Oscar communication event.')
        output={'native_models':mappings,'stores':Shop.objects.count(),'listings':Product.objects.count(),'orders':Order.objects.count(),'issues':issues}
        self.stdout.write(json.dumps(output,indent=2))
        if issues:raise CommandError('Oscar audit found issues; reconcile these records before launch.')
