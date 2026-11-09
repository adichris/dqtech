import re
from django import forms
from decimal import Decimal, InvalidOperation
from .geography import REGIONS


class DeliveryAddressForm(forms.Form):
    recipient = forms.CharField(max_length=100, label='Recipient name', widget=forms.TextInput(attrs={'autocomplete':'shipping name'}))
    phone = forms.CharField(max_length=25, label='Contact phone', widget=forms.TextInput(attrs={'type':'tel','autocomplete':'shipping tel','placeholder':'+233 24 123 4567'}))
    country = forms.ChoiceField(choices=[('GH','Ghana'),('NG','Nigeria'),('US','United States'),('GB','United Kingdom')], initial='GH')
    region = forms.CharField(max_length=100, label='Region / state')
    city = forms.CharField(max_length=100, label='City / town', widget=forms.TextInput(attrs={'autocomplete':'shipping address-level2','list':'delivery-cities'}))
    street = forms.CharField(max_length=250, label='Street, house or building', widget=forms.TextInput(attrs={'autocomplete':'shipping address-line1'}))
    landmark = forms.CharField(max_length=150, required=False, label='Nearby landmark / area')
    digital_address = forms.CharField(max_length=30, required=False, label='GhanaPost GPS / postcode (optional)')
    instructions = forms.CharField(max_length=500, required=False, label='Delivery or collection notes', widget=forms.Textarea(attrs={'rows':2}))

    whatsapp_opt_in=forms.BooleanField(required=False,label='Send me purchase and delivery updates on WhatsApp from the sellers in this order')

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        for name,field in self.fields.items():
            field.widget.attrs.update({'form':'checkout-form','id':'delivery-'+name})
        if self.is_bound:
            fulfilments=[v for k,v in self.data.items() if k.startswith('fulfilment_')]
            if fulfilments and all(v=='collection' for v in fulfilments):
                for name in ['street','region','city']:self.fields[name].required=False
        country=self.data.get('country',self.initial.get('country','GH')) if self.is_bound else self.initial.get('country','GH')
        if country=='GH':
            self.fields['region']=forms.ChoiceField(required=self.fields['region'].required,choices=[('','Choose a region')]+[(r,r) for r in REGIONS],widget=forms.Select(attrs={'form':'checkout-form','id':'delivery-region'}))

    def clean_phone(self):
        value=self.cleaned_data['phone']
        if not re.fullmatch(r'\+?[\d\s()\-]{7,25}',value) or not 7<=len(re.sub(r'\D','',value))<=15:
            raise forms.ValidationError('Enter a valid contact phone number, including country code when needed.')
        return value

    def clean(self):
        data=super().clean()
        # A town outside the suggestions is allowed, but known towns must match.
        if data.get('country')=='GH' and data.get('city') and data.get('region'):
            known={r for r,towns in REGIONS.items() if data['city'].casefold() in [t.casefold() for t in towns]}
            if known and data['region'] not in known:self.add_error('city','This town belongs to a different region. Check your region or city.')
        if data.get('whatsapp_opt_in'):
            from .messaging import normalize_phone
            if not normalize_phone(data.get('phone',''),data.get('country','GH')):self.add_error('phone','Use an international phone number, or a valid Ghana/Nigeria local number, for WhatsApp updates.')
        if not self.errors and data.get('street'):
            from django.core.exceptions import ValidationError
            from oscar.core.loading import get_model
            from .address_views import address_values
            native=get_model('order','ShippingAddress')(**address_values(data))
            try:native.full_clean(exclude=['search_text'])
            except ValidationError as error:
                aliases={'first_name':'recipient','phone_number':'phone','line1':'street','line4':'city','state':'region','postcode':'digital_address'}
                for key,errors in error.message_dict.items():
                    for message in errors:self.add_error(aliases.get(key,key) if aliases.get(key,key) in self.fields else None,message)
        return data

    def formatted(self):
        data=self.cleaned_data
        return '\n'.join(str(data[k]) for k in ['recipient','phone','street','landmark','city','region','country','digital_address','instructions'] if data.get(k))


def ensure_cod(shop):
    from .models import PaymentMethod
    method,_=PaymentMethod.objects.get_or_create(shop=shop,kind='cod',defaults={'label':'Cash on Delivery','instructions':'Pay your seller or their authorised delivery agent in cash when your order arrives, or at collection. No advance payment required.','active':True})
    if not method.active:
        method.active=True;method.save(update_fields=['active'])
    return method


def delivery_fee(config,fulfilment,address=None):
    if fulfilment=='collection' or config is None:return Decimal('0')
    address=address or {}
    if address.get('country')=='GH':
        raw=config.regional_delivery_fees.get(address.get('region'),config.delivery_fee)
    else:raw=config.delivery_fee
    try:
        fee=Decimal(str(raw))
        if not fee.is_finite() or fee<0 or fee>Decimal('99999999.99') or fee!=fee.quantize(Decimal('.01')):raise ValueError()
        return fee
    except (InvalidOperation,ValueError,TypeError):raise ValueError('This seller has an invalid delivery rate. Please contact the seller.')
