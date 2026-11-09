from decimal import Decimal
from io import StringIO
from django.test import TestCase,override_settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from oscar.core.loading import get_model,get_class
from oscar.apps.address.abstract_models import AbstractUserAddress
from oscar.apps.order.exceptions import InvalidOrderStatus
from .models import Shop,Product,Order,BuyerAddress,Review,Wishlist,Notification,OrderLine,Receipt
from .services import checkout
from .address_views import save_address
from .order_actions import advance,confirm_payment,request_return,decide_return
from .messaging import dispatch_one

@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class OscarCoreTests(TestCase):
    def setUp(self):
        users=get_user_model();self.owner=users.objects.create_user('seller');self.buyer=users.objects.create_user('buyer',email='buyer@example.test');self.other=users.objects.create_user('outsider')
        self.shop=Shop.objects.create(owner=self.owner,name='Store',slug='store',active=True)
        self.product=Product.objects.create(shop=self.shop,name='Oscar item',description='Native',price=100,stock=8,category='Fashion')
        self.data={'recipient':'Buyer Name','phone':'0241234567','country':'GH','region':'Greater Accra','city':'Accra','street':'12 Market Road','landmark':'Library','digital_address':'','instructions':'Call first'}
    def order(self):return checkout(self.buyer,{str(self.product.pk):2},'Address',{},'core-test',delivery_address=self.data)[0]

    def test_native_models_and_no_shadow_commerce_fields(self):
        self.assertTrue(issubclass(BuyerAddress,AbstractUserAddress))
        self.assertEqual([m._meta.label for m in [Review,Wishlist,Notification,OrderLine]],['reviews.ProductReview','wishlists.WishList','communication.Notification','order.Line'])
        for model,removed in [(Product,{'name','description','price','stock','category','active'}),(Order,{'status','total','currency','delivery_fee','delivery_address','address','created'})]:
            self.assertFalse({field.name for field in model._meta.fields}&removed)

    def test_oscar_edits_are_immediately_visible_without_synchronising(self):
        get_model('catalogue','Product').objects.filter(pk=self.product.oscar_product_id).update(title='Edited in Oscar')
        record=get_model('partner','StockRecord').objects.get(product=self.product.oscar_product)
        record.price=Decimal('145');record.num_in_stock=6;record.num_allocated=2;record.save()
        self.product.refresh_from_db()
        self.assertEqual(self.product.name,'Edited in Oscar');self.assertEqual(self.product.price,145);self.assertEqual(self.product.stock,4)
        self.assertContains(self.client.get('/product/'+str(self.product.pk)+'/'),'Edited in Oscar')

    def test_basket_uses_oscar_lines_and_ignores_session_quantity_cache(self):
        self.client.force_login(self.buyer);self.client.post('/bag/add/'+str(self.product.pk)+'/',{'quantity':2})
        refs=self.client.session['oscar_baskets'];basket=get_model('basket','Basket').objects.get(pk=refs[str(self.shop.pk)])
        self.assertEqual(basket.owner,self.buyer);self.assertEqual(basket.lines.get().product,self.product.oscar_product)
        session=self.client.session;session['cart']={str(self.product.pk):99};session.save()
        response=self.client.get('/bag/');self.assertEqual(response.context['item_count'],2)
        self.assertEqual(self.client.session['cart'][str(self.product.pk)],2)

    def test_checkout_submits_existing_oscar_basket(self):
        self.client.force_login(self.buyer);self.client.post('/bag/add/'+str(self.product.pk)+'/',{'quantity':2})
        basket_id=self.client.session['oscar_baskets'][str(self.shop.pk)]
        self.client.post('/bag/',self.data)
        order=Order.objects.get();self.assertEqual(order.oscar_order.basket_id,basket_id)
        self.assertEqual(order.oscar_order.basket.status,'Submitted')
        self.assertEqual(order.oscar_order.lines.get().status,'Confirmed')

    def test_oscar_address_copy_usage_and_immutable_order_snapshot(self):
        address=save_address(self.buyer,self.data,'Home');order=self.order();address.refresh_from_db()
        self.assertEqual(address.num_orders_as_shipping_address,1)
        self.assertEqual(order.oscar_order.shipping_address.line1,'12 Market Road')
        save_address(self.buyer,{**self.data,'street':'Changed Road'},address=address)
        order.refresh_from_db();self.assertEqual(order.delivery_address['street'],'12 Market Road')
        self.assertNotIn('street',order.delivery_metadata)

    def test_native_status_shipping_payment_and_refund_history(self):
        order=self.order();advance(order.pk,self.owner,'Preparing');advance(order.pk,self.owner,'Dispatched','TRACK-1')
        line=order.oscar_order.lines.get();self.assertEqual(line.num_allocated,0)
        self.assertTrue(order.oscar_order.status_changes.filter(new_status='Dispatched').exists())
        self.assertTrue(order.oscar_order.shipping_events.filter(event_type__name='Dispatched').exists())
        confirm_payment(order.pk,self.owner,'CASH-1');advance(order.pk,self.owner,'Delivered')
        source=order.oscar_order.sources.get();self.assertEqual(source.transactions.get(txn_type='Debit').amount,200)
        self.assertTrue(order.oscar_order.payment_events.filter(event_type__name='Payment received').exists())
        request=request_return(order.pk,self.buyer,'Returned');decide_return(request.pk,self.owner,'Refund confirmed','Refunded','REFUND-1',True)
        source.refresh_from_db();self.assertEqual(source.amount_refunded,200)
        self.assertEqual(source.transactions.get(txn_type='Refund').reference,'REFUND-1')
        self.product.refresh_from_db();self.assertEqual(self.product.stock,8)

    def test_oscar_dashboard_uses_cod_guards_and_tenant_authorisation(self):
        order=self.order();handler=get_class('order.processing','EventHandler')(user=self.owner)
        with self.assertRaises(InvalidOrderStatus):handler.handle_order_status_change(order.oscar_order,'Paid')
        with self.assertRaises(InvalidOrderStatus):get_class('order.processing','EventHandler')(user=self.other).handle_order_status_change(order.oscar_order,'Preparing')
        handler.handle_order_status_change(order.oscar_order,'Preparing')
        order.refresh_from_db();self.assertEqual(order.status,'Preparing')

    def test_native_totals_are_the_only_order_money_source(self):
        order=self.order();self.product.price=999;self.product.save()
        order.refresh_from_db();self.assertEqual(order.total,200)
        order.total=1
        with self.assertRaises(ValueError):order.save(update_fields=['total'])
        order.refresh_from_db();self.assertEqual(order.total,order.oscar_order.total_incl_tax)

    def test_oscar_partner_membership_and_tenant_stock_selection(self):
        self.assertTrue(self.shop.oscar_partner.users.filter(pk=self.owner.pk).exists())
        second=Shop.objects.create(owner=self.other,name='Second',slug='second',active=True)
        get_model('partner','StockRecord').objects.create(product=self.product.oscar_product,partner=second.oscar_partner,partner_sku='other-price',price=1,price_currency='GHS',num_in_stock=100)
        info=get_class('partner.strategy','Selector')().strategy().fetch_for_product(self.product.oscar_product)
        self.assertEqual(info.stockrecord.partner,self.shop.oscar_partner);self.assertEqual(info.price.incl_tax,100)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_communication_history_and_read_only_architecture_audit(self):
        order=self.order();event=order.tracking_events.get()
        self.assertEqual(event.communication_event.order,order.oscar_order)
        dispatch_one(event.messages.get(channel='email',audience='buyer').pk)
        self.assertEqual(get_model('communication','Email').objects.get(user=self.buyer).email,self.buyer.email)
        output=StringIO();call_command('audit_oscar',stdout=output);self.assertIn('"issues": []',output.getvalue())
