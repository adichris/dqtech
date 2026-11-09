from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Shop,Product,PaymentMethod,Order,OrderLine,Enquiry,CommissionPolicy
for model in [Shop,Product,PaymentMethod,Enquiry,CommissionPolicy]: admin.site.register(model,ModelAdmin)

from .models import StaffMembership,Expense,AuditEvent
for model in [StaffMembership]:admin.site.register(model,ModelAdmin)
@admin.register(AuditEvent)
class AuditAdmin(ModelAdmin):
    readonly_fields=['shop','actor','action','detail','created']
    def has_add_permission(self,request):return False
    def has_change_permission(self,request,obj=None):return False
    def has_delete_permission(self,request,obj=None):return False

from .models import GatewayConnection,PaymentAttempt,Receipt,Journal,Posting,BillingInvoice,ReturnRequest,Notification,VerificationRequest,ShopSettings,Review,Wishlist
for model in [ShopSettings]:admin.site.register(model,ModelAdmin)
@admin.register(VerificationRequest)
class VerificationAdmin(ModelAdmin):
    list_display=['business_name','shop','state','created']
    def save_model(self,request,obj,form,change):
        super().save_model(request,obj,form,change)
        if obj.state in ['Approved','Rejected']:
            obj.shop.verified=obj.state=='Approved';obj.shop.active=obj.state=='Approved';obj.shop.save()
            AuditEvent.objects.create(shop=obj.shop,actor=request.user,action='Business verification '+obj.state,detail=str(obj.pk))
class ReadOnlyFinanceAdmin(ModelAdmin):
    def has_add_permission(self,request):return False
    def has_change_permission(self,request,obj=None):return False
    def has_delete_permission(self,request,obj=None):return False
for model in [Order,Expense,PaymentAttempt,Receipt,Journal,Posting,BillingInvoice,ReturnRequest]:admin.site.register(model,ReadOnlyFinanceAdmin)
# Gateway secrets are intentionally not registered in the technical admin.
from django.conf import settings
admin.site.site_header=settings.SYSTEM_NAME+' — Technical administration'
admin.site.site_title=settings.SYSTEM_NAME

from .models import ListingReport
admin.site.register(ListingReport,ModelAdmin)

from .models import TrackingEvent,OutboundMessage,WhatsAppInbound,WhatsAppStatusReport
for model in [TrackingEvent,OutboundMessage,WhatsAppInbound,WhatsAppStatusReport]:admin.site.register(model,ReadOnlyFinanceAdmin)
