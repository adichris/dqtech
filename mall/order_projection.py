from django.db import models
from django.utils import timezone
from oscar.core.loading import get_model,get_class

CORE_FIELDS={'status':'status','total':'total_incl_tax','currency':'currency','delivery_fee':'shipping_incl_tax','created':'date_placed'}
ADDRESS_FIELDS={'recipient','phone','country','region','city','street','landmark','digital_address','instructions'}

class TenantOrderManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().annotate(**{name:models.F('oscar_order__'+field) for name,field in CORE_FIELDS.items()})

def core_value(instance,name):
    if name in instance._order_values:return instance._order_values[name]
    if instance.oscar_order_id:return getattr(instance.oscar_order,CORE_FIELDS[name])
    return {'status':'Awaiting payment','currency':'GHS','total':0,'delivery_fee':0,'created':timezone.now()}[name]

def core_property(name):
    return property(lambda self:core_value(self,name),lambda self,value:self._order_values.__setitem__(name,value))

def save_order(instance,*args,**kwargs):
    requested=kwargs.get('update_fields')
    updates={name:value for name,value in instance._order_values.items() if requested is None or name in requested}
    if instance.oscar_order_id and updates:
        core=get_model('order','Order').objects.select_for_update().get(pk=instance.oscar_order_id)
        status=updates.pop('status',None)
        if status and status!=core.status:
            get_class('order.processing','EventHandler')(marketplace_internal=True).handle_order_status_change(core,status)
        for name,value in updates.items():
            if value!=getattr(core,CORE_FIELDS[name]):
                raise ValueError('Placed order prices, currency and date are immutable Oscar snapshots.')
        instance.oscar_order=core
    if requested is not None:
        kwargs['update_fields']=[key for key in requested if key not in CORE_FIELDS and key not in ['address','delivery_address']]
        if any(key in requested for key in ['address','delivery_address']):kwargs['update_fields'].append('delivery_metadata')
        if not kwargs['update_fields']:
            instance._order_values.clear();return
    models.Model.save(instance,*args,**kwargs)
    if instance.oscar_order_id:instance._order_values.clear()

def shipping_data(instance):
    if instance.oscar_order_id and instance.oscar_order.shipping_address_id:
        address=instance.oscar_order.shipping_address
        return {'recipient':address.name,'phone':str(address.phone_number),'country':address.country_id,'region':address.state,'city':address.line4,'street':address.line1,'landmark':address.line2,'digital_address':address.postcode,'instructions':address.notes,**instance.delivery_metadata}
    return {**instance._shipping_values,**instance.delivery_metadata}

def set_shipping_data(instance,data):
    instance._shipping_values={key:value for key,value in data.items() if key in ADDRESS_FIELDS}
    legacy=instance.delivery_metadata.get('legacy_address','')
    instance.delivery_metadata={key:value for key,value in data.items() if key not in ADDRESS_FIELDS}
    if not instance._shipping_values and legacy:instance.delivery_metadata['legacy_address']=legacy

def address_text(instance):
    data=shipping_data(instance)
    text='\n'.join(str(data[key]) for key in ['recipient','phone','street','landmark','city','region','country','digital_address','instructions'] if data.get(key))
    return ('Collection: ' if instance.fulfilment=='collection' else '')+(text or instance.delivery_metadata.get('legacy_address',''))
