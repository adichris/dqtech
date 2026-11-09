import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from .eligibility import own_gateway_eligibility
from .forms import ProductForm
from .gateway_crypto import encrypt_secret
from .gateway_services import begin, reconcile
from .models import (AuditEvent, BillingInvoice, GatewayConnection, Order, PaymentAttempt, PaymentMethod,
                     Product, Receipt, ReturnRequest, Shop, StaffMembership)
from .order_actions import advance, decide_return, request_return
from .security import client_ip
from .services import checkout, expire_unpaid_orders

PLATFORM_SECRET = 'sk_test_platform_secret_example'
FAST_HASH = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])


class Fixture(TestCase):
    def setUp(self):
        U = get_user_model()
        self.owner = U.objects.create_user('h-owner', email='owner@example.test', password='test-password-123')
        self.buyer = U.objects.create_user('h-buyer', email='buyer@example.test', password='test-password-123')
        self.shop = Shop.objects.create(owner=self.owner, name='Harden', slug='harden', active=True, verified=True)
        self.product = Product.objects.create(shop=self.shop, name='Basket', description='Woven', price='100.00', stock=50, category='Fashion')
        self.manual = PaymentMethod.objects.create(shop=self.shop, kind='momo', label='MoMo', instructions='Send to 024')
        self.n = 0

    def place(self, method=None, buyer=None, qty=1):
        self.n += 1
        method_id = (method or self.manual).pk
        return checkout(buyer or self.buyer, {str(self.product.pk): qty}, 'Accra', {str(self.shop.pk): method_id}, 'key-' + str(self.n))[0]

    def stock(self):
        return Product.objects.get(pk=self.product.pk).stock


@FAST_HASH
class StockHoldTests(Fixture):
    def test_open_unpaid_orders_are_capped_per_shop(self):
        for _ in range(3):
            self.place()
        with self.assertRaisesMessage(ValueError, 'too many unpaid orders'):
            self.place()

    @override_settings(MAX_OPEN_UNPAID_ORDERS=2, MAX_OPEN_UNPAID_ORDERS_PER_SHOP=5)
    def test_open_unpaid_orders_are_capped_in_total(self):
        self.place(); self.place()
        with self.assertRaisesMessage(ValueError, 'unpaid orders reserving stock'):
            self.place()

    def test_paid_orders_do_not_count_toward_cap(self):
        from .order_actions import confirm_payment
        for i in range(3):
            confirm_payment(self.place().pk, self.owner, 'receipt-%d' % i)
        self.place()  # no error

    def test_stale_unpaid_order_expires_and_releases_stock(self):
        order = self.place(qty=5)
        self.assertEqual(self.stock(), 45)
        self.assertEqual(expire_unpaid_orders(), [])  # still inside the hold window
        later = timezone.now() + timedelta(hours=49)
        self.assertEqual(expire_unpaid_orders(now=later), [order.pk])
        order.refresh_from_db()
        self.assertEqual(order.status, 'Cancelled')
        self.assertEqual(self.stock(), 50)
        event = AuditEvent.objects.filter(action__startswith='Order cancelled').latest('pk')
        self.assertIsNone(event.actor)

    def test_expiry_skips_cod_and_orders_with_buyer_reference(self):
        cod = self.place(method=PaymentMethod.objects.get(shop=self.shop, kind='cod'))
        referenced = self.place()
        referenced.payment_reference = 'MOMO-123'
        referenced.save(update_fields=['payment_reference'])
        self.assertEqual(expire_unpaid_orders(now=timezone.now() + timedelta(days=5)), [])
        cod.refresh_from_db(); referenced.refresh_from_db()
        self.assertEqual(cod.status, 'Confirmed')
        self.assertEqual(referenced.status, 'Awaiting payment')

    def test_seller_can_cancel_unpaid_order(self):
        order = self.place(qty=2)
        self.client.force_login(self.owner)
        self.client.post('/seller/orders/%d/' % order.pk, {'status': 'Cancelled', 'reason': 'Suspected fake order'})
        order.refresh_from_db()
        self.assertEqual(order.status, 'Cancelled')
        self.assertEqual(self.stock(), 50)
        self.assertEqual(order.tracking_events.first().note, 'Suspected fake order')

    def test_other_users_cannot_cancel_seller_orders(self):
        order = self.place()
        self.client.force_login(get_user_model().objects.create_user('stranger'))
        self.assertEqual(self.client.post('/seller/orders/%d/' % order.pk, {'status': 'Cancelled'}).status_code, 403)
        order.refresh_from_db()
        self.assertEqual(order.status, 'Awaiting payment')


