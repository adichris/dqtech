from urllib.parse import urlencode
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render,redirect,get_object_or_404
from django.views.decorators.http import require_GET,require_POST
from .models import Shop,Product,Review,Wishlist,AuditEvent
from .forms import ReviewForm
from .favourites import saved_lines,save_find
from .discovery import catalogue,suggestions,can_review
from .security import ratelimit
@require_GET
@ratelimit('autocomplete',300,60,methods=('GET',))
def autocomplete(request):
    q=request.GET.get('q','').strip()[:100]
    products=catalogue().filter(name__icontains=q).order_by('-rating_count','name')[:6] if len(q)>=2 else []
    shops=Shop.objects.filter(active=True,name__icontains=q).order_by('name')[:3] if len(q)>=2 else []
    response=render(request,'fragments/autocomplete.html',{'matches':products,'matching_shops':shops,'search_query':q})
    response['Cache-Control']='no-store'
    return response
@require_GET
def quick_view(request,pk):
    p=get_object_or_404(catalogue(),pk=pk)
    return render(request,'fragments/quick_view.html',{'product':p})
@require_POST
def save_product(request,pk):
    p=get_object_or_404(Product,pk=pk,active=True,shop__active=True)
    if not request.user.is_authenticated:
        response=HttpResponse();response['HX-Redirect']='/login/?'+urlencode({'next':'/product/'+str(pk)+'/'})
        return response if request.headers.get('HX-Request')=='true' else redirect(response['HX-Redirect'])
    with transaction.atomic():
        # Serialize toggles per user to avoid duplicate/concurrent additions.
        from django.contrib.auth import get_user_model
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        existing=saved_lines(request.user).filter(product=p.oscar_product).first()
        if existing:existing.delete();saved=False
        else:save_find(request.user,p);saved=True
    if request.headers.get('HX-Request')=='true':return render(request,'fragments/save_button.html',{'p':p,'is_saved':saved})
    return redirect('detail',pk=pk)
@login_required
def wishlist(request):
    return render(request,'wishlist.html',{'products':catalogue().filter(oscar_product_id__in=saved_lines(request.user).values('product_id')).order_by('-pk')})
@login_required
@require_POST
@ratelimit('review',20,3600,key='user')
@transaction.atomic
def submit_review(request,pk):
    p=get_object_or_404(Product,pk=pk,active=True,shop__active=True)
    if not can_review(request.user,p):
        messages.error(request,'Reviews are available after a delivered purchase. Sellers cannot review their own products.');return redirect('detail',pk=pk)
    from django.contrib.auth import get_user_model
    get_user_model().objects.select_for_update().get(pk=request.user.pk)
    existing=Review.objects.filter(user=request.user,product=p.oscar_product).first()
    form=ReviewForm(request.POST,instance=existing or Review(user=request.user,product=p.oscar_product))
    if form.is_valid():
        review=form.save(commit=False);review.user=request.user;review.product=p.oscar_product;review.save()
        messages.success(request,'Your verified-purchase review has been saved.')
    else:
        if request.headers.get('HX-Request')=='true':return render(request,'fragments/review_form.html',{'form':form,'product':p},status=422)
        messages.error(request,'Check your rating, title and review text.')
    return redirect('detail',pk=pk)
@require_GET
def shops(request):
    qs=Shop.objects.filter(active=True)
    q=request.GET.get('q','').strip()
    if q:qs=qs.filter(name__icontains=q)
    return render(request,'shops.html',{'shops':qs,'q':q})

@require_GET
def search_page(request):
    from .search import search_context
    context=search_context(request)
    partial=request.headers.get('HX-Request')=='true' and request.headers.get('HX-Request-Type')!='full' and request.headers.get('HX-History-Restore-Request')!='true'
    response=render(request,'search_content.html' if partial else 'search.html',context)
    response['Vary']='HX-Request, HX-Request-Type, HX-History-Restore-Request'
    return response

@login_required
@require_POST
@ratelimit('report',10,3600,key='user')
def report_listing(request,pk):
    from .models import ListingReport
    p=get_object_or_404(Product,pk=pk,active=True,shop__active=True)
    reason=request.POST.get('reason','')
    allowed=[value for value,label in ListingReport._meta.get_field('reason').choices]
    if reason not in allowed:messages.error(request,'Choose a reason for your report.')
    elif ListingReport.objects.filter(product=p,user=request.user,state='Pending').exists():messages.info(request,'Your report is already pending review.')
    else:
        ListingReport.objects.create(product=p,user=request.user,reason=reason,notes=request.POST.get('notes','')[:2000])
        messages.success(request,'Your report was sent to the marketplace team for review.')
    return redirect('detail',pk=pk)
