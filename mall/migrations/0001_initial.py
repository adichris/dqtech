from django.db import migrations, models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal

class Migration(migrations.Migration):
    initial=True
    dependencies=[migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations=[
        migrations.CreateModel(name='Shop', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('owner', models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)),
            ('name', models.CharField(max_length=100)),
            ('slug', models.SlugField(unique=True)),
            ('description', models.TextField(blank=True)),
            ('location', models.CharField(max_length=100, default='Accra, Ghana')),
            ('programme', models.CharField(max_length=30, default='Independent')),
            ('verified', models.BooleanField(default=False)),
            ('active', models.BooleanField(default=False)),
            ('created', models.DateTimeField(default=timezone.now))
        ], options={}),
        migrations.CreateModel(name='PaymentMethod', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('shop', models.ForeignKey('mall.shop', on_delete=models.CASCADE, related_name='payment_methods')),
            ('kind', models.CharField(max_length=30, choices=[('momo', 'Mobile money'), ('bank', 'Bank transfer'), ('collection', 'Pay on collection')])),
            ('label', models.CharField(max_length=100)),
            ('instructions', models.TextField(help_text='Public payment instructions only. Never enter API keys or passwords.')),
            ('active', models.BooleanField(default=True))
        ], options={}),
        migrations.CreateModel(name='Product', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('shop', models.ForeignKey('mall.shop', on_delete=models.PROTECT, related_name='products')),
            ('name', models.CharField(max_length=150)),
            ('description', models.TextField()),
            ('category', models.CharField(max_length=50, choices=[(x, x) for x in ['Fashion', 'Electronics', 'Home & Living', 'Beauty', 'Food & Grocery', 'Campus essentials', 'Art & Crafts']])),
            ('price', models.DecimalField(max_digits=12, decimal_places=2)),
            ('stock', models.PositiveIntegerField(default=1)),
            ('image', models.URLField(blank=True)),
            ('classified', models.BooleanField(default=False)),
            ('active', models.BooleanField(default=True))
        ], options={}),
        migrations.CreateModel(name='CommissionPolicy', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('rate', models.DecimalField(max_digits=5, decimal_places=4, default=Decimal('0.03'))),
            ('effective', models.DateTimeField(default=timezone.now))
        ], options={}),
        migrations.CreateModel(name='Order', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('buyer', models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)),
            ('shop', models.ForeignKey('mall.shop', on_delete=models.PROTECT)),
            ('created', models.DateTimeField(default=timezone.now)),
            ('status', models.CharField(max_length=30, default='Awaiting payment', choices=[(x, x) for x in ['Awaiting payment', 'Paid', 'Preparing', 'Dispatched', 'Delivered', 'Cancelled']])),
            ('total', models.DecimalField(max_digits=12, decimal_places=2)),
            ('commission', models.DecimalField(max_digits=12, decimal_places=2, default=0)),
            ('payment_snapshot', models.TextField()),
            ('address', models.TextField()),
            ('payment_reference', models.CharField(max_length=150, blank=True)),
            ('delivery_reference', models.CharField(max_length=150, blank=True)),
            ('checkout_key', models.CharField(max_length=64))
        ], options={'constraints': [models.UniqueConstraint(fields=['buyer', 'shop', 'checkout_key'], name='unique_checkout_shop')]}),
        migrations.CreateModel(name='OrderLine', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('order', models.ForeignKey('mall.order', on_delete=models.CASCADE, related_name='lines')),
            ('product', models.ForeignKey('mall.product', on_delete=models.PROTECT)),
            ('name', models.CharField(max_length=150)),
            ('quantity', models.PositiveIntegerField()),
            ('unit_price', models.DecimalField(max_digits=12, decimal_places=2))
        ], options={}),
        migrations.CreateModel(name='Enquiry', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('sender', models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)),
            ('product', models.ForeignKey('mall.product', on_delete=models.CASCADE)),
            ('message', models.TextField()),
            ('created', models.DateTimeField(auto_now_add=True))
        ], options={}),
        migrations.CreateModel(name='StaffMembership', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('shop', models.ForeignKey('mall.shop', on_delete=models.CASCADE)),
            ('user', models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)),
            ('role', models.CharField(max_length=30, choices=[('manager', 'Manager'), ('finance', 'Finance'), ('support', 'Support'), ('catalogue', 'Catalogue assistant')])),
            ('active', models.BooleanField(default=True))
        ], options={'constraints': [models.UniqueConstraint(fields=['shop', 'user'], name='one_shop_membership')]}),
        migrations.CreateModel(name='Expense', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('shop', models.ForeignKey('mall.shop', on_delete=models.PROTECT)),
            ('actor', models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)),
            ('category', models.CharField(max_length=60)),
            ('amount', models.DecimalField(max_digits=12, decimal_places=2)),
            ('description', models.TextField(blank=True)),
            ('reference', models.CharField(max_length=120, blank=True)),
            ('created', models.DateTimeField(default=timezone.now))
        ], options={}),
        migrations.CreateModel(name='AuditEvent', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('shop', models.ForeignKey('mall.shop', on_delete=models.PROTECT)),
            ('actor', models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)),
            ('action', models.CharField(max_length=100)),
            ('detail', models.TextField()),
            ('created', models.DateTimeField(auto_now_add=True))
        ], options={})
    ]
