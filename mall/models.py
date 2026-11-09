from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
from datetime import date
import calendar
from oscar.core.loading import get_model
BuyerAddress=get_model('address','UserAddress')

class Shop(models.Model):
    oscar_partner=models.OneToOneField('partner.Partner',on_delete=models.PROTECT,null=True,blank=True,related_name='tenant_store')
    owner=models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    name=models.CharField(max_length=100)
    slug=models.SlugField(unique=True)
    description=models.TextField(blank=True)
    location=models.CharField(max_length=100,default='Accra, Ghana')
    programme=models.CharField(max_length=30,default='Independent')
    country=models.CharField(max_length=2,default='GH')
    currency=models.CharField(max_length=3,default='GHS')
    verified=models.BooleanField(default=False)
    active=models.BooleanField(default=False)
    created=models.DateTimeField(default=timezone.now)
    own_gateway_approved=models.BooleanField(default=False,help_text='Platform override: allow this seller to connect their own Paystack account before meeting the automatic eligibility threshold.')
    def __str__(self): return self.name
    def trial_end(self):
        from .pricing import trial_end
        return trial_end(timezone.localtime(self.created).date())
class PaymentMethod(models.Model):
    shop=models.ForeignKey(Shop,on_delete=models.CASCADE,related_name='payment_methods')
    kind=models.CharField(max_length=30,choices=[('cod','Cash on Delivery'),('momo','Mobile money'),('bank','Bank transfer'),('collection','Pay on collection'),('online','Online gateway')])
    label=models.CharField(max_length=100)
    instructions=models.TextField(help_text='Public payment instructions only. Never enter API keys or passwords.')
    active=models.BooleanField(default=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['shop'],condition=models.Q(kind='cod'),name='one_cod_per_shop')]
    def save(self,*args,**kwargs):
        if self.kind=='cod':self.active=True
        super().save(*args,**kwargs)
from .catalogue import ListingManager,COMMERCE_FIELDS,commerce_property,save_listing
def image_allowed(url):
    """Seller image links must be HTTPS and, when PRODUCT_IMAGE_HOSTS is set, on an approved host."""
    from urllib.parse import urlparse
    if not isinstance(url,str) or not url:return False
    parsed=urlparse(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:return False
    hosts=getattr(settings,'PRODUCT_IMAGE_HOSTS',[])
    host=parsed.hostname.lower()
    return not hosts or any(host==h or host.endswith('.'+h) for h in hosts)
class Product(models.Model):
    """Tenant listing; Oscar owns title, description, category, price and stock."""
    objects=ListingManager()
    name=commerce_property('name')
    description=commerce_property('description')
    active=commerce_property('active')
    category=commerce_property('category')
    price=commerce_property('price')
    stock=commerce_property('stock')
    def __init__(self,*args,**kwargs):
        values={key:kwargs.pop(key) for key in list(kwargs) if key in COMMERCE_FIELDS}
        self._commerce={}
        super().__init__(*args,**kwargs)
        self._commerce.update(values)
    def save(self,*args,**kwargs):return save_listing(self,*args,**kwargs)
    def refresh_from_db(self,*args,**kwargs):
        super().refresh_from_db(*args,**kwargs);self._commerce.clear()

    gallery=models.JSONField(default=list,blank=True)
    oscar_product=models.OneToOneField('catalogue.Product',on_delete=models.PROTECT,related_name='tenant_listing')
    shop=models.ForeignKey(Shop,on_delete=models.PROTECT,related_name='products')
    image=models.URLField(blank=True)
    classified=models.BooleanField(default=False)
    def __str__(self): return self.name
    @property
    def reviews(self):return self.oscar_product.reviews
    @property
    def image_url(self):
        from urllib.parse import urlparse
        from django.templatetags.static import static
        if self.image:
            url=urlparse(self.image)
            if url.netloc=='images.unsplash.com':
                name=url.path.strip('/')+'.jpg'
                if '/' not in name and (settings.BASE_DIR/'static/demo'/name).is_file():return static('demo/'+name)
        if image_allowed(self.image):return self.image
        return next(iter(self.safe_gallery),'')
    @property
    def safe_gallery(self):
        return [url for url in (self.gallery if isinstance(self.gallery,list) else []) if image_allowed(url)]
    @property
    def gallery_images(self):
        return list(dict.fromkeys(([self.image_url] if self.image_url else [])+self.safe_gallery))
class CommissionPolicy(models.Model):
    rate=models.DecimalField(max_digits=5,decimal_places=4,default=Decimal('0.03'))
    effective=models.DateTimeField(default=timezone.now)
from .order_projection import TenantOrderManager,CORE_FIELDS,core_property,save_order,shipping_data,set_shipping_data,address_text
class Order(models.Model):
    """Tenant/COD/commission metadata for one canonical Oscar order."""
    objects=TenantOrderManager()
    delivery_metadata=models.JSONField(default=dict,blank=True)
    status=core_property('status')
    total=core_property('total')
    currency=core_property('currency')
    delivery_fee=core_property('delivery_fee')
    created=core_property('created')
    delivery_address=property(shipping_data,set_shipping_data)
    address=property(address_text,lambda self,value:self.delivery_metadata.__setitem__('legacy_address',value))
    def __init__(self,*args,**kwargs):
        self._order_values={};self._shipping_values={}
        super().__init__(*args,**kwargs)
    def save(self,*args,**kwargs):return save_order(self,*args,**kwargs)
    def refresh_from_db(self,*args,**kwargs):
        super().refresh_from_db(*args,**kwargs);self._order_values.clear();self._shipping_values.clear()

    cash_on_delivery=models.BooleanField(default=False)
    fulfilment=models.CharField(max_length=20,default='delivery',choices=[('delivery','Delivery'),('collection','Collection')])
    oscar_order=models.OneToOneField('order.Order',on_delete=models.PROTECT,related_name='tenant_order')
    buyer=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    shop=models.ForeignKey(Shop,on_delete=models.PROTECT)
    commission=models.DecimalField(max_digits=12,decimal_places=2,default=0)
    payment_method=models.ForeignKey(PaymentMethod,on_delete=models.PROTECT,null=True,blank=True)
    payment_snapshot=models.TextField()
    payment_reference=models.CharField(max_length=150,blank=True)
    delivery_reference=models.CharField(max_length=150,blank=True)
    checkout_key=models.CharField(max_length=64)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['buyer','shop','checkout_key'],name='unique_checkout_shop')]
    @property
    def lines(self):
        return get_model('order','Line').objects.filter(order_id=self.oscar_order_id).annotate(name=models.F('title'),unit_price=models.F('unit_price_incl_tax'))


