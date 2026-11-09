"""When a seller may switch from Mall Pay to their own Paystack account.

With their own account, the marketplace cannot deduct commission at payment time,
so the seller must first show a track record. Thresholds live in settings:

- business verified by the platform
- OWN_GATEWAY_MIN_DAYS (90) since the store opened: past the commission-free trial
- OWN_GATEWAY_MIN_DELIVERED_ORDERS (25) delivered orders
- refunds at most OWN_GATEWAY_MAX_REFUND_RATE (10%) of completed orders
- no commission invoice overdue by more than OWN_GATEWAY_OVERDUE_DAYS (30)

Platform staff can approve a store early with Shop.own_gateway_approved.
"""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.utils import timezone


def thresholds():
    return {
        'days': getattr(settings, 'OWN_GATEWAY_MIN_DAYS', 90),
        'orders': getattr(settings, 'OWN_GATEWAY_MIN_DELIVERED_ORDERS', 25),
        'refund_rate': Decimal(str(getattr(settings, 'OWN_GATEWAY_MAX_REFUND_RATE', '0.10'))),
        'overdue_days': getattr(settings, 'OWN_GATEWAY_OVERDUE_DAYS', 30),
    }


def own_gateway_eligibility(shop, now=None):
    from .models import BillingInvoice, Order
    now = now or timezone.now()
    t = thresholds()
    age = (now - shop.created).days
    delivered = Order.objects.filter(shop=shop, oscar_order__status='Delivered').count()
    refunded = Order.objects.filter(shop=shop, oscar_order__status='Refunded').count()
    completed = delivered + refunded
    rate = Decimal(refunded) / Decimal(completed) if completed else Decimal('0')
    overdue = BillingInvoice.objects.filter(shop=shop, state='Due', created__lt=now - timedelta(days=t['overdue_days'])).count()
    checks = [
        {'label': 'Business verified by the marketplace', 'ok': shop.verified, 'detail': 'Verified' if shop.verified else 'Submit your business details for verification'},
        {'label': f"Selling for at least {t['days']} days", 'ok': age >= t['days'], 'detail': f'{age} of {t["days"]} days'},
        {'label': f"At least {t['orders']} delivered orders", 'ok': delivered >= t['orders'], 'detail': f'{delivered} of {t["orders"]} delivered'},
        {'label': f"Refunds at or below {int(t['refund_rate'] * 100)}% of completed orders", 'ok': rate <= t['refund_rate'], 'detail': f'{(rate * 100).quantize(Decimal("0.1"))}% refunded'},
        {'label': f"No commission overdue more than {t['overdue_days']} days", 'ok': overdue == 0, 'detail': 'Up to date' if not overdue else f'{overdue} overdue invoice(s)'},
    ]
    automatic = all(check['ok'] for check in checks)
    return {'eligible': automatic or shop.own_gateway_approved, 'approved_override': shop.own_gateway_approved and not automatic, 'checks': checks}


def may_save_own_gateway(shop, connection):
    """Existing seller-owned connections are grandfathered; new ones need eligibility."""
    if connection and connection.mode == connection.OWN and connection.encrypted_secret:
        return True
    return own_gateway_eligibility(shop)['eligible']
