from django.test import TestCase
from django.contrib.auth import get_user_model
from .models import BuyerAddress,Shop,Product,Order,ShopSettings
from .address_views import save_address

class AddressBookTests(TestCase):
    def setUp(self):
        users=get_user_model();self.buyer=users.objects.create_user('buyer');self.other=users.objects.create_user('other')
        self.data={'recipient':'Buyer Name','phone':'0241234567','country':'GH','region':'Greater Accra','city':'Accra','street':'12 Market Road','landmark':'Library','digital_address':'','instructions':'Call first'}
        self.client.force_login(self.buyer)
    def test_save_default_deduplicate_and_exclude_consent(self):
        first=save_address(self.buyer,{**self.data,'whatsapp_opt_in':True},'Home')
        self.assertTrue(first.is_default);self.assertNotIn('whatsapp_opt_in',first.data)
        self.assertEqual(save_address(self.buyer,self.data).pk,first.pk)
        second=save_address(self.buyer,{**self.data,'street':'Work Road'},'Work',True)
        first.refresh_from_db();self.assertFalse(first.is_default);self.assertTrue(second.is_default)
    def test_default_prefill_and_fresh_consent(self):
        address=save_address(self.buyer,self.data)
        response=self.client.get('/bag/')
        self.assertEqual(response.context['address_form'].initial['street'],'12 Market Road')
        self.assertFalse(response.context['address_form'].initial['whatsapp_opt_in'])
        self.assertEqual(response.context['selected_address'],address)
        response=self.client.get('/bag/?address=new');self.assertIsNone(response.context['selected_address'])
    def test_address_ownership_for_every_operation(self):
        address=save_address(self.other,self.data)
        for path in [f'/account/addresses/{address.pk}/edit/',f'/bag/?address={address.pk}']:
            self.assertEqual(self.client.get(path).status_code,404)
        for path in [f'/account/addresses/{address.pk}/edit/',f'/account/addresses/{address.pk}/default/',f'/account/addresses/{address.pk}/delete/']:
            self.assertEqual(self.client.post(path,self.data).status_code,404)
        self.assertNotContains(self.client.get('/account/addresses/'),'12 Market Road')
    def test_edit_delete_and_default_replacement(self):
        first=save_address(self.buyer,self.data)
        second=save_address(self.buyer,{**self.data,'street':'Work Road'},'Work')
        response=self.client.post(f'/account/addresses/{first.pk}/edit/',{**self.data,'street':'New Road','label':'New home'})
        self.assertRedirects(response,'/account/addresses/');first.refresh_from_db();self.assertEqual(first.data['street'],'New Road')
        self.assertEqual(self.client.get(f'/account/addresses/{first.pk}/delete/').status_code,405)
        self.client.post(f'/account/addresses/{first.pk}/delete/');second.refresh_from_db();self.assertTrue(second.is_default)
    def test_address_book_requires_complete_valid_address(self):
        response=self.client.post('/account/addresses/new/',{**self.data,'street':'','fulfilment_1':'collection','label':'Home'})
        self.assertEqual(response.status_code,200);self.assertFalse(BuyerAddress.objects.exists())
        self.assertContains(response,'This field is required')
        response=self.client.post('/account/addresses/new/',{**self.data,'label':'Campus'})
        self.assertRedirects(response,'/account/addresses/');self.assertEqual(BuyerAddress.objects.get().label,'Campus')
    def test_checkout_save_and_order_snapshot_survives_address_changes(self):
        shop=Shop.objects.create(owner=self.other,name='Store',slug='store',active=True)
        product=Product.objects.create(shop=shop,name='Item',description='Test',category='Fashion',price=100,stock=5)
        session=self.client.session;session['cart']={str(product.pk):1};session.save()
        response=self.client.post('/bag/',{**self.data,'save_address':'on','address_label':'Home'})
        self.assertRedirects(response,'/orders/');order=Order.objects.get();saved=BuyerAddress.objects.get()
        original=order.delivery_address.copy();save_address(self.buyer,{**self.data,'street':'Changed Road'},address=saved)
        self.client.post(f'/account/addresses/{saved.pk}/delete/')
        order.refresh_from_db();self.assertEqual(order.delivery_address,original);self.assertIn('12 Market Road',order.address)
    def test_selected_address_kept_after_checkout_validation_error(self):
        save_address(self.buyer,self.data)
        second=save_address(self.buyer,{**self.data,'street':'Work Road'},'Work')
        response=self.client.post('/bag/',{**self.data,'address_choice':second.pk,'phone':'bad'})
        self.assertEqual(response.context['selected_address'],second)
    def test_saved_default_uses_regional_fee_in_initial_summary(self):
        save_address(self.buyer,self.data)
        shop=Shop.objects.create(owner=self.other,name='Store',slug='store',active=True)
        ShopSettings.objects.create(shop=shop,delivery_fee=50,regional_delivery_fees={'Greater Accra':'20.00'})
        product=Product.objects.create(shop=shop,name='Item',description='Test',category='Fashion',price=100,stock=5)
        session=self.client.session;session['cart']={str(product.pk):1};session.save()
        group=self.client.get('/bag/').context['groups'][0]
        self.assertEqual(group['delivery_fee'],20);self.assertEqual(group['total'],120);self.assertEqual(group['base_delivery_fee'],50)
