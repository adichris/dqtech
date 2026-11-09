from django.db import migrations,models
import django.db.models.deletion


def move_orders(apps,schema_editor):
    from django.utils.text import slugify
    Tenant=apps.get_model('mall','Order');LegacyLine=apps.get_model('mall','OrderLine');Core=apps.get_model('order','Order');Line=apps.get_model('order','Line');Address=apps.get_model('order','ShippingAddress');Country=apps.get_model('address','Country');Stock=apps.get_model('partner','StockRecord');Receipt=apps.get_model('mall','Receipt');Source=apps.get_model('payment','Source');SourceType=apps.get_model('payment','SourceType');Txn=apps.get_model('payment','Transaction');Tracking=apps.get_model('mall','TrackingEvent');Kind=apps.get_model('communication','CommunicationEventType');Communication=apps.get_model('order','CommunicationEvent')
    names={'GH':'Ghana','NG':'Nigeria','US':'United States','GB':'United Kingdom'}
    for code,name in names.items():
        country,created=Country.objects.get_or_create(pk=code,defaults={'name':name,'printable_name':name,'is_shipping_country':True})
        if not country.is_shipping_country:country.is_shipping_country=True;country.save(update_fields=['is_shipping_country'])
    address_keys={'recipient','phone','country','region','city','street','landmark','digital_address','instructions'}
    for order in Tenant.objects.select_related('shop').all().iterator():
        new_core=not order.oscar_order_id
        if new_core:
            core=Core.objects.create(number='DQ-'+str(order.pk),date_placed=order.created,site_id=1,user_id=order.buyer_id,currency=order.currency,total_incl_tax=order.total,total_excl_tax=order.total,shipping_incl_tax=order.delivery_fee,shipping_excl_tax=order.delivery_fee,status=order.status,shipping_code='merchant-'+str(order.shop_id)+'-'+order.fulfilment,shipping_method=order.fulfilment)
            Core.objects.filter(pk=core.pk).update(date_placed=order.created)
            order.oscar_order_id=core.pk
        else:core=Core.objects.get(pk=order.oscar_order_id)
        if not core.shipping_address_id:
            data=order.delivery_address or {};code=data.get('country',order.shop.country);country,_=Country.objects.get_or_create(pk=code,defaults={'name':code,'printable_name':code,'is_shipping_country':True})
            name=data.get('recipient','Customer').split(' ',1)
            address=Address.objects.create(first_name=name[0],last_name=name[1] if len(name)>1 else '',line1=data.get('street') or order.address,line2=data.get('landmark',''),line4=data.get('city',''),state=data.get('region',''),country=country,phone_number=data.get('phone',''),postcode=data.get('digital_address',''),notes=data.get('instructions',''),search_text=order.address)
            core.shipping_address_id=address.pk;core.save(update_fields=['shipping_address'])
        for old in LegacyLine.objects.filter(order=order).select_related('product'):
            if not Line.objects.filter(order=core,product_id=old.product.oscar_product_id).exists():
                record=Stock.objects.get(product_id=old.product.oscar_product_id,partner_id=order.shop.oscar_partner_id)
                allocated=old.quantity if core.status in ['Awaiting payment','Confirmed','Paid','Preparing'] else 0
                Line.objects.create(order=core,product_id=old.product.oscar_product_id,title=old.name,quantity=old.quantity,stockrecord=record,partner_id=record.partner_id,partner_name=order.shop.name,partner_sku=record.partner_sku,status=core.status,unit_price_incl_tax=old.unit_price,unit_price_excl_tax=old.unit_price,line_price_incl_tax=old.unit_price*old.quantity,line_price_excl_tax=old.unit_price*old.quantity,line_price_before_discounts_incl_tax=old.unit_price*old.quantity,line_price_before_discounts_excl_tax=old.unit_price*old.quantity,num_allocated=allocated)
                if allocated:
                    record.num_in_stock=(record.num_in_stock or 0)+allocated;record.num_allocated=(record.num_allocated or 0)+allocated;record.save()
        order.delivery_metadata={key:value for key,value in (order.delivery_address or {}).items() if key not in address_keys}
        order.save(update_fields=['oscar_order','delivery_metadata'])
        receipt=Receipt.objects.filter(order=order).first()
        if receipt:
            kind,_=SourceType.objects.get_or_create(name=receipt.method,defaults={'code':slugify(receipt.method)})
            source,created=Source.objects.get_or_create(order=core,reference=receipt.reference,defaults={'source_type':kind,'currency':receipt.currency,'amount_allocated':receipt.amount,'amount_debited':receipt.amount})
            if not Txn.objects.filter(source=source,txn_type='Debit').exists():Txn.objects.create(source=source,txn_type='Debit',amount=source.amount_debited,reference=receipt.reference,status='Migrated verified receipt')
            if source.amount_refunded and not Txn.objects.filter(source=source,txn_type='Refund').exists():Txn.objects.create(source=source,txn_type='Refund',amount=source.amount_refunded,reference=receipt.reference,status='Migrated confirmed refund')
        for event in Tracking.objects.filter(order=order,communication_event__isnull=True):
            kind,_=Kind.objects.get_or_create(code='MARKETPLACE_'+slugify(event.title).replace('-','_').upper(),defaults={'name':event.title,'category':'Order related'})
            communication=Communication.objects.create(order=core,event_type=kind);Communication.objects.filter(pk=communication.pk).update(date_created=event.created)
            event.communication_event=communication;event.save(update_fields=['communication_event'])

class Migration(migrations.Migration):
    dependencies=[('mall','0013_remove_review_product_remove_review_user_and_more'),('order','0021_billingaddress_code_shippingaddress_code'),('sites','0002_alter_domain_unique'),('payment','0005_auto_20200801_0817')]
    operations=[
        migrations.AddField(model_name='order',name='delivery_metadata',field=models.JSONField(blank=True,default=dict)),
        migrations.AddField(model_name='trackingevent',name='communication_event',field=models.OneToOneField(blank=True,null=True,on_delete=django.db.models.deletion.PROTECT,related_name='marketplace_tracking',to='order.communicationevent')),
        migrations.RunPython(move_orders),
        *[migrations.RemoveField(model_name='order',name=name) for name in ['address','created','currency','delivery_address','delivery_fee','status','total']],
        migrations.DeleteModel(name='OrderLine'),
        migrations.AlterField(model_name='product',name='oscar_product',field=models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,related_name='tenant_listing',to='catalogue.product')),
        migrations.AlterField(model_name='order',name='oscar_order',field=models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,related_name='tenant_order',to='order.order')),
    ]
