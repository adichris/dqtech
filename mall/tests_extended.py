import json,hmac,hashlib
from decimal import Decimal
from unittest.mock import patch
from cryptography.fernet import Fernet
from django.test import TestCase,override_settings
from django.contrib.auth import get_user_model
from django.db.models import Sum
from .models import *
from .services import checkout
from .order_actions import confirm_payment,advance,cancel,request_return,decide_return
from .gateway_services import reconcile
from .gateway_crypto import encrypt_secret

@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class DiscoveryAndCommerceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        U=get_user_model()
        cls.buyer=U.objects.create_user('shopper',email='buyer@example.test',password='test-password-123')
        cls.owner=U.objects.create_user('merchant',password='test-password-123')
        cls.other=U.objects.create_user('outsider',password='test-password-123')
        cls.shop=Shop.objects.create(owner=cls.owner,name='Sample Store',slug='sample',active=True)
        cls.product=Product.objects.create(shop=cls.shop,name='Canvas Tote',description='A cotton bag',price='100.00',stock=10,category='Fashion')
        cls.related=Product.objects.create(shop=cls.shop,name='Linen Shirt',description='Another find',price='150.00',stock=5,category='Fashion')
        cls.method=PaymentMethod.objects.create(shop=cls.shop,kind='collection',label='Collect',instructions='Collect in Accra')
    def order(self):
        return checkout(self.buyer,{str(self.product.pk):1},'Accra',{str(self.shop.pk):self.method.pk},'test-checkout')[0]
    def delivered(self):
        o=self.order();confirm_payment(o.pk,self.owner,'receipt-1');advance(o.pk,self.owner,'Preparing');advance(o.pk,self.owner,'Dispatched','Courier 123');advance(o.pk,self.owner,'Delivered');o.refresh_from_db();return o
    def test_system_name_from_settings(self):
        with override_settings(SYSTEM_NAME='My Configured Mall'):
            self.assertContains(self.client.get('/'),'<title>My Configured Mall')
    def test_autocomplete_returns_fragment_and_products(self):
        response=self.client.get('/search/suggestions/?q=canvas')
        self.assertEqual(response.status_code,200);self.assertContains(response,'Canvas Tote');self.assertNotContains(response,'<!doctype html>')
    def test_autocomplete_short_query_is_empty(self):self.assertEqual(self.client.get('/search/suggestions/?q=c').content.strip(),b'')
    def test_autocomplete_excludes_inactive_stores(self):
        self.shop.active=False;self.shop.save();self.assertNotContains(self.client.get('/search/suggestions/?q=canvas'),'Canvas Tote')
    def test_quick_view_fragment(self):
        response=self.client.get('/product/'+str(self.product.pk)+'/quick-view/');self.assertContains(response,'Canvas Tote');self.assertNotContains(response,'<!doctype html>')
    def test_wishlist_add_remove(self):
        self.client.force_login(self.buyer);url='/product/'+str(self.product.pk)+'/save/'
        self.client.post(url);self.assertEqual(get_model('wishlists','Line').objects.filter(wishlist__owner=self.buyer).count(),1)
        self.client.post(url);self.assertEqual(get_model('wishlists','Line').objects.filter(wishlist__owner=self.buyer).count(),0)
    def test_wishlists_are_private(self):
        __import__('mall.favourites',fromlist=['save_find']).save_find(self.other,self.product);self.client.force_login(self.buyer)
        self.assertNotContains(self.client.get('/wishlist/'),'Canvas Tote')
    def test_anonymous_save_redirects_htmx(self):
        response=self.client.post('/product/'+str(self.product.pk)+'/save/',HTTP_HX_REQUEST='true');self.assertIn('/login/',response.headers['HX-Redirect'])
    def test_review_requires_delivery(self):
        self.client.force_login(self.buyer);self.client.post('/product/'+str(self.product.pk)+'/review/',{'rating':5,'title':'Great','body':'Loved it'})
        self.assertEqual(Review.objects.count(),0)
    def test_verified_review(self):
        self.delivered();self.client.force_login(self.buyer);self.client.post('/product/'+str(self.product.pk)+'/review/',{'rating':5,'title':'Great tote','body':'Useful every day'})
        review=Review.objects.get();self.assertTrue(get_model('order','Line').objects.filter(product=review.product,order__user=review.user,order__status='Delivered').exists());self.assertEqual(review.score,5)
    def test_review_updates_single_record(self):
        self.delivered();self.client.force_login(self.buyer);url='/product/'+str(self.product.pk)+'/review/'
        for rating in [4,5]:self.client.post(url,{'rating':rating,'title':'Great tote','body':'Useful every day'})
        self.assertEqual(Review.objects.count(),1);self.assertEqual(Review.objects.get().score,5)
    def test_invalid_rating_rejected_with_422(self):
        self.delivered();self.client.force_login(self.buyer)
        response=self.client.post('/product/'+str(self.product.pk)+'/review/',{'rating':9,'title':'Bad score','body':'Example'},HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code,422);self.assertEqual(Review.objects.count(),0)
    def test_hidden_review_excluded_from_rating(self):
        Review.objects.create(product=self.product.oscar_product,user=self.buyer,score=5,title='Hidden',body='Hidden',status=Review.REJECTED)
        response=self.client.get('/product/'+str(self.product.pk)+'/');self.assertEqual(response.context['product'].rating_count,0)
    def test_suggestions_exclude_current_product(self):
        response=self.client.get('/product/'+str(self.product.pk)+'/');ids=[p.pk for p in response.context['products']]
        self.assertIn(self.related.pk,ids);self.assertNotIn(self.product.pk,ids)
    def test_price_sort(self):
        prices=[p.price for p in self.client.get('/?sort=price_low').context['products']];self.assertEqual(prices,sorted(prices))
    def test_inline_add_updates_bag_fragment(self):
        response=self.client.post('/bag/add/'+str(self.product.pk)+'/',HTTP_HX_REQUEST='true');self.assertEqual(response.status_code,200);self.assertContains(response,'hx-partial')
        self.assertEqual(self.client.session['cart'][str(self.product.pk)],1)
    def test_inline_stock_error_is_422(self):
        self.product.stock=0;self.product.save();response=self.client.post('/bag/add/'+str(self.product.pk)+'/',HTTP_HX_REQUEST='true');self.assertEqual(response.status_code,422)
    def test_oscar_order_is_created(self):
        o=self.order();self.assertIsNotNone(o.oscar_order_id);self.assertEqual(o.oscar_order.total_incl_tax,o.total);self.assertEqual(o.oscar_order.lines.count(),1)
    def test_cancel_restores_stock_once(self):
        o=self.order();cancel(o.pk,self.buyer);cancel(o.pk,self.buyer);self.product.refresh_from_db();self.assertEqual(self.product.stock,10)
        o.refresh_from_db();self.assertEqual(o.oscar_order.status,'Cancelled')
    def test_paid_order_cannot_cancel(self):
        o=self.order();confirm_payment(o.pk,self.owner,'receipt-1')
        with self.assertRaises(ValueError):cancel(o.pk,self.buyer)
    def test_receipt_posts_balanced_journal_once(self):
        o=self.order();confirm_payment(o.pk,self.owner,'receipt-1');confirm_payment(o.pk,self.owner,'receipt-1')
        self.assertEqual(Receipt.objects.count(),1);j=Journal.objects.get(key='receipt:'+str(o.pk));sums=j.postings.aggregate(d=Sum('debit'),c=Sum('credit'));self.assertEqual(sums['d'],sums['c'])
        self.assertEqual(o.oscar_order.sources.count(),1)
    def test_refund_restock_and_journal(self):
        o=self.delivered();rr=request_return(o.pk,self.buyer,'Wrong size');decide_return(rr.pk,self.owner,'Refund confirmed','Returned','refund-123',True)
        self.product.refresh_from_db();o.refresh_from_db();self.assertEqual(self.product.stock,10);self.assertEqual(o.status,'Refunded')
        self.assertTrue(Journal.objects.filter(key='refund:'+str(o.pk)).exists())
    def test_refund_requires_reference(self):
        o=self.delivered();rr=request_return(o.pk,self.buyer,'Wrong size')
        with self.assertRaises(ValueError):decide_return(rr.pk,self.owner,'Refund confirmed','Returned','',True)
    def test_invoice_is_private(self):
        o=self.order();self.client.force_login(self.other);self.assertEqual(self.client.get('/orders/'+str(o.pk)+'/invoice/').status_code,403)
    def test_staff_only_oscar_dashboard(self):
        self.client.force_login(self.owner);self.assertEqual(self.client.get('/engine/dashboard/').status_code,403)
    def test_delivery_fee_is_snapshotted(self):
        ShopSettings.objects.create(shop=self.shop,delivery_fee=15)
        o=self.order();self.assertEqual(o.total,Decimal('115.00'));self.assertEqual(o.delivery_fee,Decimal('15.00'))
    def test_no_cross_currency_total(self):
        U=get_user_model();owner=U.objects.create_user('dollar-owner');shop=Shop.objects.create(owner=owner,name='Dollar shop',slug='dollar',active=True,country='US',currency='USD')
        product=Product.objects.create(shop=shop,name='US find',price=50,stock=2,description='Other market',category='Home & Living')
        session=self.client.session;session['cart']={str(self.product.pk):1,str(product.pk):1};session.save()
        totals=dict(self.client.get('/bag/').context['totals']);self.assertEqual(totals,{'GHS':Decimal('100.00'),'USD':Decimal('50.00')})
    def test_online_gateway_cannot_be_created_as_manual(self):
        self.client.force_login(self.owner);self.client.post('/seller/payments/',{'kind':'online','label':'Fake','instructions':'Fake','active':True})
        self.assertFalse(PaymentMethod.objects.filter(kind='online').exists())
    def test_new_shops_need_activation(self):
        shop=Shop.objects.create(owner=self.other,name='Pending',slug='pending');self.assertFalse(shop.active)

    def test_platform_staff_can_open_oscar_dashboard(self):
        self.owner.is_staff=True;self.owner.save();self.client.force_login(self.owner)
        self.assertEqual(self.client.get('/engine/dashboard/').status_code,200)