@FAST_HASH
@override_settings(RATELIMIT_ENABLED=True, LOGIN_FAILURES_PER_ACCOUNT=3)
class RateLimitTests(Fixture):
    def setUp(self):
        super().setUp()
        cache.clear()

    def test_login_locks_after_repeated_failures(self):
        for _ in range(3):
            self.assertEqual(self.client.post('/login/', {'username': 'h-buyer', 'password': 'wrong'}).status_code, 200)
        response = self.client.post('/login/', {'username': 'h-buyer', 'password': 'test-password-123'})
        self.assertEqual(response.status_code, 429)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_successful_login_resets_counter(self):
        self.client.post('/login/', {'username': 'h-buyer', 'password': 'wrong'})
        self.client.post('/login/', {'username': 'h-buyer', 'password': 'test-password-123'})
        self.assertIn('_auth_user_id', self.client.session)

    def test_signup_is_rate_limited(self):
        for i in range(20):
            self.client.post('/signup/', {'username': ''})
        self.assertEqual(self.client.post('/signup/', {'username': ''}).status_code, 429)

    def test_autocomplete_is_rate_limited(self):
        from .security import hit
        for _ in range(300):
            hit('autocomplete:ip127.0.0.1', 300, 60)
        self.assertEqual(self.client.get('/search/suggestions/?q=ba').status_code, 429)

    def test_password_reset_email_limit_does_not_reveal_anything(self):
        for _ in range(5):
            response = self.client.post('/password-reset/', {'email': 'buyer@example.test'})
            self.assertRedirects(response, '/password-reset/done/', fetch_redirect_response=False)
        from django.core import mail
        self.assertEqual(len(mail.outbox), 3)

    def test_client_ip_trusts_only_configured_proxies(self):
        request = RequestFactory().get('/', REMOTE_ADDR='10.0.0.1', HTTP_X_FORWARDED_FOR='6.6.6.6, 41.0.0.9')
        self.assertEqual(client_ip(request), '10.0.0.1')
        with override_settings(TRUSTED_PROXY_COUNT=1):
            self.assertEqual(client_ip(request), '41.0.0.9')


@FAST_HASH
class LoginRedirectAndDashboardTests(Fixture):
    def login(self, username):
        return self.client.post('/login/', {'username': username, 'password': 'test-password-123'})

    def test_buyer_lands_on_the_mall(self):
        self.assertRedirects(self.login('h-buyer'), '/', fetch_redirect_response=False)

    def test_owner_lands_on_seller_centre(self):
        self.assertRedirects(self.login('h-owner'), '/seller/', fetch_redirect_response=False)

    def test_staff_reach_workspaces(self):
        staff = get_user_model().objects.create_user('h-staff', password='test-password-123')
        StaffMembership.objects.create(shop=self.shop, user=staff, role='support')
        self.assertRedirects(self.login('h-staff'), '/workspaces/', fetch_redirect_response=False)
        self.assertRedirects(self.client.get('/seller/'), '/workspaces/', fetch_redirect_response=False)

    def test_next_parameter_still_wins(self):
        response = self.client.post('/login/?next=/wishlist/', {'username': 'h-buyer', 'password': 'test-password-123'})
        self.assertRedirects(response, '/wishlist/', fetch_redirect_response=False)

    def test_seller_dashboard_paginates_orders(self):
        from .order_actions import confirm_payment
        for i in range(27):
            confirm_payment(self.place().pk, self.owner, 'r-%d' % i)
        self.client.force_login(self.owner)
        response = self.client.get('/seller/')
        self.assertEqual(len(response.context['orders']), 25)
        self.assertEqual(response.context['order_count'], 27)
        self.assertContains(response, 'Page 1 of 2')

    def test_finance_csv_reports_store_currency(self):
        self.shop.currency = 'NGN'; self.shop.country = 'NG'; self.shop.save()
        Product.objects.get(pk=self.product.pk).save()  # resync the stock record currency
        self.place()
        self.client.force_login(self.owner)
        rows = self.client.get('/operations/harden/export/').content.decode().splitlines()
        self.assertEqual(rows[0], 'Type,ID,Date,Currency,Amount,Commission,Status')
        self.assertIn(',NGN,', rows[1])

    def test_security_headers(self):
        response = self.client.get('/')
        self.assertIn("frame-ancestors 'none'", response['Content-Security-Policy'])
        self.assertIn("object-src 'none'", response['Content-Security-Policy'])
        self.assertIn('camera=()', response['Permissions-Policy'])


