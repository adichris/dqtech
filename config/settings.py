from oscar.defaults import *
import os
from pathlib import Path
import dj_database_url
BASE_DIR=Path(__file__).resolve().parent.parent
DEBUG=os.getenv('DEBUG','0')=='1'
SECRET_KEY=os.environ.get('SECRET_KEY','development-only-change-before-production')
if not DEBUG and SECRET_KEY=='development-only-change-before-production':
    raise RuntimeError('Set SECRET_KEY or use DEBUG=1 for local development')
ALLOWED_HOSTS=os.getenv('ALLOWED_HOSTS','localhost,127.0.0.1').split(',')
INSTALLED_APPS=['unfold','django.contrib.admin','django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles','mall']
MIDDLEWARE=['django.middleware.security.SecurityMiddleware','whitenoise.middleware.WhiteNoiseMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware','django.contrib.messages.middleware.MessageMiddleware','django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF='config.urls'
TEMPLATES=[{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[BASE_DIR/'templates'],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages','mall.views.cart_context','mall.context_processors.branding','mall.context_processors.my_shop']}}]
DATABASES={'default':dj_database_url.config(default='sqlite:///'+str(BASE_DIR/'db.sqlite3'))}
AUTH_PASSWORD_VALIDATORS=[{'NAME':'django.contrib.auth.password_validation.MinimumLengthValidator'},{'NAME':'django.contrib.auth.password_validation.CommonPasswordValidator'}]
STATIC_URL='/static/'
STATIC_ROOT=BASE_DIR/'staticfiles'
STATICFILES_DIRS=[BASE_DIR/'static']
DEFAULT_AUTO_FIELD='django.db.models.BigAutoField'
LOGIN_URL='/login/'
LOGIN_REDIRECT_URL='/seller/'
LOGOUT_REDIRECT_URL='/'
USE_TZ=True
TIME_ZONE='Africa/Accra'
SESSION_COOKIE_HTTPONLY=True
SESSION_COOKIE_SECURE=not DEBUG
CSRF_COOKIE_SECURE=not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF=True
X_FRAME_OPTIONS='DENY'
CELERY_BROKER_URL=os.getenv('REDIS_URL','redis://redis:6379/0')

GATEWAY_ENCRYPTION_KEY=os.environ.get('GATEWAY_ENCRYPTION_KEY','')
PUBLIC_BASE_URL=os.environ.get('PUBLIC_BASE_URL','http://127.0.0.1:8008')
EMAIL_BACKEND=os.getenv('EMAIL_BACKEND','django.core.mail.backends.console.EmailBackend' if DEBUG else 'django.core.mail.backends.smtp.EmailBackend')
DEFAULT_FROM_EMAIL=os.getenv('DEFAULT_FROM_EMAIL','noreply@example.invalid')
EMAIL_HOST=os.getenv('EMAIL_HOST','localhost')
EMAIL_PORT=int(os.getenv('EMAIL_PORT','587'))
EMAIL_HOST_USER=os.getenv('EMAIL_HOST_USER','')
EMAIL_HOST_PASSWORD=os.getenv('EMAIL_HOST_PASSWORD','')
EMAIL_USE_TLS=os.getenv('EMAIL_USE_TLS','1')=='1'
EMAIL_USE_SSL=os.getenv('EMAIL_USE_SSL','0')=='1'
EMAIL_TIMEOUT=15

CSRF_TRUSTED_ORIGINS=[x for x in os.getenv('CSRF_TRUSTED_ORIGINS','').split(',') if x]
SECURE_SSL_REDIRECT=os.getenv('SECURE_SSL_REDIRECT','0' if DEBUG else '1')=='1'

# Public identity. Set the system name here; templates never hard-code it.
SYSTEM_NAME='DQTech Digital Shopping Mall'
SYSTEM_TAGLINE='Your Business. Your Store. Connected to the World.'
SYSTEM_COMPANY='Digital Quotient Technologies Ltd'
SYSTEM_LOGO='brand/dqtech-logo.png'

from oscar import INSTALLED_APPS as OSCAR_APPS
INSTALLED_APPS += [name for name in OSCAR_APPS if name not in INSTALLED_APPS]
INSTALLED_APPS=[('commerce.address.apps.AddressConfig' if name=='oscar.apps.address.apps.AddressConfig' or name=='oscar.apps.address' else name) for name in INSTALLED_APPS]
INSTALLED_APPS += ['sorl.thumbnail']
SITE_ID=1
OSCAR_SHOP_NAME=SYSTEM_NAME
OSCAR_SHOP_TAGLINE=SYSTEM_TAGLINE
OSCAR_DEFAULT_CURRENCY='GHS'
OSCAR_INITIAL_ORDER_STATUS='Awaiting payment'
OSCAR_INITIAL_LINE_STATUS='Awaiting payment'
HAYSTACK_CONNECTIONS={'default':{'ENGINE':'haystack.backends.simple_backend.SimpleEngine'}}
MEDIA_URL='/media/'
MEDIA_ROOT=BASE_DIR/'media'
MIDDLEWARE += ['mall.middleware.OscarStaffOnlyMiddleware']
TEMPLATES[0]['OPTIONS']['context_processors'] += ['mall.context_processors.oscar_staff_context']

if os.getenv('TRUST_PROXY_HTTPS','0')=='1':
    SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https')

if DEBUG:
    MIDDLEWARE=[middleware for middleware in MIDDLEWARE if middleware!='whitenoise.middleware.WhiteNoiseMiddleware']

# Browser-only current-device reverse geocoding; set empty to disable.
GEO_LOOKUP_URL=os.getenv('GEO_LOOKUP_URL','https://api.bigdatacloud.net/data/reverse-geocode-client')

# Version shown in the user's supplied Meta Messages API reference; configurable.
WHATSAPP_GRAPH_VERSION=os.getenv('WHATSAPP_GRAPH_VERSION','v27.0')

PHONENUMBER_DEFAULT_REGION='GH'
OSCAR_REQUIRED_ADDRESS_FIELDS=['first_name','line1','line4','country']

# Supported Oscar app extensions; schema remains the upstream order/partner schema.
INSTALLED_APPS=[('commerce.partner.apps.PartnerConfig' if name in ['oscar.apps.partner','oscar.apps.partner.apps.PartnerConfig'] else 'commerce.order.apps.OrderConfig' if name in ['oscar.apps.order','oscar.apps.order.apps.OrderConfig'] else name) for name in INSTALLED_APPS]
MIGRATION_MODULES={'partner':'oscar.apps.partner.migrations','order':'oscar.apps.order.migrations'}
OSCAR_ORDER_STATUS_PIPELINE={
    'Awaiting payment':('Paid','Cancelled'),
    'Confirmed':('Preparing','Cancelled'),
    'Paid':('Preparing','Refunded'),
    'Preparing':('Dispatched','Refunded','Cancelled'),
    'Dispatched':('Delivered','Refunded','Cancelled'),
    'Delivered':('Refunded',),'Cancelled':(),'Refunded':(),
}
OSCAR_LINE_STATUS_PIPELINE=OSCAR_ORDER_STATUS_PIPELINE
OSCAR_ORDER_STATUS_CASCADE={name:name for name in OSCAR_ORDER_STATUS_PIPELINE}
OSCAR_FROM_EMAIL=DEFAULT_FROM_EMAIL

# ---------------------------------------------------------------------------
# Production hardening
# ---------------------------------------------------------------------------
import sys
from urllib.parse import urlparse as _urlparse

SECURE_HSTS_SECONDS=int(os.getenv('SECURE_HSTS_SECONDS','0' if DEBUG else '3600'))  # raise to 31536000 once HTTPS is stable
SECURE_HSTS_INCLUDE_SUBDOMAINS=os.getenv('SECURE_HSTS_INCLUDE_SUBDOMAINS','0')=='1'
SECURE_HSTS_PRELOAD=os.getenv('SECURE_HSTS_PRELOAD','0')=='1'
SECURE_REFERRER_POLICY='same-origin'
SESSION_COOKIE_SAMESITE='Lax'

# Shared cache: required in production so rate limits are counted across all workers.
if os.getenv('REDIS_URL'):
    CACHES={'default':{'BACKEND':'django.core.cache.backends.redis.RedisCache','LOCATION':os.environ['REDIS_URL'],'KEY_PREFIX':'dqtech'}}
else:
    CACHES={'default':{'BACKEND':'django.core.cache.backends.locmem.LocMemCache','LOCATION':'dqtech'}}

# Abuse protection. Number of trusted reverse proxies that append to X-Forwarded-For
# (1 behind a single nginx/Caddy). Leave 0 when Django is reached directly.
TRUSTED_PROXY_COUNT=int(os.getenv('TRUSTED_PROXY_COUNT','0'))
RATELIMIT_ENABLED=os.getenv('RATELIMIT_ENABLED','1')=='1' and sys.argv[1:2]!=['test']  # tests opt in explicitly
LOGIN_FAILURES_PER_ACCOUNT=10
LOGIN_FAILURES_PER_IP=50  # campuses share NAT addresses; keep this generous
PASSWORD_RESETS_PER_EMAIL=3

# Stock holds. Unpaid online/manual orders are cancelled after this many hours (0 disables).
UNPAID_ORDER_HOLD_HOURS=int(os.getenv('UNPAID_ORDER_HOLD_HOURS','48'))
MAX_OPEN_UNPAID_ORDERS=10
MAX_OPEN_UNPAID_ORDERS_PER_SHOP=3

# Optional allow-list of seller image hosts, e.g. "res.cloudinary.com,images.unsplash.com". Empty = any HTTPS host.
PRODUCT_IMAGE_HOSTS=[h.strip().lower() for h in os.getenv('PRODUCT_IMAGE_HOSTS','').split(',') if h.strip()]

def _origin(url):
    parsed=_urlparse(url or '')
    return f'{parsed.scheme}://{parsed.netloc}' if parsed.scheme and parsed.netloc else ''
# Inline handlers and Alpine.js still need 'unsafe-inline'/'unsafe-eval'; the policy blocks
# third-party scripts, plugins, framing, <base> hijacking and off-site form posts.
CONTENT_SECURITY_POLICY=os.getenv('CONTENT_SECURITY_POLICY','; '.join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com data:",
    "img-src 'self' https: data: blob:",
    ("connect-src 'self' "+_origin(GEO_LOOKUP_URL)).strip(),
    "form-action 'self' https://checkout.paystack.com",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "object-src 'none'",
]))
MIDDLEWARE.insert(1,'mall.security.SecurityHeadersMiddleware')

ADMINS=[tuple(item.split(':',1)) for item in os.getenv('ADMINS','').split(',') if ':' in item]  # "Name:email,..."
SERVER_EMAIL=os.getenv('SERVER_EMAIL',DEFAULT_FROM_EMAIL)
LOGGING={
    'version':1,'disable_existing_loggers':False,
    'formatters':{'plain':{'format':'%(asctime)s %(levelname)s %(name)s %(message)s'}},
    'handlers':{
        'console':{'class':'logging.StreamHandler','formatter':'plain'},
        'mail_admins':{'class':'django.utils.log.AdminEmailHandler','level':'ERROR','filters':['require_debug_false']},
    },
    'filters':{'require_debug_false':{'()':'django.utils.log.RequireDebugFalse'}},
    'root':{'handlers':['console'],'level':os.getenv('LOG_LEVEL','INFO')},
    'loggers':{
        'django.request':{'handlers':['console']+(['mail_admins'] if ADMINS else []),'level':'WARNING','propagate':False},
        'django.security':{'handlers':['console']+(['mail_admins'] if ADMINS else []),'level':'WARNING','propagate':False},
        'mall':{'handlers':['console'],'level':os.getenv('LOG_LEVEL','INFO'),'propagate':False},
        'oscar':{'handlers':['console'],'level':'WARNING','propagate':False},
    },
}

# Mall Pay: the marketplace's own Paystack account. Sellers get Paystack subaccounts and each
# payment is split automatically, deducting commission at source. Webhook: /webhooks/paystack/platform/
PLATFORM_PAYSTACK_SECRET=os.getenv('PLATFORM_PAYSTACK_SECRET','')
PLATFORM_PAYSTACK_CURRENCIES=[c.strip().upper() for c in os.getenv('PLATFORM_PAYSTACK_CURRENCIES','GHS').split(',') if c.strip()]
# Sellers may connect their own Paystack account only after this track record (see mall/eligibility.py).
OWN_GATEWAY_MIN_DAYS=int(os.getenv('OWN_GATEWAY_MIN_DAYS','90'))
OWN_GATEWAY_MIN_DELIVERED_ORDERS=int(os.getenv('OWN_GATEWAY_MIN_DELIVERED_ORDERS','25'))
OWN_GATEWAY_MAX_REFUND_RATE=os.getenv('OWN_GATEWAY_MAX_REFUND_RATE','0.10')
OWN_GATEWAY_OVERDUE_DAYS=int(os.getenv('OWN_GATEWAY_OVERDUE_DAYS','30'))
