import secrets
from decimal import Decimal
from django.shortcuts import render,redirect,get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.views.decorators.http import require_POST
from django.db.models import Q,Sum,Exists,OuterRef
from oscar.core.loading import get_model
from .models import *
from .forms import *
from .services import checkout
from .discovery import catalogue,suggestions,can_review
from .baskets import read_cart,write_cart
from .security import ratelimit
from .catalogue import CATEGORIES
def cart_context(request): return {'bag_count':sum(read_cart(request).values()),'categories':CATEGORIES}
def home(request):
    products=catalogue()
    country=request.GET.get('country','')
    if country:products=products.filter(shop__country=country)
    q=request.GET.get('q','');category=request.GET.get('category','');mode=request.GET.get('mode','')
    if q: products=products.filter(Q(name__icontains=q)|Q(shop__name__icontains=q)|Q(description__icontains=q))
    if category: products=products.filter(category=category)
    if mode=='classifieds': products=products.filter(classified=True)
    if mode=='campus': products=products.filter(Q(category='Campus essentials')|Q(shop__programme__in=['STUDSMALL','GradVenture','CASMET']))
    sort=request.GET.get('sort','newest')
    ordering={'newest':'-pk','price_low':'price','price_high':'-price','rating':'-rating_average'}.get(sort,'-pk')
    products=products.order_by(ordering,'pk')[:48]
    context={'sort':sort,'products':products,'q':q,'selected':category,'mode':mode,'shop_count':Shop.objects.filter(active=True).count()}
    response=render(request,'discovery.html' if request.headers.get('HX-Request')=='true' else 'home.html',context)
    response['Vary']='HX-Request'
    return response
@ratelimit('enquiry',20,3600,key='user')
def detail(request,pk):
    p=get_object_or_404(catalogue(),pk=pk)
    if request.method=='POST' and request.user.is_authenticated:
        msg=request.POST.get('message','').strip()
        if msg: Enquiry.objects.create(sender=request.user,product=p,message=msg[:4000]);messages.success(request,'Your enquiry has been sent to the seller.')
        return redirect('detail',pk=pk)
    from django.db.models import Count
    histogram={row['score']:row['n'] for row in p.reviews.filter(status=Review.APPROVED).values('score').annotate(n=Count('pk'))}
    distribution=[{'stars':stars,'count':histogram.get(stars,0),'percent':round(histogram.get(stars,0)*100/p.rating_count) if p.rating_count else 0} for stars in range(5,0,-1)]
    return render(request,'detail.html',{'rating_distribution':distribution,'product':p,'reviews':p.reviews.filter(status=Review.APPROVED).select_related('user').annotate(verified_purchase=Exists(get_model('order','Line').objects.filter(product_id=OuterRef('product_id'),order__user_id=OuterRef('user_id'),order__status='Delivered'))).order_by('-date_created'),'can_review':can_review(request.user,p),'review_form':ReviewForm(instance=Review.objects.filter(product=p.oscar_product,user=request.user).first()) if request.user.is_authenticated else None,'products':suggestions(p)})
def store(request,slug):
    s=get_object_or_404(Shop,slug=slug,active=True)
    return render(request,'store.html',{'shop':s,'products':catalogue().filter(shop=s)})
@require_POST
@ratelimit('bag-add',120,60)
def add(request,pk):
    p=get_object_or_404(Product,pk=pk,active=True,shop__active=True,classified=False)
    cart=read_cart(request);
    try:requested=int(request.POST.get('quantity','1'))
    except (ValueError,TypeError):requested=0
    qty=cart.get(str(pk),0)+requested
    error=requested<1 or qty>min(p.stock,99)
    if not error:
        cart[str(pk)]=qty;write_cart(request,cart)
        text=p.name+' was added to your bag.'
    else:text='No more stock is available for '+p.name+'.'
    if not error and request.POST.get('action')=='buy_now':
        if request.headers.get('HX-Request')=='true':
            response=HttpResponse();response['HX-Redirect']='/bag/';return response
        return redirect('bag')
    if request.headers.get('HX-Request')=='true':
        return render(request,'fragments/cart_result.html',{'text':text,'error':error},status=422 if error else 200)
    if error:messages.error(request,text)
    else:messages.success(request,text)
    return redirect('bag')
@require_POST
def remove(request,pk):
    from .basket_views import remove_item
    return remove_item(request,pk)

def bag(request):
    from .basket_views import basket
    return basket(request)

@ratelimit('signup',20,3600)
def signup(request):
    f=RegistrationForm(request.POST or None)
    if request.method=='POST' and f.is_valid(): login(request,f.save());return redirect('home')
    return render(request,'form.html',{'form':f,'title':'Make yourself at home','subtitle':'Create your account to shop or start selling.'})
