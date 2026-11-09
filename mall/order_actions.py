from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from .models import Order,Product,Receipt,AuditEvent,BillingInvoice,Notification,ReturnRequest
from .ledger import post
from .oscar_bridge import set_status,record_receipt,release_stock

def audit(order,actor,action,detail=''):
    AuditEvent.objects.create(shop=order.shop,actor=actor,action=action,detail=str(order.pk)+' '+detail)
@transaction.atomic
def confirm_payment(order_id,actor,reference,method='manual'):
    order=Order.objects.select_for_update().select_related('shop').get(pk=order_id)
    if Receipt.objects.filter(order=order).exists():return order
    if (order.cash_on_delivery and order.status not in ['Dispatched','Delivered']) or (not order.cash_on_delivery and order.status!='Awaiting payment'):raise ValueError('This order cannot accept a payment. It needs reconciliation.')
    if not reference.strip() or len(reference)>128:raise ValueError('A verified receipt reference of up to 128 characters is required.')
    if order.cash_on_delivery:method='cash_on_delivery'
    Receipt.objects.create(order=order,shop=order.shop,amount=order.total,currency=order.currency,reference=reference,method=method)
    post(order.shop,'receipt:'+str(order.pk),'Order payment', [('seller_receipts',order.total,0),('sales',0,order.total)])
    if not order.cash_on_delivery:order.status='Paid'
    order.payment_reference=reference;order.save(update_fields=['status','payment_reference'])
    record_receipt(order,reference,method)
    from .messaging import record_event
    record_event(order,'Cash collected' if order.cash_on_delivery else 'Payment confirmed',actor=actor)
    audit(order,actor,'Payment verified',method)
    return order
@transaction.atomic
def advance(order_id,actor,target,tracking=''):
    order=Order.objects.select_for_update().select_related('shop').get(pk=order_id)
    transitions={'Confirmed':'Preparing','Paid':'Preparing','Preparing':'Dispatched','Dispatched':'Delivered'}
    if target!=transitions.get(order.status):raise ValueError('Invalid order transition.')
    if target=='Delivered' and order.cash_on_delivery and not Receipt.objects.filter(order=order).exists():raise ValueError('Record the cash actually collected before marking this order delivered.')
    if target=='Dispatched' and not tracking.strip():raise ValueError('Enter a delivery or collection reference.')
    if target=='Dispatched':release_stock(order,'dispatch')
    order.status=target
    if tracking:order.delivery_reference=tracking[:150]
    order.save()
    if target=='Delivered' and order.commission>0 and not BillingInvoice.objects.filter(order=order).exists():
        BillingInvoice.objects.get_or_create(order=order,defaults={'shop':order.shop,'amount':order.commission,'currency':order.currency})
        post(order.shop,'commission:'+str(order.pk),'Marketplace commission',[('commission_expense',order.commission,0),('commission_payable',0,order.commission)])
    set_status(order)
    from .messaging import record_event
    record_event(order,'Ready for collection' if target=='Dispatched' and order.fulfilment=='collection' else target,actor=actor)
    audit(order,actor,'Order '+target)
    return order
@transaction.atomic
def cancel(order_id,actor,reason=''):
    """Cancel an unpaid, unprepared order. actor=None means an automatic system action."""
    order=Order.objects.select_for_update().select_related('shop').get(pk=order_id)
    if order.status=='Cancelled':return order
    if order.status not in ['Awaiting payment','Confirmed'] or Receipt.objects.filter(order=order).exists():raise ValueError('Only unpaid, unprepared orders can be cancelled. Contact your seller for other orders.')
    release_stock(order,'cancel')
    order.status='Cancelled';order.save(update_fields=['status']);set_status(order)
    audit(order,actor,'Order cancelled; stock restored',reason[:200])
    from .messaging import record_event
    record_event(order,'Order cancelled',actor=actor,note=reason[:500])
    if actor is None or actor.pk==order.buyer_id:
        Notification.objects.create(recipient=order.shop.owner,subject='Order #'+str(order.pk)+' was cancelled.',body='/seller/')
    return order
