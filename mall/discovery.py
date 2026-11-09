from django.db.models import Avg,Count,Q,Case,When,IntegerField
from .models import Product,OrderLine

def catalogue():
    return Product.objects.filter(active=True,shop__active=True).select_related('shop').annotate(rating_average=Avg('oscar_product__reviews__score',filter=Q(oscar_product__reviews__status=1)),rating_count=Count('oscar_product__reviews',filter=Q(oscar_product__reviews__status=1)))
def suggestions(product,limit=4):
    return catalogue().filter(Q(category=product.category)|Q(shop_id=product.shop_id)).exclude(pk=product.pk).annotate(relevance=Case(When(category=product.category,then=2),default=1,output_field=IntegerField())).order_by('-relevance','-rating_count','-pk')[:limit]
def can_review(user,product):
    return user.is_authenticated and product.shop.owner_id!=user.pk and OrderLine.objects.filter(product=product.oscar_product,order__user=user,order__status='Delivered').exists()