class SellerSMSSettings(models.Model):
    shop=models.OneToOneField(Shop,on_delete=models.CASCADE,related_name='sms_settings')
    encrypted_key=models.TextField(blank=True)
    sender_id=models.CharField(max_length=11,blank=True)
    active=models.BooleanField(default=False)
    updated=models.DateTimeField(auto_now=True)

class TrackingEvent(models.Model):
    communication_event=models.OneToOneField('order.CommunicationEvent',null=True,blank=True,on_delete=models.PROTECT,related_name='marketplace_tracking')
    order=models.ForeignKey(Order,on_delete=models.CASCADE,related_name='tracking_events')
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,blank=True)
    title=models.CharField(max_length=120)
    status=models.CharField(max_length=30)
    note=models.TextField(blank=True)
    location=models.CharField(max_length=160,blank=True)
    latitude=models.DecimalField(max_digits=9,decimal_places=6,null=True,blank=True)
    longitude=models.DecimalField(max_digits=9,decimal_places=6,null=True,blank=True)
    created=models.DateTimeField(default=timezone.now)
    class Meta:
        ordering=['-created','-pk']

class OutboundMessage(models.Model):
    event=models.ForeignKey(TrackingEvent,on_delete=models.CASCADE,related_name='messages')
    channel=models.CharField(max_length=10,choices=[('email','Email'),('sms','SMS'),('whatsapp','WhatsApp')])
    audience=models.CharField(max_length=10,default='buyer')
    payload=models.JSONField(default=dict,blank=True)
    recipient=models.CharField(max_length=254)
    subject=models.CharField(max_length=180)
    body=models.TextField()
    state=models.CharField(max_length=15,default='queued',choices=[(v,v) for v in ['queued','sending','preview','sent','accepted','delivered','read','failed','uncertain','skipped']])
    attempts=models.PositiveIntegerField(default=0)
    provider_reference=models.CharField(max_length=150,blank=True)
    error=models.CharField(max_length=250,blank=True)
    created=models.DateTimeField(default=timezone.now)
    updated=models.DateTimeField(auto_now=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['event','channel','audience'],name='unique_event_channel_audience')]

