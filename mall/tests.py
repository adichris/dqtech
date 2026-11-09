from django.test import TestCase,Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from .models import *
from .services import checkout
class CommerceTests(TestCase):
    def setUp(self):
        U=get_user_model();self.buyer=U.objects.create_user('buyer',password='long-test-password');self.owner=U.objects.create_user('owner',password='long-test-password');self.other=U.objects.create_user('other',password='long-test-password')
        self.shop=Shop.objects.create(owner=self.owner,name='One',slug='one',active=True)
        self.shop2=Shop.objects.create(owner=self.other,name='Two',slug='two',active=True,created=timezone.now()-timedelta(days=120))
        self.p=Product.objects.create(shop=self.shop,name='Item',price=100,stock=3,description='Test',category='Fashion')
        self.p2=Product.objects.create(shop=self.shop2,name='Other',price=200,stock=4,description='Test',category='Fashion')
        self.m=PaymentMethod.objects.create(shop=self.shop,kind='collection',label='Collect',instructions='Collect here')
        self.m2=PaymentMethod.objects.create(shop=self.shop2,kind='bank',label='Bank',instructions='Public instructions')
    def test_split_trial_and_commission(self):
        orders=checkout(self.buyer,{str(self.p.pk):2,str(self.p2.pk):1},'Accra',{str(self.shop.pk):self.m.pk,str(self.shop2.pk):self.m2.pk},'a')
        self.assertEqual(len(orders),2);self.assertEqual(orders[0].commission,0);self.assertEqual(orders[1].commission,Decimal('6.00'))
        self.p.refresh_from_db();self.assertEqual(self.p.stock,1)
    def test_atomic_failure(self):
        with self.assertRaises(ValueError):checkout(self.buyer,{str(self.p.pk):1,str(self.p2.pk):99},'Accra',{str(self.shop.pk):self.m.pk,str(self.shop2.pk):self.m2.pk},'a')
        self.assertEqual(Order.objects.count(),0);self.p.refresh_from_db();self.assertEqual(self.p.stock,3)
    def test_method_must_belong_to_seller(self):
        with self.assertRaises(ValueError):checkout(self.buyer,{str(self.p.pk):1},'Accra',{str(self.shop.pk):self.m2.pk},'a')
    def test_replay_does_not_reduce_stock_twice(self):
        args=(self.buyer,{str(self.p.pk):1},'Accra',{str(self.shop.pk):self.m.pk},'a')
        checkout(*args);checkout(*args);self.assertEqual(Order.objects.count(),1);self.p.refresh_from_db();self.assertEqual(self.p.stock,2)
    def test_tenant_isolation(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get('/seller/products/'+str(self.p.pk)+'/').status_code,404)
        self.assertEqual(self.client.get('/operations/one/finance/').status_code,403)
    def test_support_cannot_access_finance_or_export(self):
        StaffMembership.objects.create(shop=self.shop,user=self.buyer,role='support')
        self.client.force_login(self.buyer)
        self.assertEqual(self.client.get('/operations/one/support/').status_code,200)
        self.assertEqual(self.client.get('/operations/one/finance/').status_code,403)
        self.assertEqual(self.client.get('/operations/one/export/').status_code,403)
        self.assertNotContains(self.client.get('/operations/one/overview/'),'Confirmed receipts')
    def test_reference_does_not_confirm_payment(self):
        o=checkout(self.buyer,{str(self.p.pk):1},'Accra',{str(self.shop.pk):self.m.pk},'a')[0]
        self.client.force_login(self.buyer);self.client.post('/orders/'+str(o.pk)+'/reference/',{'reference':'sent'})
        o.refresh_from_db();self.assertEqual(o.status,'Awaiting payment')
    def test_revoked_staff_has_no_access(self):
        StaffMembership.objects.create(shop=self.shop,user=self.buyer,role='finance',active=False)
        self.client.force_login(self.buyer);self.assertEqual(self.client.get('/operations/one/finance/').status_code,403)
    def test_csrf(self):
        client=Client(enforce_csrf_checks=True)
        self.assertEqual(client.post('/bag/add/'+str(self.p.pk)+'/').status_code,403)
    def test_classified_cannot_checkout(self):
        self.p.classified=True;self.p.save()
        with self.assertRaises(ValueError):checkout(self.buyer,{str(self.p.pk):1},'Accra',{str(self.shop.pk):self.m.pk},'a')
    def test_pages_render(self):
        self.client.force_login(self.owner)
        for url in ['/','/product/'+str(self.p.pk)+'/','/shops/one/','/bag/','/seller/','/seller/payments/','/seller/team/','/orders/','/operations/one/finance/','/operations/one/expenses/']:
            self.assertEqual(self.client.get(url).status_code,200,url)

    def test_search_returns_html_fragment(self):
        response=self.client.get('/?q=Item',HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code,200)
        self.assertNotContains(response,'<!doctype html>')
        self.assertContains(response,'Item')
        self.assertIn('HX-Request',response.headers['Vary'])