@login_required
def onboard(request):
    if Shop.objects.filter(owner=request.user).exists():return redirect('seller')
    f=ShopForm(request.POST or None)
    if request.method=='POST' and f.is_valid():
        s=f.save(commit=False);s.owner=request.user;s.save();messages.success(request,'Your shop has been created. Add products and payments while an administrator verifies and activates your store.');return redirect('seller')
    return render(request,'form.html',{'form':f,'title':'Your business. Your store.','subtitle':'First three calendar months commission-free. Then 3% on qualifying marketplace sales.'})
@login_required
def seller(request):
    s=Shop.objects.filter(owner=request.user).first()
    if not s:
        if StaffMembership.objects.filter(user=request.user,active=True).exists():return redirect('workspaces')
        return redirect('onboard')
    all_orders=Order.objects.filter(shop=s).select_related('payment_method','oscar_order').order_by('-created','-pk')
    page=paginate(request,all_orders)
    return render(request,'seller.html',{'shop':s,'orders':page.object_list,'page_obj':page,'order_count':page.paginator.count,'enquiries':Enquiry.objects.filter(product__shop=s).select_related('sender','product'),'revenue':Receipt.objects.filter(shop=s).exclude(order__oscar_order__status='Refunded').aggregate(v=Sum('amount'))['v'] or 0})
def paginate(request,queryset,per_page=25):
    from django.core.paginator import Paginator
    return Paginator(queryset,per_page).get_page(request.GET.get('page'))
@login_required
def edit_product(request,pk=None):
    s=get_object_or_404(Shop,owner=request.user)
    p=get_object_or_404(Product,pk=pk,shop=s) if pk else None
    f=ProductForm(request.POST or None,instance=p)
    if request.method=='POST' and f.is_valid(): obj=f.save(commit=False);obj.shop=s;obj.save();return redirect('seller')
    return render(request,'form.html',{'form':f,'title':'Edit product' if p else 'Add a product'})
@login_required
def payments(request):
    s=get_object_or_404(Shop,owner=request.user);f=PaymentForm(request.POST or None)
    if request.method=='POST' and f.is_valid():obj=f.save(commit=False);obj.shop=s;obj.save();messages.success(request,'Payment instructions saved.');return redirect('payments')
    return render(request,'payments.html',{'form':f,'shop':s})
@login_required
@require_POST
def payment_toggle(request,pk):
    p=get_object_or_404(PaymentMethod,pk=pk,shop__owner=request.user)
    if p.kind=='cod':messages.info(request,'Cash on Delivery is a platform default and is always available.')
    else:p.active=not p.active;p.save()
    return redirect('payments')
@login_required
def orders(request): return render(request,'orders.html',{'orders':Order.objects.filter(buyer=request.user).select_related('shop','oscar_order','payment_method').order_by('-created','-pk')})
@login_required
@require_POST
def order_update(request,pk):
    o=get_object_or_404(Order,pk=pk)
    target=request.POST.get('status')
    access_shop(request,o.shop.slug,'finance' if target=='Paid' else 'orders')
    from .order_actions import confirm_payment,advance
    from django.db import IntegrityError
    from .order_actions import cancel
    try:
        if target=='Cancelled':
            cancel(o.pk,request.user,request.POST.get('reason','').strip() or 'Cancelled by the seller.')
            messages.success(request,'Order cancelled and stock restored. The customer has been notified.');return redirect('seller')
        if target=='Paid':confirm_payment(o.pk,request.user,request.POST.get('receipt_reference') or o.payment_reference)
        else:advance(o.pk,request.user,target,request.POST.get('delivery_reference',''))
        messages.success(request,'Order updated.')
    except (ValueError,IntegrityError) as e:messages.error(request,str(e) if isinstance(e,ValueError) else 'This receipt reference has already been used.')
    return redirect('seller')
@login_required
@require_POST
def reference(request,pk):
    o=get_object_or_404(Order,pk=pk,buyer=request.user)
    if o.status!='Awaiting payment' or o.cash_on_delivery:messages.error(request,'This order does not need a payment reference.')
    else:
        o.payment_reference=request.POST.get('reference','')[:150];o.save(update_fields=['payment_reference']);messages.success(request,'Reference sent. Your seller will verify receipt.')
    return redirect('orders')

from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.contrib.auth import get_user_model
import csv
ROLE_ACCESS={'manager':{'overview','finance','expenses','orders','catalogue','support'},'finance':{'overview','finance','expenses'},'support':{'overview','support','orders'},'catalogue':{'overview','catalogue'}}
def access_shop(request,slug,area):
    s=get_object_or_404(Shop,slug=slug)
    if s.owner_id==request.user.pk:return s,True
    membership=StaffMembership.objects.filter(shop=s,user=request.user,active=True).first()
    if not membership or area not in ROLE_ACCESS.get(membership.role,set()): raise PermissionDenied
    return s,'finance' in ROLE_ACCESS.get(membership.role,set())
