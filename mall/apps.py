from django.apps import AppConfig

class MallConfig(AppConfig):
    default_auto_field='django.db.models.BigAutoField'
    name='mall'

    def ready(self):
        from django.db.models.signals import post_save
        from .models import Shop,StaffMembership
        from oscar.core.loading import get_model
        from .delivery import ensure_cod
        def provision(sender,instance,created,raw=False,**kwargs):
            if raw:return
            if created:ensure_cod(instance)
            Partner=get_model('partner','Partner')
            if not instance.oscar_partner_id:
                partner=Partner.objects.create(name=instance.name,code='shop-'+str(instance.pk))
                Shop.objects.filter(pk=instance.pk).update(oscar_partner=partner)
                instance.oscar_partner=partner
            else:partner=instance.oscar_partner
            partner.users.set({instance.owner_id,*StaffMembership.objects.filter(shop=instance,active=True).values_list('user_id',flat=True)})
        def staff_changed(sender,instance,**kwargs):
            if instance.shop.oscar_partner_id:
                provision(Shop,instance.shop,False)
        from django.db.models.signals import post_delete
        post_save.connect(staff_changed,sender=StaffMembership,weak=False,dispatch_uid='mall.oscar_partner_staff')
        post_delete.connect(staff_changed,sender=StaffMembership,weak=False,dispatch_uid='mall.oscar_partner_staff_delete')
        post_save.connect(provision,sender=Shop,weak=False,dispatch_uid='mall.default_cod')