class ImageLinkTests(Fixture):
    def form(self, **extra):
        data = {'name': 'Lamp', 'description': 'Brass', 'category': 'Fashion', 'price': '10', 'stock': '1', 'active': 'on', 'image': '', 'gallery_links': ''}
        data.update(extra)
        return ProductForm(data)

    def test_plain_http_image_is_rejected(self):
        form = self.form(image='http://tracker.example/pixel.gif')
        self.assertFalse(form.is_valid())
        self.assertIn('image', form.errors)

    def test_https_image_is_accepted(self):
        self.assertTrue(self.form(image='https://cdn.example/lamp.jpg').is_valid())

    @override_settings(PRODUCT_IMAGE_HOSTS=['res.cloudinary.com'])
    def test_host_allow_list(self):
        self.assertFalse(self.form(image='https://cdn.example/lamp.jpg').is_valid())
        self.assertFalse(self.form(gallery_links='https://evil.example/a.jpg').is_valid())
        self.assertTrue(self.form(image='https://res.cloudinary.com/demo/lamp.jpg').is_valid())

    def test_existing_insecure_links_are_not_rendered(self):
        Product.objects.filter(pk=self.product.pk).update(image='http://tracker.example/p.gif', gallery=['http://x.example/a.jpg', 'https://ok.example/b.jpg'])
        product = Product.objects.get(pk=self.product.pk)
        self.assertEqual(product.image_url, 'https://ok.example/b.jpg')
        self.assertEqual(product.gallery_images, ['https://ok.example/b.jpg'])


