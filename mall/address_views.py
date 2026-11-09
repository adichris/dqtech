
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import render,redirect,get_object_or_404
from django.views.decorators.http import require_POST
from .models import BuyerAddress
from .delivery import DeliveryAddressForm
from .geography import REGIONS

ADDRESS_FIELDS=['recipient','phone','country','region','city','street','landmark','digital_address','instructions']

@transaction.atomic
def save_address(user,data,label='Home',make_default=False,address=None):
    get_user_model().objects.select_for_update().get(pk=user.pk)
    values=address_values(data)
    rows=BuyerAddress.objects.filter(user=user)
    if address is not None and address.user_id!=user.pk:raise ValueError('Address does not belong to this account.')
    candidate=BuyerAddress(user=user,**values)
    duplicate=rows.filter(hash=str(candidate.generate_hash())).first()
    if duplicate and address and duplicate.pk!=address.pk:raise ValueError('This address is already saved. Edit or use the existing entry.')
    obj=address or duplicate or candidate
    for key,value in values.items():setattr(obj,key,value)
    obj.is_default_for_shipping=make_default or obj.is_default_for_shipping or not rows.exists()
    if address or not obj.pk:obj.label=(label.strip() or 'Home')[:60]
    # Oscar validates/normalises the address, generates its hash, and maintains defaults.
    obj.full_clean(exclude=['hash','search_text'],validate_unique=False,validate_constraints=False)
    obj.save();return obj

def address_values(data):
    from oscar.core.loading import get_model
    Country=get_model('address','Country')
    names={'GH':'Ghana','NG':'Nigeria','US':'United States','GB':'United Kingdom'}
    code=data.get('country','GH')
    country,_=Country.objects.get_or_create(pk=code,defaults={'name':names.get(code,code),'printable_name':names.get(code,code),'is_shipping_country':True})
    from phonenumber_field.phonenumber import PhoneNumber
    phone=PhoneNumber.from_string(str(data.get('phone','')),region=code) if data.get('phone') else ''
    name=str(data.get('recipient','')).strip().split(' ',1)
    return {'first_name':name[0] if name else '', 'last_name':name[1] if len(name)>1 else '', 'phone_number':phone,'country':country,'state':data.get('region',''),'line4':data.get('city',''),'line1':data.get('street',''),'line2':data.get('landmark',''),'postcode':data.get('digital_address',''),'notes':data.get('instructions','')}

def checkout_addresses(request):
    rows=list(BuyerAddress.objects.filter(user=request.user).select_related('country')) if request.user.is_authenticated else []
    chosen=next((row for row in rows if row.is_default_for_shipping),rows[0] if rows else None)
    selected=request.POST.get('address_choice') if request.method=='POST' else request.GET.get('address')
    if selected=='new':chosen=None
    elif selected is not None:
        chosen=next((row for row in rows if str(row.pk)==selected),None)
        if chosen is None:
            from django.http import Http404
            raise Http404('Saved address not found')
    initial=chosen.data.copy() if chosen else {'country':'GH','recipient':request.user.get_full_name() if request.user.is_authenticated else ''}
    initial['whatsapp_opt_in']=False
    return {'saved_addresses':rows,'selected_address':chosen,'address_form':DeliveryAddressForm(initial=initial)}

@login_required
def address_book(request):
    return render(request,'addresses.html',{'addresses':BuyerAddress.objects.filter(user=request.user)})

@login_required
def address_edit(request,pk=None):
    address=get_object_or_404(BuyerAddress,pk=pk,user=request.user) if pk else None
    # Strip checkout fulfilment fields so address-book entries always have a full address.
    posted=request.POST.copy() if request.method=='POST' else None
    if posted is not None:
        for key in list(posted):
            if key.startswith('fulfilment_'):posted.pop(key)
    form=DeliveryAddressForm(posted,initial=address.data if address else {'country':'GH'})
    form.fields.pop('whatsapp_opt_in')
    for field in form.fields.values():field.widget.attrs['form']='checkout-form'
    label=request.POST.get('label','Home')[:60] if request.method=='POST' else address.label if address else 'Home'
    if request.method=='POST' and form.is_valid():
        try:
            save_address(request.user,form.cleaned_data,label,request.POST.get('is_default')=='on',address)
            messages.success(request,'Address saved for future orders.');return redirect('address_book')
        except ValueError as error:form.add_error(None,str(error))
    return render(request,'address_edit.html',{'address_editor':True,'address':address,'address_label':label,'address_form':form,'delivery_regions':REGIONS,'geo_url':settings.GEO_LOOKUP_URL})

@login_required
@require_POST
@transaction.atomic
def address_default(request,pk):
    get_user_model().objects.select_for_update().get(pk=request.user.pk)
    obj=get_object_or_404(BuyerAddress,pk=pk,user=request.user)
    BuyerAddress.objects.filter(user=request.user).update(is_default_for_shipping=False)
    obj.is_default=True;obj.save(update_fields=['is_default_for_shipping']);return redirect('address_book')

@login_required
@require_POST
@transaction.atomic
def address_delete(request,pk):
    get_user_model().objects.select_for_update().get(pk=request.user.pk)
    obj=get_object_or_404(BuyerAddress,pk=pk,user=request.user);was_default=obj.is_default;obj.delete()
    if was_default:
        replacement=BuyerAddress.objects.filter(user=request.user).first()
        if replacement:replacement.is_default=True;replacement.save(update_fields=['is_default_for_shipping'])
    messages.success(request,'Saved address removed. Existing orders retain their delivery details.')
    return redirect('address_book')
