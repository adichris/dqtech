import time
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from mall.models import OutboundMessage
from mall.messaging import dispatch_one

class Command(BaseCommand):
    help='Drain the durable order email/SMS outbox. --watch runs a background worker.'
    def add_arguments(self,parser):
        parser.add_argument('--watch',action='store_true')
        parser.add_argument('--limit',type=int,default=100)
    def handle(self,*args,**options):
        last_expiry=0.0
        try:
            while True:
                close_old_connections()
                if options['watch'] and time.monotonic()-last_expiry>=300:
                    # Housekeeping every five minutes: release stock held by stale unpaid orders.
                    from mall.services import expire_unpaid_orders
                    expired=expire_unpaid_orders();last_expiry=time.monotonic()
                    if expired:self.stdout.write(f'Expired unpaid orders: {expired}')
                ids=list(OutboundMessage.objects.filter(state='queued').order_by('pk').values_list('pk',flat=True)[:max(1,min(options['limit'],1000))])
                for pk in ids:
                    state=dispatch_one(pk)
                    self.stdout.write(f'Message #{pk}: {state}')
                if not options['watch']:break
                time.sleep(3)
        except KeyboardInterrupt:pass