class SellerWhatsAppSettings(models.Model):
    shop=models.OneToOneField(Shop,on_delete=models.CASCADE,related_name='whatsapp_settings')
    phone_number_id=models.CharField(max_length=40,unique=True)
    encrypted_token=models.TextField()
    encrypted_app_secret=models.TextField()
    verify_token_hash=models.CharField(max_length=64)
    order_template=models.CharField(max_length=100)
    seller_template=models.CharField(max_length=100,blank=True)
    language=models.CharField(max_length=20,default='en')
    seller_phone=models.CharField(max_length=25,blank=True)
    seller_opt_in=models.BooleanField(default=False)
    active=models.BooleanField(default=False)
    updated=models.DateTimeField(auto_now=True)

class WhatsAppContact(models.Model):
    shop=models.ForeignKey(Shop,on_delete=models.CASCADE)
    phone=models.CharField(max_length=25)
    last_inbound=models.DateTimeField(null=True,blank=True)
    opted_out=models.BooleanField(default=False)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['shop','phone'],name='unique_shop_whatsapp_contact')]

class WhatsAppInbound(models.Model):
    shop=models.ForeignKey(Shop,on_delete=models.CASCADE)
    phone=models.CharField(max_length=25)
    provider_id=models.CharField(max_length=200,unique=True)
    text=models.TextField(blank=True)
    created=models.DateTimeField(default=timezone.now)

class WhatsAppStatusReport(models.Model):
    shop=models.ForeignKey(Shop,on_delete=models.CASCADE)
    provider_reference=models.CharField(max_length=150)
    recipient=models.CharField(max_length=25)
    status=models.CharField(max_length=15)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['shop','provider_reference','recipient','status'],name='unique_whatsapp_report')]
OrderLine=get_model('order','Line')
class Enquiry(models.Model):
    sender=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    product=models.ForeignKey(Product,on_delete=models.CASCADE)
    message=models.TextField()
    created=models.DateTimeField(auto_now_add=True)

class StaffMembership(models.Model):
    shop=models.ForeignKey(Shop,on_delete=models.CASCADE)
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    role=models.CharField(max_length=30,choices=[('manager','Manager'),('finance','Finance'),('support','Support'),('catalogue','Catalogue assistant')])
    active=models.BooleanField(default=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['shop','user'],name='one_shop_membership')]
class Expense(models.Model):
    shop=models.ForeignKey(Shop,on_delete=models.PROTECT)
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    category=models.CharField(max_length=60)
    amount=models.DecimalField(max_digits=12,decimal_places=2)
    description=models.TextField(blank=True)
    reference=models.CharField(max_length=120,blank=True)
    created=models.DateTimeField(default=timezone.now)
class AuditEvent(models.Model):
    shop=models.ForeignKey(Shop,on_delete=models.PROTECT)
    # Empty actor = automatic system action (for example unpaid-order expiry).
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,null=True,blank=True)
    action=models.CharField(max_length=100)
    detail=models.TextField()
    created=models.DateTimeField(auto_now_add=True)

class GatewayConnection(models.Model):
    import uuid
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    shop=models.OneToOneField(Shop,on_delete=models.PROTECT,related_name='gateway')
    PLATFORM='platform';OWN='own'
    provider=models.CharField(max_length=30,default='paystack')
    # platform = Mall Pay: the marketplace Paystack account collects and splits to the seller's subaccount.
    # own = the seller's own Paystack secret (only after the eligibility threshold).
    mode=models.CharField(max_length=10,default=OWN,choices=[(PLATFORM,'Mall Pay (platform-managed)'),(OWN,'Seller-owned Paystack')])
    # Kept when switching to Mall Pay so earlier seller-owned payments can still be verified.
    encrypted_secret=models.TextField(blank=True)
    subaccount_code=models.CharField(max_length=40,blank=True)
    settlement_bank=models.CharField(max_length=40,blank=True)
    settlement_bank_name=models.CharField(max_length=120,blank=True)
    account_last4=models.CharField(max_length=4,blank=True)
    account_name=models.CharField(max_length=150,blank=True)
    test_mode=models.BooleanField(default=True)
    active=models.BooleanField(default=False)
    created=models.DateTimeField(default=timezone.now)
    @property
    def is_platform(self):return self.mode==self.PLATFORM
