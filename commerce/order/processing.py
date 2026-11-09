from oscar.apps.order.processing import EventHandler as CoreEventHandler
from oscar.apps.order.exceptions import InvalidOrderStatus

class EventHandler(CoreEventHandler):
    """Keep Oscar dashboard actions on the same tenant/COD policy as storefront."""
    def handle_order_status_change(self,order,new_status,note_msg=None):
        tenant=getattr(order,'tenant_order',None)
        if tenant is None or self.kwargs.get('marketplace_internal'):
            return super().handle_order_status_change(order,new_status,note_msg)
        if new_status==order.status:return
        if new_status in ['Paid','Refunded']:
            raise InvalidOrderStatus('Verify the actual payment/refund in the merchant finance workflow first.')
        from mall.order_actions import advance,cancel
        if self.user is None:raise InvalidOrderStatus('An authorised staff actor is required.')
        from mall.models import StaffMembership
        if not self.user.is_staff and self.user.pk!=tenant.shop.owner_id and not StaffMembership.objects.filter(shop=tenant.shop,user=self.user,active=True,role__in=['manager','support']).exists():raise InvalidOrderStatus('This order belongs to another seller.')
        try:
            if new_status=='Cancelled':cancel(tenant.pk,self.user)
            else:advance(tenant.pk,self.user,new_status,tenant.delivery_reference)
        except ValueError as error:raise InvalidOrderStatus(str(error)) from None