@transaction.atomic
def request_return(order_id,buyer,reason):
    order=Order.objects.select_for_update().get(pk=order_id,buyer=buyer)
    if order.status not in ['Paid','Preparing','Dispatched','Delivered']:raise ValueError('This order is not eligible for a return request.')
    if not reason.strip():raise ValueError('Explain the reason for your request.')
    obj,created=ReturnRequest.objects.get_or_create(order=order,defaults={'reason':reason[:4000]})
    if not created:return obj
    Notification.objects.create(recipient=order.shop.owner,subject='A return/refund request needs attention for order #'+str(order.pk),body='/seller/returns/')
    from .messaging import record_event
    record_event(order,'Return requested',actor=buyer,note=reason[:500])
    audit(order,buyer,'Return requested');return obj
@transaction.atomic
def decide_return(return_id,actor,decision,response,reference='',restock=False):
    request=ReturnRequest.objects.select_for_update().select_related('order__shop').get(pk=return_id)
    order=Order.objects.select_for_update().get(pk=request.order_id)
    if request.state!='Requested':raise ValueError('This request has already been resolved.')
    if decision not in ['Rejected','Refund confirmed','Returned unpaid']:raise ValueError('Choose a valid decision.')
    if decision=='Returned unpaid':
        if not order.cash_on_delivery or Receipt.objects.filter(order=order).exists():raise ValueError('This option is only for Cash on Delivery orders where no cash was collected.')
        if order.status not in ['Preparing','Dispatched','Delivered']:raise ValueError('This order cannot be returned unpaid.')
        if not restock or not reference.strip():raise ValueError('Confirm the goods are back and enter the return delivery reference.')
        release_stock(order,'return' if order.status in ['Dispatched','Delivered'] else 'cancel')
        request.restocked=True
        order.status='Cancelled';order.save(update_fields=['status']);set_status(order)
    if decision=='Refund confirmed':
        if not reference.strip() or len(reference)>128:raise ValueError('Record the actual refund transaction reference (up to 128 characters). This action does not send funds.')
        if not Receipt.objects.filter(order=order).exists():raise ValueError('No verified original receipt was found.')
        post(order.shop,'refund:'+str(order.pk),'Refund confirmed',[('sales',order.total,0),('seller_receipts',0,order.total)])
        invoice=BillingInvoice.objects.filter(order=order).first()
        if invoice and invoice.state=='Due':
            invoice.state='Credited';invoice.save()
            if order.commission>0:post(order.shop,'commission-reversal:'+str(order.pk),'Commission credit',[('commission_payable',order.commission,0),('commission_expense',0,order.commission)])
        elif invoice and invoice.state=='Collected':
            # Mall Pay kept this commission in the split; the marketplace owes it back to the seller.
            invoice.state='Credit due';invoice.save()
            post(order.shop,'commission-reversal:'+str(order.pk),'Mall Pay commission to be returned',[('commission_receivable',invoice.amount,0),('commission_expense',0,invoice.amount)])
            from django.contrib.auth import get_user_model
            for staff in get_user_model().objects.filter(is_superuser=True,is_active=True):
                Notification.objects.create(recipient=staff,subject=f'Mall Pay refund for order #{order.pk}: refund the buyer in Paystack and return {order.currency} {invoice.amount} commission to {order.shop.name}',body='/admin/mall/billinginvoice/')
        if restock:release_stock(order,'return' if order.status in ['Dispatched','Delivered'] else 'cancel')
        elif order.status in ['Paid','Preparing']:release_stock(order,'dispatch')
        request.restocked=restock
        order.status='Refunded';order.save(update_fields=['status']);set_status(order)
        from .oscar_bridge import record_refund
        record_refund(order,reference)
    request.state=decision;request.seller_response=response[:4000];request.refund_reference=reference[:150];request.save()
    from .messaging import record_event
    record_event(order,'Return '+decision,actor=actor,note=response[:500])
    audit(order,actor,'Return '+decision)
    return request