@FAST_HASH
@override_settings(PLATFORM_PAYSTACK_SECRET=PLATFORM_SECRET, PLATFORM_PAYSTACK_CURRENCIES=['GHS'], PUBLIC_BASE_URL='https://mall.example')
class MallPayTests(Fixture):
    def setUp(self):
        super().setUp()
        cache.clear()
        # Past the commission-free trial, so the 3% commission applies.
        Shop.objects.filter(pk=self.shop.pk).update(created=timezone.now() - timedelta(days=400))
        self.shop.refresh_from_db()
        self.gateway = GatewayConnection.objects.create(shop=self.shop, mode='platform', subaccount_code='ACCT_seller1', active=True)
        self.online = PaymentMethod.objects.create(shop=self.shop, kind='online', label='Pay online (Mall Pay)', instructions='Online')

    def paid_order(self):
        order = self.place(method=self.online)
        with patch('mall.gateway_services.Paystack.initialize', return_value='https://checkout.paystack.com/abc') as init:
            begin(order.pk, self.buyer)
        attempt = PaymentAttempt.objects.get(order=order)
        data = {'id': 99, 'status': 'success', 'reference': attempt.reference, 'amount': 10000, 'currency': 'GHS'}
        with patch('mall.gateway_services.Paystack.verify', return_value=data):
            reconcile(attempt.pk)
        order.refresh_from_db()
        return order, attempt, init

    def test_checkout_splits_payment_to_seller_subaccount(self):
        order, attempt, init = self.paid_order()
        kwargs = init.call_args.kwargs
        self.assertEqual(kwargs['subaccount'], 'ACCT_seller1')
        self.assertEqual(kwargs['platform_charge'], Decimal('3.00'))
        self.assertTrue(attempt.platform)
        self.assertEqual(order.status, 'Paid')
        self.assertEqual(Receipt.objects.get(order=order).method, 'mall_pay')

    def test_paystack_payload_contains_split(self):
        from .paystack import Paystack
        with patch.object(Paystack, 'call', return_value={'authorization_url': 'https://checkout.paystack.com/x'}) as call:
            Paystack('sk').initialize('a@b.test', Decimal('100.00'), 'GHS', 'ref', 'https://cb', subaccount='ACCT_1', platform_charge=Decimal('3.00'))
        payload = call.call_args.args[2]
        self.assertEqual(payload['subaccount'], 'ACCT_1')
        self.assertEqual(payload['transaction_charge'], 300)
        self.assertEqual(payload['bearer'], 'subaccount')

    def test_commission_is_collected_not_billed(self):
        order, _, _ = self.paid_order()
        invoice = BillingInvoice.objects.get(order=order)
        self.assertEqual((invoice.state, invoice.amount), ('Collected', Decimal('3.00')))
        advance(order.pk, self.owner, 'Preparing'); advance(order.pk, self.owner, 'Dispatched', 'Rider 7'); advance(order.pk, self.owner, 'Delivered')
        self.assertEqual(BillingInvoice.objects.filter(order=order).count(), 1)
        self.assertFalse(BillingInvoice.objects.filter(shop=self.shop, state='Due').exists())

    def test_refund_marks_commission_credit_due(self):
        order, _, _ = self.paid_order()
        request_return(order.pk, self.buyer, 'Damaged')
        decide_return(ReturnRequest.objects.get(order=order).pk, self.owner, 'Refund confirmed', 'Sorry', 'RF-1', restock=True)
        self.assertEqual(BillingInvoice.objects.get(order=order).state, 'Credit due')

    def test_attempt_keeps_platform_secret_after_switch_to_own(self):
        order = self.place(method=self.online)
        with patch('mall.gateway_services.Paystack.initialize', return_value='https://checkout.paystack.com/abc'):
            begin(order.pk, self.buyer)
        attempt = PaymentAttempt.objects.get(order=order)
        GatewayConnection.objects.filter(pk=self.gateway.pk).update(mode='own')
        data = {'id': 5, 'status': 'success', 'reference': attempt.reference, 'amount': 10000, 'currency': 'GHS'}
        with patch('mall.gateway_services.Paystack.__init__', return_value=None) as init, patch('mall.gateway_services.Paystack.verify', return_value=data):
            reconcile(attempt.pk)
        self.assertEqual(init.call_args.args[0], PLATFORM_SECRET)

    def test_platform_webhook_verifies_signature(self):
        order = self.place(method=self.online)
        with patch('mall.gateway_services.Paystack.initialize', return_value='https://checkout.paystack.com/abc'):
            begin(order.pk, self.buyer)
        attempt = PaymentAttempt.objects.get(order=order)
        body = json.dumps({'event': 'charge.success', 'data': {'reference': attempt.reference}}).encode()
        bad = self.client.post('/webhooks/paystack/platform/', body, content_type='application/json', HTTP_X_PAYSTACK_SIGNATURE='0' * 128)
        self.assertEqual(bad.status_code, 401)
        signature = hmac.new(PLATFORM_SECRET.encode(), body, hashlib.sha512).hexdigest()
        data = {'id': 7, 'status': 'success', 'reference': attempt.reference, 'amount': 10000, 'currency': 'GHS'}
        with patch('mall.gateway_services.Paystack.verify', return_value=data):
            good = self.client.post('/webhooks/paystack/platform/', body, content_type='application/json', HTTP_X_PAYSTACK_SIGNATURE=signature)
        self.assertEqual(good.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, 'Paid')

    def test_seller_sets_up_mall_pay(self):
        self.gateway.delete(); self.online.delete()
        banks = [{'code': 'MTN', 'name': 'MTN Mobile Money', 'type': 'mobile_money'}]
        self.client.force_login(self.owner)
        with patch('mall.paystack.Paystack.banks', return_value=banks), \
             patch('mall.paystack.Paystack.save_subaccount', return_value={'subaccount_code': 'ACCT_new', 'account_name': 'HARDEN LTD'}) as save:
            self.assertContains(self.client.get('/seller/mall-pay/'), 'MTN Mobile Money')
            response = self.client.post('/seller/mall-pay/', {'business_name': 'Harden', 'settlement_bank': 'MTN', 'account_number': '0241234567', 'active': 'on'})
        self.assertRedirects(response, '/seller/mall-pay/', fetch_redirect_response=False)
        self.assertEqual(save.call_args.args[:4], ('', 'Harden', 'MTN', '0241234567'))
        connection = GatewayConnection.objects.get(shop=self.shop)
        self.assertEqual((connection.mode, connection.subaccount_code, connection.account_last4), ('platform', 'ACCT_new', '4567'))
        self.assertTrue(PaymentMethod.objects.get(shop=self.shop, kind='online').active)

    @override_settings(PLATFORM_PAYSTACK_SECRET='')
    def test_mall_pay_unavailable_without_platform_key(self):
        self.client.force_login(self.owner)
        self.assertContains(self.client.get('/seller/mall-pay/'), 'not available')