class PaymentAttempt(models.Model):
    import uuid
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    order=models.ForeignKey(Order,on_delete=models.PROTECT,related_name='payment_attempts')
    gateway=models.ForeignKey(GatewayConnection,on_delete=models.PROTECT)
    reference=models.CharField(max_length=80,unique=True)
    # True when initialised on the marketplace (Mall Pay) Paystack account; fixes which secret verifies it.
    platform=models.BooleanField(default=False)
    platform_commission=models.DecimalField(max_digits=12,decimal_places=2,default=0)
    provider_transaction=models.CharField(max_length=100,blank=True)
    status=models.CharField(max_length=20,default='pending')
    authorization_url=models.URLField(blank=True,max_length=500)
    created=models.DateTimeField(default=timezone.now)
class Receipt(models.Model):
    order=models.OneToOneField(Order,on_delete=models.PROTECT,related_name='receipt')
    shop=models.ForeignKey(Shop,on_delete=models.PROTECT)
    amount=models.DecimalField(max_digits=12,decimal_places=2)
    currency=models.CharField(max_length=3,default='GHS')
    reference=models.CharField(max_length=150)
    method=models.CharField(max_length=30)
    created=models.DateTimeField(default=timezone.now)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['shop','reference'],name='unique_seller_receipt')]
class Journal(models.Model):
    shop=models.ForeignKey(Shop,on_delete=models.PROTECT)
    key=models.CharField(max_length=150,unique=True)
    description=models.CharField(max_length=200)
    created=models.DateTimeField(default=timezone.now)
class Posting(models.Model):
    journal=models.ForeignKey(Journal,on_delete=models.PROTECT,related_name='postings')
    account=models.CharField(max_length=40)
    debit=models.DecimalField(max_digits=12,decimal_places=2,default=0)
    credit=models.DecimalField(max_digits=12,decimal_places=2,default=0)
class BillingInvoice(models.Model):
    shop=models.ForeignKey(Shop,on_delete=models.PROTECT)
    order=models.OneToOneField(Order,on_delete=models.PROTECT,related_name='commission_invoice')
    amount=models.DecimalField(max_digits=12,decimal_places=2)
    currency=models.CharField(max_length=3,default='GHS')
    state=models.CharField(max_length=20,default='Due')
    created=models.DateTimeField(default=timezone.now)
class ReturnRequest(models.Model):
    order=models.OneToOneField(Order,on_delete=models.PROTECT,related_name='return_request')
    reason=models.TextField()
    state=models.CharField(max_length=30,default='Requested')
    seller_response=models.TextField(blank=True)
    refund_reference=models.CharField(max_length=150,blank=True)
    restocked=models.BooleanField(default=False)
    created=models.DateTimeField(default=timezone.now)
Notification=get_model('communication','Notification')
class VerificationRequest(models.Model):
    shop=models.ForeignKey(Shop,on_delete=models.PROTECT)
    business_name=models.CharField(max_length=150)
    registration_reference=models.CharField(max_length=100,blank=True)
    contact_email=models.EmailField()
    contact_phone=models.CharField(max_length=30)
    state=models.CharField(max_length=20,default='Pending',choices=[(v,v) for v in ['Pending','Approved','Rejected']])
    reviewer_notes=models.TextField(blank=True)
    created=models.DateTimeField(default=timezone.now)
class ShopSettings(models.Model):
    regional_delivery_fees=models.JSONField(default=dict,blank=True)
    shop=models.OneToOneField(Shop,on_delete=models.CASCADE,related_name='settings')
    delivery_fee=models.DecimalField(max_digits=10,decimal_places=2,default=0)
    collection_available=models.BooleanField(default=True)
    collection_address=models.TextField(blank=True)
    delivery_policy=models.TextField(blank=True)
    return_policy=models.TextField(blank=True)

Review=get_model('reviews','ProductReview')
Wishlist=get_model('wishlists','WishList')

class ListingReport(models.Model):
    product=models.ForeignKey(Product,on_delete=models.PROTECT)
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    reason=models.CharField(max_length=50,choices=[(x,x) for x in ['Inaccurate listing','Suspected counterfeit','Prohibited content','Suspected fraud','Other']])
    notes=models.TextField(blank=True)
    state=models.CharField(max_length=20,default='Pending')
    created=models.DateTimeField(default=timezone.now)
