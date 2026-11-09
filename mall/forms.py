from django import forms
from .models import Product,PaymentMethod,Shop
def image_check(url):
    from django.conf import settings
    from .models import image_allowed
    if not image_allowed(url):
        hosts=getattr(settings,'PRODUCT_IMAGE_HOSTS',[])
        raise forms.ValidationError('Use a secure https:// image link'+(' from an approved host: '+', '.join(hosts) if hosts else '')+'.')
class ProductForm(forms.ModelForm):
    name=forms.CharField(max_length=150)
    description=forms.CharField(widget=forms.Textarea)
    category=forms.ChoiceField(choices=lambda:[(x,x) for x in __import__('mall.catalogue',fromlist=['CATEGORIES']).CATEGORIES])
    price=forms.DecimalField(max_digits=12,decimal_places=2,min_value=0.01)
    stock=forms.IntegerField(min_value=0)
    active=forms.BooleanField(required=False,initial=True)

    gallery_links=forms.CharField(required=False,widget=forms.Textarea(attrs={'rows':3}),help_text='Optional: up to six additional HTTPS image URLs, one per line.')
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        if self.instance.pk:
            self.fields['gallery_links'].initial='\n'.join(self.instance.gallery)
            for key in ['name','description','category','price','stock','active']:self.initial[key]=getattr(self.instance,key)
    def clean_gallery_links(self):
        from django.core.validators import URLValidator
        urls=[x.strip() for x in self.cleaned_data.get('gallery_links','').splitlines() if x.strip()]
        if len(urls)>6:raise forms.ValidationError('Use up to six gallery images.')
        for url in urls:
            URLValidator(schemes=['https'])(url)
            image_check(url)
        return urls
    def clean_image(self):
        url=self.cleaned_data.get('image','').strip()
        if url:image_check(url)
        return url
    def save(self,commit=True):
        for key in ['name','description','category','price','stock','active']:setattr(self.instance,key,self.cleaned_data[key])
        self.instance.gallery=self.cleaned_data.get('gallery_links',[])
        return super().save(commit=commit)

    class Meta:
        model=Product
        fields=['name','description','category','price','stock','image','classified','active']
    def clean_price(self):
        v=self.cleaned_data['price']
        if v<=0: raise forms.ValidationError('Price must be greater than zero.')
        return v
class PaymentForm(forms.ModelForm):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['kind'].choices=[(k,v) for k,v in self.fields['kind'].choices if k not in ['online','cod']]
    def clean_kind(self):
        kind=self.cleaned_data['kind']
        if kind=='online':raise forms.ValidationError('Configure online payments in Gateway settings.')
        return kind
    class Meta:
        model=PaymentMethod
        fields=['kind','label','instructions','active']
class ShopForm(forms.ModelForm):
    class Meta:
        model=Shop
        fields=['name','slug','description','location','programme','country','currency']
    def clean(self):
        data=super().clean()
        markets={'GH':'GHS','NG':'NGN','US':'USD','GB':'GBP'}
        if markets.get(data.get('country'))!=data.get('currency'):raise forms.ValidationError('Supported country/currency pairs: GH/GHS, NG/NGN, US/USD, GB/GBP.')
        return data

from .models import Expense
class ExpenseForm(forms.ModelForm):
    class Meta:
        model=Expense
        fields=['category','amount','description','reference']
    def clean_amount(self):
        value=self.cleaned_data['amount']
        if value<=0: raise forms.ValidationError('Amount must be greater than zero.')
        return value

class GatewayForm(forms.Form):
    secret=forms.CharField(widget=forms.PasswordInput(render_value=False),help_text='Your own Paystack secret. Stored encrypted; never shown again.')
    test_mode=forms.BooleanField(required=False,initial=True)
    active=forms.BooleanField(required=False)
    def clean(self):
        data=super().clean();secret=data.get('secret','')
        prefix='sk_test_' if data.get('test_mode') else 'sk_live_'
        if not secret.startswith(prefix) or len(secret)<20:raise forms.ValidationError('The key does not match the selected test/live mode.')
        return data
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
class RegistrationForm(UserCreationForm):
    email=forms.EmailField(required=True)
    class Meta(UserCreationForm.Meta):
        model=get_user_model()
        fields=('username','email')
    def clean_email(self):
        email=self.cleaned_data['email'].lower()
        if get_user_model().objects.filter(email__iexact=email).exists():raise forms.ValidationError('This email address is already registered.')
        return email
from .models import ShopSettings,VerificationRequest
class SettingsForm(forms.ModelForm):
    regional_rates=forms.CharField(required=False,label='Ghana regional delivery rates (optional)',widget=forms.Textarea(attrs={'rows':5}),help_text='One Region=Amount per line, for example Greater Accra=20 or Ashanti=35. Use exact region names. Other regions use your default delivery fee. Amounts are in your store currency.')
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        if self.instance.pk:self.fields['regional_rates'].initial='\n'.join(f'{region}={value}' for region,value in self.instance.regional_delivery_fees.items())
    def clean_regional_rates(self):
        from decimal import Decimal,InvalidOperation
        from .geography import REGIONS
        rates={}
        for line in self.cleaned_data.get('regional_rates','').splitlines():
            if not line.strip():continue
            try:
                region,raw=line.split('=',1);region=region.strip();value=Decimal(raw.strip())
                if region not in REGIONS or region in rates or not value.is_finite() or value<0 or value>Decimal('99999999.99') or value!=value.quantize(Decimal('.01')):raise ValueError()
            except (ValueError,InvalidOperation):raise forms.ValidationError('Use a unique valid Ghana region and a non-negative amount with up to two decimal places per line: Greater Accra=20.00')
            rates[region]=str(value.quantize(Decimal('.01')))
        return rates
    def save(self,commit=True):
        self.instance.regional_delivery_fees=self.cleaned_data.get('regional_rates',{})
        return super().save(commit=commit)

    class Meta:
        model=ShopSettings
        fields=['delivery_fee','collection_available','collection_address','delivery_policy','return_policy']
    def clean_delivery_fee(self):
        value=self.cleaned_data['delivery_fee']
        if value<0:raise forms.ValidationError('Delivery fee cannot be negative.')
        return value
class VerificationForm(forms.ModelForm):
    class Meta:
        model=VerificationRequest
        fields=['business_name','registration_reference','contact_email','contact_phone']

from .models import Review
class ReviewForm(forms.ModelForm):
    rating=forms.TypedChoiceField(coerce=int,choices=[(n,str(n)) for n in range(1,6)])
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        if self.instance.pk:self.initial['rating']=self.instance.score
    def save(self,commit=True):
        self.instance.score=self.cleaned_data['rating']
        return super().save(commit=commit)

    class Meta:
        model=Review
        fields=['rating','title','body']
        widgets={'body':forms.Textarea(attrs={'rows':4,'maxlength':4000})}
    def clean_body(self):
        value=self.cleaned_data['body'].strip()
        if not value or len(value)>4000:raise forms.ValidationError('Write a review of up to 4,000 characters.')
        return value
