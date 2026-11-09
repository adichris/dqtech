from django.core.management.base import BaseCommand
from mall.services import expire_unpaid_orders


class Command(BaseCommand):
    help = 'Cancel unpaid online/manual-payment orders past UNPAID_ORDER_HOLD_HOURS and release their stock.'

    def handle(self, *args, **options):
        expired = expire_unpaid_orders()
        self.stdout.write(f'Expired {len(expired)} unpaid order(s).')