@login_required
def team(request):
    s=get_object_or_404(Shop,owner=request.user)
    if request.method=='POST':
        if request.POST.get('revoke'):
            member=get_object_or_404(StaffMembership,pk=request.POST['revoke'],shop=s);member.active=False;member.save()
            AuditEvent.objects.create(shop=s,actor=request.user,action='Staff access revoked',detail=str(member.user_id))
        else:
            u=get_user_model().objects.filter(username=request.POST.get('username')).first();role=request.POST.get('role')
            if u and u.pk!=request.user.pk and role in ROLE_ACCESS:
                StaffMembership.objects.update_or_create(shop=s,user=u,defaults={'role':role,'active':True})
                AuditEvent.objects.create(shop=s,actor=request.user,action='Staff role assigned',detail=u.username+' · '+role)
                messages.success(request,'Staff access updated.')
            else:messages.error(request,'Choose an existing account and a valid role. The owner already has full access.')
        return redirect('team')
    return render(request,'team.html',{'shop':s,'members':StaffMembership.objects.filter(shop=s).select_related('user'),'roles':ROLE_ACCESS})
@login_required
def workspaces(request):
    return render(request,'workspaces.html',{'members':StaffMembership.objects.filter(user=request.user,active=True).select_related('shop')})
@login_required
def operations(request,slug,area='overview'):
    if area not in {'overview','finance','expenses','orders','catalogue','support'}:raise PermissionDenied
    s,money=access_shop(request,slug,area)
    f=ExpenseForm(request.POST or None)
    if request.method=='POST':
        if area!='expenses':raise PermissionDenied
        if f.is_valid():
            from django.db import transaction
            from .ledger import post
            with transaction.atomic():
                expense=f.save(commit=False);expense.shop=s;expense.actor=request.user;expense.save()
                post(s,'expense:'+str(expense.pk),'Operating expense',[('operating_expenses',expense.amount,0),('seller_receipts',0,expense.amount)])
                AuditEvent.objects.create(shop=s,actor=request.user,action='Expense recorded',detail=str(expense.pk))
            return redirect('operations',slug=slug,area=area)
    ctx={'shop':s,'area':area,'money':money,'form':f,'access':{'overview','finance','expenses','orders','catalogue','support'} if s.owner_id==request.user.pk else ROLE_ACCESS[StaffMembership.objects.get(shop=s,user=request.user).role]}
    if money:
        paid=Receipt.objects.filter(shop=s).exclude(order__oscar_order__status='Refunded')
        income=paid.aggregate(v=Sum('amount'))['v'] or Decimal('0')
        costs=Expense.objects.filter(shop=s).aggregate(v=Sum('amount'))['v'] or Decimal('0')
        payable=BillingInvoice.objects.filter(shop=s,state='Due').aggregate(v=Sum('amount'))['v'] or Decimal('0')
        ctx.update(income=income,costs=costs,net=income-costs-payable,payable=payable)
    listing={'finance':('orders',lambda:Order.objects.filter(shop=s).select_related('oscar_order').order_by('-created','-pk')),
             'orders':('orders',lambda:Order.objects.filter(shop=s).select_related('oscar_order','buyer').order_by('-created','-pk')),
             'expenses':('expenses',lambda:Expense.objects.filter(shop=s).order_by('-created','-pk')),
             'catalogue':('products',lambda:Product.objects.filter(shop=s).order_by('-pk')),
             'support':('enquiries',lambda:Enquiry.objects.filter(product__shop=s).select_related('product','sender').order_by('-created','-pk'))}
    if area in listing:
        name,rows=listing[area];page=paginate(request,rows());ctx[name]=page.object_list;ctx['page_obj']=page
    return render(request,'operations.html',ctx)
@login_required
def finance_export(request,slug):
    s,_=access_shop(request,slug,'finance')
    response=HttpResponse(content_type='text/csv');response['Content-Disposition']='attachment; filename="finance.csv"'
    writer=csv.writer(response);writer.writerow(['Type','ID','Date','Currency','Amount','Commission','Status'])
    for o in Order.objects.filter(shop=s).order_by('pk'):writer.writerow(['Order',o.pk,o.created.isoformat(),o.currency,o.total,o.commission,o.status])
    for e in Expense.objects.filter(shop=s).order_by('pk'):writer.writerow(['Expense',e.pk,e.created.isoformat(),s.currency,e.amount,0,'Recorded'])
    AuditEvent.objects.create(shop=s,actor=request.user,action='Finance export',detail='Orders and expenses CSV')
    return response
