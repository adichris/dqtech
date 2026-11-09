from decimal import Decimal
from django.test import TestCase,override_settings
from django.contrib.auth import get_user_model
from .models import Shop,Product,PaymentMethod,ShopSettings,Order,Review,ListingReport
from .forms import ProductForm
from .services import checkout

@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class SearchAndBasketTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        U=get_user_model();cls.owner=U.objects.create_user('search-owner',password='password-123');cls.buyer=U.objects.create_user('search-buyer',password='password-123')
        cls.shop=Shop.objects.create(owner=cls.owner,name='Local Store',slug='local',active=True,country='GH',currency='GHS')
        cls.product=Product.objects.create(shop=cls.shop,name='Canvas Tote',description='Everyday cotton',price=100,stock=10,category='Fashion')
        cls.other=Product.objects.create(shop=cls.shop,name='Desk Lamp',description='For your home',price=200,stock=0,category='Home & Living')
        cls.method=PaymentMethod.objects.create(shop=cls.shop,kind='collection',label='Collect',instructions='Collect here')
    def add(self,quantity=1):
        session=self.client.session;session['cart']={str(self.product.pk):quantity};session.save()
    def test_search_page(self):
        r=self.client.get('/search/');self.assertEqual(r.status_code,200);self.assertContains(r,'Refine your finds');self.assertEqual(r.context['result_count'],2)
    def test_keyword_filter(self):
        r=self.client.get('/search/?q=canvas');self.assertEqual(r.context['result_count'],1);self.assertEqual(list(r.context['products'])[0].pk,self.product.pk)
    def test_keyword_tokens(self):self.assertEqual(self.client.get('/search/?q=canvas+cotton').context['result_count'],1)
    def test_category_filter(self):self.assertEqual(self.client.get('/search/?category=Fashion').context['result_count'],1)
    def test_price_requires_currency(self):
        r=self.client.get('/search/?max_price=150');self.assertTrue(r.context['form'].errors);self.assertEqual(r.context['result_count'],0)
    def test_price_range(self):self.assertEqual(self.client.get('/search/?max_price=150&currency=GHS').context['result_count'],1)
    def test_country_supplies_currency(self):self.assertEqual(self.client.get('/search/?country=GH&max_price=150').context['result_count'],1)
    def test_country_currency_mismatch(self):self.assertTrue(self.client.get('/search/?country=GH&currency=USD').context['form'].errors)
    def test_reversed_prices(self):self.assertTrue(self.client.get('/search/?country=GH&min_price=200&max_price=100').context['form'].errors)
    def test_in_stock_filter(self):self.assertEqual(self.client.get('/search/?in_stock=on').context['result_count'],1)
    def test_verified_filter(self):
        self.assertEqual(self.client.get('/search/?verified=on').context['result_count'],0);self.shop.verified=True;self.shop.save();self.assertEqual(self.client.get('/search/?verified=on').context['result_count'],2)
    def test_rating_filter(self):
        Review.objects.create(product=self.product.oscar_product,user=self.buyer,score=5,title='Useful',body='My find',status=Review.APPROVED)
        self.assertEqual(self.client.get('/search/?rating=4').context['result_count'],1)
    def test_classifieds_filter(self):
        self.product.classified=True;self.product.save();self.assertEqual(self.client.get('/search/?listing=classifieds').context['result_count'],1)
    def test_pagination_and_query_preservation(self):
        for n in range(15):Product.objects.create(shop=self.shop,name='Canvas item '+str(n),description='Cotton',price=10,stock=1,category='Fashion')
        r=self.client.get('/search/?q=canvas&category=Fashion');self.assertEqual(len(r.context['products']),12);self.assertIn('q=canvas',r.context['next_url']);self.assertIn('category=Fashion',r.context['next_url'])
    def test_search_html_fragment(self):
        r=self.client.get('/search/?q=canvas',HTTP_HX_REQUEST='true');self.assertContains(r,'id="search-page"');self.assertNotContains(r,'<!doctype html>')
    def test_hidden_products_excluded(self):
        self.product.active=False;self.product.save();self.assertEqual(self.client.get('/search/?q=canvas').context['result_count'],0)
    def test_quantity_update(self):
        self.add();self.client.post('/bag/quantity/'+str(self.product.pk)+'/',{'quantity':3});self.assertEqual(self.client.session['cart'][str(self.product.pk)],3)
    def test_invalid_quantity_does_not_change_cart(self):
        self.add();r=self.client.post('/bag/quantity/'+str(self.product.pk)+'/',{'quantity':-1},HTTP_HX_REQUEST='true');self.assertEqual(r.status_code,422);self.assertEqual(self.client.session['cart'][str(self.product.pk)],1)
    def test_quantity_above_stock_rejected(self):
        self.add();r=self.client.post('/bag/quantity/'+str(self.product.pk)+'/',{'quantity':99},HTTP_HX_REQUEST='true');self.assertEqual(r.status_code,422)
    def test_collection_removes_delivery_fee(self):
        ShopSettings.objects.create(shop=self.shop,delivery_fee=25,collection_available=True,collection_address='Campus gate')
        o=checkout(self.buyer,{str(self.product.pk):1},'Collect tomorrow',{str(self.shop.pk):self.method.pk},'collect',fulfilments={str(self.shop.pk):'collection'})[0]
        self.assertEqual(o.delivery_fee,0);self.assertEqual(o.total,100);self.assertEqual(o.fulfilment,'collection');self.assertIn('Campus gate',o.address)
    def test_disabled_collection_rejected(self):
        ShopSettings.objects.create(shop=self.shop,delivery_fee=25,collection_available=False)
        with self.assertRaises(ValueError):checkout(self.buyer,{str(self.product.pk):1},'Collect tomorrow',{str(self.shop.pk):self.method.pk},'collect',fulfilments={str(self.shop.pk):'collection'})
        self.assertEqual(Order.objects.count(),0)
    def test_remove_fragment_updates_basket(self):
        self.add();r=self.client.post('/bag/remove/'+str(self.product.pk)+'/',HTTP_HX_REQUEST='true');self.assertEqual(r.status_code,200);self.assertContains(r,'Your next favourite is out there.');self.assertNotContains(r,'<!doctype html>')
    def test_report_is_stored_once(self):
        self.client.force_login(self.buyer)
        for _ in range(2):self.client.post('/product/'+str(self.product.pk)+'/report/',{'reason':'Inaccurate listing','notes':'Please review'})
        self.assertEqual(ListingReport.objects.count(),1)
    def test_buyer_quantity_is_respected(self):
        self.client.post('/bag/add/'+str(self.product.pk)+'/',{'quantity':3});self.assertEqual(self.client.session['cart'][str(self.product.pk)],3)
    def test_buy_now_redirect(self):
        r=self.client.post('/bag/add/'+str(self.product.pk)+'/',{'quantity':1,'action':'buy_now'},HTTP_HX_REQUEST='true');self.assertEqual(r.headers['HX-Redirect'],'/bag/')
    def test_gallery_rejects_insecure_urls(self):
        f=ProductForm({'name':'Sample','description':'Good find','category':'Fashion','price':10,'stock':1,'gallery_links':'javascript:alert(1)'})
        self.assertFalse(f.is_valid());self.assertIn('gallery_links',f.errors)
