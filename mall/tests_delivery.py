from decimal import Decimal
from datetime import timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Shop,Product,PaymentMethod,Order,Receipt,BillingInvoice,ShopSettings,Journal
from .delivery import DeliveryAddressForm,ensure_cod
from .geography import REGIONS
from .services import checkout
from .order_actions import confirm_payment,advance,cancel
from .forms import SettingsForm,PaymentForm


class DeliveryTests(TestCase):
    def setUp(self):
        users=get_user_model()
        self.owner=users.objects.create_user('merchant')
        self.buyer=users.objects.create_user('customer')
        self.shop=Shop.objects.create(owner=self.owner,name='Nationwide store',slug='nationwide',active=True,created=timezone.now()-timedelta(days=130))
        self.product=Product.objects.create(shop=self.shop,name='Parcel',price=100,stock=10,description='Test',category='Fashion')
        self.address={'recipient':'Customer Name','phone':'0241234567','country':'GH','region':'Greater Accra','city':'Accra','street':'12 Market Road','landmark':'Library','digital_address':'','instructions':'Call on arrival'}

    def order(self,key='cod',fulfilment='delivery'):
        return checkout(self.buyer,{str(self.product.pk):1},'Customer, Accra',{},key,{str(self.shop.pk):fulfilment},self.address.copy())[0]

    def test_default_for_new_seller_and_cannot_disable(self):
        cod=self.shop.payment_methods.get(kind='cod');self.assertTrue(cod.active)
        self.client.force_login(self.owner)
        self.client.post('/seller/payments/'+str(cod.pk)+'/toggle/')
        cod.refresh_from_db();self.assertTrue(cod.active)
        cod.active=False;cod.save();cod.refresh_from_db();self.assertTrue(cod.active)
        self.assertEqual(ensure_cod(self.shop).pk,cod.pk)
        self.assertNotIn('cod',[choice[0] for choice in PaymentForm().fields['kind'].choices])

    def test_default_checkout_reserves_stock_without_receipt(self):
        order=self.order();self.assertTrue(order.cash_on_delivery);self.assertEqual(order.status,'Confirmed')
        self.assertEqual(order.delivery_address,{**self.address,'phone':'+233241234567'})
        self.assertFalse(Receipt.objects.filter(order=order).exists());self.assertFalse(Journal.objects.exists())
        self.assertEqual(order.oscar_order.status,'Confirmed')
        self.product.refresh_from_db();self.assertEqual(self.product.stock,9)

    def test_cash_not_paid_until_collected_and_delivered(self):
        order=self.order()
        with self.assertRaises(ValueError):confirm_payment(order.pk,self.owner,'EARLY')
        advance(order.pk,self.owner,'Preparing')
        advance(order.pk,self.owner,'Dispatched','COURIER-1')
        with self.assertRaises(ValueError):advance(order.pk,self.owner,'Delivered')
        self.assertFalse(BillingInvoice.objects.exists())
        confirm_payment(order.pk,self.owner,'CASH-1')
        confirm_payment(order.pk,self.owner,'CASH-1')
        order.refresh_from_db();self.assertEqual(order.status,'Dispatched')
        self.assertEqual(order.receipt.method,'cash_on_delivery');self.assertEqual(Receipt.objects.count(),1)
        advance(order.pk,self.owner,'Delivered')
        self.assertEqual(BillingInvoice.objects.get(order=order).amount,Decimal('3.00'))
        self.assertEqual(Journal.objects.count(),2)

    def test_cancel_confirmed_cod_restores_stock(self):
        order=self.order();cancel(order.pk,self.buyer)
        self.product.refresh_from_db();self.assertEqual(self.product.stock,10)
        self.assertFalse(Receipt.objects.exists());self.assertFalse(BillingInvoice.objects.exists())

    def test_region_rate_authoritative_and_collection_free(self):
        ShopSettings.objects.create(shop=self.shop,delivery_fee=50,regional_delivery_fees={'Greater Accra':'20.00'})
        order=self.order();self.assertEqual(order.delivery_fee,20);self.assertEqual(order.total,120)
        self.assertEqual(self.order('collection','collection').total,100)
        self.address['region']='Ashanti';self.address['city']='Kumasi'
        self.assertEqual(self.order('ashanti').delivery_fee,50)

    def test_regional_rate_form_rejects_invalid_and_negative(self):
        for text in ['Atlantis=20','Ashanti=-1','Ashanti=NaN','Ashanti=1.001','Ashanti=2\nAshanti=3']:
            form=SettingsForm({'delivery_fee':'10','regional_rates':text})
            self.assertFalse(form.is_valid(),text)
        form=SettingsForm({'delivery_fee':'10','regional_rates':'Greater Accra=20\nAshanti=35'},instance=ShopSettings(shop=self.shop))
        self.assertTrue(form.is_valid(),form.errors);self.assertEqual(form.save().regional_delivery_fees['Ashanti'],'35.00')

    def test_all_regions_and_manual_town(self):
        self.assertEqual(len(REGIONS),16)
        for region in REGIONS:
            form=DeliveryAddressForm({**self.address,'region':region,'city':'My village'})
            self.assertTrue(form.is_valid(),form.errors)
        form=DeliveryAddressForm({**self.address,'region':'Ashanti'})
        self.assertFalse(form.is_valid());self.assertIn('city',form.errors)
        form=DeliveryAddressForm({**self.address,'region':'Fake region'})
        self.assertFalse(form.is_valid())

    def test_collection_needs_contact_but_not_street(self):
        data={**self.address,'region':'','city':'','street':'','fulfilment_1':'collection'}
        self.assertTrue(DeliveryAddressForm(data).is_valid())
        data['phone']='abc';self.assertFalse(DeliveryAddressForm(data).is_valid())

    def test_checkout_http_structured_and_bad_address_preserves_bag(self):
        self.client.force_login(self.buyer)
        session=self.client.session;session['cart']={str(self.product.pk):1};session.save()
        response=self.client.get('/bag/');self.assertContains(response,'Use my location');self.assertContains(response,'Cash on Delivery')
        bad=self.client.post('/bag/',{**self.address,'phone':'bad'})
        self.assertContains(bad,'Enter a valid contact');self.assertFalse(Order.objects.exists());self.assertTrue(self.client.session['cart'])
        response=self.client.post('/bag/',{**self.address,'fulfilment_'+str(self.shop.pk):'delivery'})
        self.assertRedirects(response,'/orders/');order=Order.objects.get()
        self.assertTrue(order.cash_on_delivery);self.assertIn('12 Market Road',order.address)
        self.assertEqual(order.delivery_address['recipient'],'Customer Name')
        self.assertContains(self.client.get('/orders/'),'Cash due on arrival')

    def test_support_cannot_collect_cash(self):
        from .models import StaffMembership
        order=self.order();advance(order.pk,self.owner,'Preparing');advance(order.pk,self.owner,'Dispatched','TRACK')
        StaffMembership.objects.create(shop=self.shop,user=self.buyer,role='support')
        self.client.force_login(self.buyer)
        self.assertEqual(self.client.post('/seller/orders/'+str(order.pk)+'/',{'status':'Paid','receipt_reference':'FAKE'}).status_code,403)
        self.assertFalse(Receipt.objects.exists())

    def test_seller_cash_actions_render(self):
        order=self.order();self.client.force_login(self.owner)
        self.assertContains(self.client.get('/seller/'),'Start preparing')
        advance(order.pk,self.owner,'Preparing');advance(order.pk,self.owner,'Dispatched','TRACK')
        self.assertContains(self.client.get('/seller/'),'Confirm cash collected')
        confirm_payment(order.pk,self.owner,'CASH');self.assertContains(self.client.get('/seller/'),'Mark delivered')

    def test_unpaid_return_restock_without_refund_or_commission(self):
        from .order_actions import request_return,decide_return
        order=self.order();advance(order.pk,self.owner,'Preparing');advance(order.pk,self.owner,'Dispatched','TRACK')
        request=request_return(order.pk,self.buyer,'Unable to accept parcel')
        with self.assertRaises(ValueError):decide_return(request.pk,self.owner,'Returned unpaid','Goods back','RETURN',False)
        decide_return(request.pk,self.owner,'Returned unpaid','Goods back','RETURN',True)
        self.product.refresh_from_db();order.refresh_from_db()
        self.assertEqual(self.product.stock,10);self.assertEqual(order.status,'Cancelled')
        self.assertFalse(Receipt.objects.exists());self.assertFalse(Journal.objects.exists());self.assertFalse(BillingInvoice.objects.exists())
        with self.assertRaises(ValueError):decide_return(request.pk,self.owner,'Returned unpaid','Replay','RETURN',True)

    def test_mix_cod_and_prepaid_and_checkout_idempotency(self):
        owner=get_user_model().objects.create_user('second-merchant')
        second=Shop.objects.create(owner=owner,name='Second',slug='second',active=True)
        product=Product.objects.create(shop=second,name='Second parcel',price=50,stock=5,description='Test',category='Fashion')
        bank=PaymentMethod.objects.create(shop=second,kind='bank',label='Bank transfer',instructions='Bank')
        args=(self.buyer,{str(self.product.pk):1,str(product.pk):2},'Customer address',{str(second.pk):bank.pk},'mixed')
        orders=checkout(*args);replayed=checkout(*args)
        self.assertEqual([o.pk for o in orders],[o.pk for o in replayed]);self.assertEqual(Order.objects.count(),2)
        self.assertEqual([o.status for o in orders],['Confirmed','Awaiting payment'])
        self.assertFalse(Receipt.objects.exists())

    def test_customer_cannot_forge_cod_cash_receipt(self):
        order=self.order();self.client.force_login(self.buyer)
        self.client.post('/orders/'+str(order.pk)+'/reference/',{'reference':'CASH'})
        order.refresh_from_db();self.assertEqual(order.payment_reference,'');self.assertFalse(Receipt.objects.exists())