@FAST_HASH
@override_settings(OWN_GATEWAY_MIN_DELIVERED_ORDERS=2)
class OwnGatewayEligibilityTests(Fixture):
    def setUp(self):
        super().setUp()
        self.key = Fernet.generate_key().decode()
        self.override = override_settings(GATEWAY_ENCRYPTION_KEY=self.key)
        self.override.enable(); self.addCleanup(self.override.disable)
        self.client.force_login(self.owner)

    def post_key(self):
        return self.client.post('/seller/gateway/', {'secret': 'sk_test_' + 'x' * 20, 'test_mode': 'on', 'active': 'on'})

    def deliver(self, count):
        from .order_actions import confirm_payment
        for i in range(count):
            order = self.place()
            confirm_payment(order.pk, self.owner, 'el-%d' % i)
            advance(order.pk, self.owner, 'Preparing'); advance(order.pk, self.owner, 'Dispatched', 'R'); advance(order.pk, self.owner, 'Delivered')

    def test_new_store_must_use_mall_pay_first(self):
        result = own_gateway_eligibility(self.shop)
        self.assertFalse(result['eligible'])
        self.assertContains(self.client.get('/seller/gateway/'), 'Requirements for a seller-owned account')
        self.post_key()
        self.assertFalse(GatewayConnection.objects.filter(shop=self.shop).exists())

    def test_established_store_can_connect_own_account(self):
        Shop.objects.filter(pk=self.shop.pk).update(created=timezone.now() - timedelta(days=120))
        self.deliver(2)
        self.shop.refresh_from_db()
        self.assertTrue(own_gateway_eligibility(self.shop)['eligible'])
        self.post_key()
        self.assertEqual(GatewayConnection.objects.get(shop=self.shop).mode, 'own')

    def test_overdue_commission_blocks_eligibility(self):
        Shop.objects.filter(pk=self.shop.pk).update(created=timezone.now() - timedelta(days=400))
        self.deliver(2)
        BillingInvoice.objects.filter(shop=self.shop).update(created=timezone.now() - timedelta(days=45))
        self.shop.refresh_from_db()
        checks = {c['label']: c['ok'] for c in own_gateway_eligibility(self.shop)['checks']}
        self.assertFalse(checks['No commission overdue more than 30 days'])

    def test_unverified_store_is_not_eligible(self):
        Shop.objects.filter(pk=self.shop.pk).update(created=timezone.now() - timedelta(days=120), verified=False)
        self.deliver(2)
        self.shop.refresh_from_db()
        self.assertFalse(own_gateway_eligibility(self.shop)['eligible'])

    def test_platform_override(self):
        Shop.objects.filter(pk=self.shop.pk).update(own_gateway_approved=True)
        self.post_key()
        self.assertTrue(GatewayConnection.objects.filter(shop=self.shop, mode='own').exists())

    def test_existing_own_connection_is_grandfathered(self):
        GatewayConnection.objects.create(shop=self.shop, mode='own', encrypted_secret=encrypt_secret('sk_test_' + 'y' * 20, self.key), active=True)
        self.assertContains(self.client.get('/seller/gateway/'), 'remains available')
        self.post_key()
        self.assertEqual(GatewayConnection.objects.get(shop=self.shop).mode, 'own')
