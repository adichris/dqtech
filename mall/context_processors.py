from django.conf import settings
from .models import Product
from .favourites import saved_lines

def my_shop(request):
    from django.utils.functional import SimpleLazyObject
    from .models import Shop
    if not request.user.is_authenticated:return {'my_shop':None}
    return {'my_shop':SimpleLazyObject(lambda:Shop.objects.filter(owner=request.user).first())}

def branding(request):
    saved=list(Product.objects.filter(oscar_product_id__in=saved_lines(request.user).values('product_id')).values_list('pk',flat=True)) if request.user.is_authenticated else []
    return {'system_name':settings.SYSTEM_NAME,'system_tagline':settings.SYSTEM_TAGLINE,'system_company':settings.SYSTEM_COMPANY,'system_logo':settings.SYSTEM_LOGO,'saved_product_ids':saved}

def oscar_staff_context(request):
    if not request.path.startswith('/engine/') or not request.user.is_staff:return {}
    from oscar.core.context_processors import metadata
    from oscar.apps.search.context_processors import search_form
    from oscar.apps.checkout.context_processors import checkout
    from oscar.apps.communication.notifications.context_processors import notifications
    context={}
    for processor in [metadata,search_form,checkout,notifications]:context.update(processor(request))
    return context
