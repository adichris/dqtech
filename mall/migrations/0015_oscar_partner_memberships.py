from django.db import migrations

def map_partners(apps,schema_editor):
    Shop=apps.get_model('mall','Shop');Partner=apps.get_model('partner','Partner');Staff=apps.get_model('mall','StaffMembership')
    for shop in Shop.objects.all().iterator():
        if shop.oscar_partner_id:partner=Partner.objects.get(pk=shop.oscar_partner_id)
        else:
            partner=Partner.objects.create(name=shop.name,code='shop-'+str(shop.pk))
            shop.oscar_partner=partner;shop.save(update_fields=['oscar_partner'])
        partner.users.set({shop.owner_id,*Staff.objects.filter(shop=shop,active=True).values_list('user_id',flat=True)})

class Migration(migrations.Migration):
    dependencies=[('mall','0014_remove_order_address_remove_order_created_and_more')]
    operations=[migrations.RunPython(map_partners,migrations.RunPython.noop)]
