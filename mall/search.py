from decimal import Decimal
from urllib.parse import urlencode
from django import forms
from django.core.paginator import Paginator
from django.db.models import Q,F
from .discovery import catalogue
from .catalogue import CATEGORIES
MARKETS={'GH':('Ghana','GHS'),'NG':('Nigeria','NGN'),'US':('United States','USD'),'GB':('United Kingdom','GBP')}
class SearchForm(forms.Form):
    q=forms.CharField(required=False,max_length=120,label='What are you looking for?')
    category=forms.ChoiceField(required=False,choices=[('','All categories')]+[(x,x) for x in CATEGORIES])
    country=forms.ChoiceField(required=False,choices=[('','All markets')]+[(k,v[0]) for k,v in MARKETS.items()])
    currency=forms.ChoiceField(required=False,choices=[('','All currencies')]+[(v[1],v[1]) for v in MARKETS.values()])
    min_price=forms.DecimalField(required=False,min_value=0,max_digits=12,decimal_places=2,label='From')
    max_price=forms.DecimalField(required=False,min_value=0,max_digits=12,decimal_places=2,label='To')
    rating=forms.ChoiceField(required=False,choices=[('','Any rating'),('4','4 stars & up'),('3','3 stars & up'),('2','2 stars & up')])
    in_stock=forms.BooleanField(required=False,label='In stock only')
    verified=forms.BooleanField(required=False,label='Verified sellers only')
    listing=forms.ChoiceField(required=False,choices=[('','All listings'),('products','Buy online'),('classifieds','Classifieds')])
    campus=forms.BooleanField(required=False,label='Campus businesses')
    sort=forms.ChoiceField(required=False,choices=[('relevance','Recommended'),('newest','Newest arrivals'),('price_low','Price: low to high'),('price_high','Price: high to low'),('rating','Highest rated')])
    def clean(self):
        data=super().clean();low=data.get('min_price');high=data.get('max_price')
        country=data.get('country');currency=data.get('currency')
        if country:
            expected=MARKETS[country][1]
            if currency and currency!=expected:self.add_error('currency','This currency does not match the selected market.')
            data['currency']=currency or expected
        if low is not None and high is not None and low>high:self.add_error('max_price','The upper price must be at least the lower price.')
        if (low is not None or high is not None or data.get('sort') in ['price_low','price_high']) and not data.get('currency'):
            self.add_error('currency','Choose a market or currency when comparing prices.')
        return data

def filtered(form):
    qs=catalogue()
    if not form.is_valid():return qs.none()
    d=form.cleaned_data;q=d.get('q','')
    if q:
        for word in q.split()[:8]:qs=qs.filter(Q(name__icontains=word)|Q(description__icontains=word)|Q(shop__name__icontains=word))
    if d.get('category'):qs=qs.filter(category=d['category'])
    if d.get('country'):qs=qs.filter(shop__country=d['country'])
    if d.get('currency'):qs=qs.filter(shop__currency=d['currency'])
    if d.get('min_price') is not None:qs=qs.filter(price__gte=d['min_price'])
    if d.get('max_price') is not None:qs=qs.filter(price__lte=d['max_price'])
    if d.get('rating'):qs=qs.filter(rating_average__gte=int(d['rating']))
    if d.get('in_stock'):qs=qs.filter(stock__gt=0)
    if d.get('verified'):qs=qs.filter(shop__verified=True)
    if d.get('listing')=='classifieds':qs=qs.filter(classified=True)
    if d.get('listing')=='products':qs=qs.filter(classified=False)
    if d.get('campus'):qs=qs.filter(Q(category='Campus essentials')|Q(shop__programme__in=['STUDSMALL','GradVenture','CASMET']))
    order=d.get('sort') or 'relevance'
    if order=='rating':return qs.order_by(F('rating_average').desc(nulls_last=True),'-rating_count','-pk')
    if order=='relevance':return qs.order_by('-rating_count','-pk')
    return qs.order_by({'newest':'-pk','price_low':'price','price_high':'-price'}.get(order,'-pk'),'pk')

def search_context(request):
    data=request.GET.copy()
    if data.get('mode')=='classifieds':data['listing']='classifieds'
    if data.get('mode')=='campus':data['campus']='on'
    form=SearchForm(data);qs=filtered(form);page=Paginator(qs,12).get_page(request.GET.get('page'))
    base=data.copy();base.pop('page',None)
    def url(number):values=base.copy();values['page']=number;return '/search/?'+values.urlencode()
    chips=[]
    for key in ['q','category','country','currency','min_price','max_price','rating','in_stock','verified','listing','campus']:
        value=data.get(key)
        if value:
            params=base.copy();params.pop(key,None)
            label=dict(form.fields[key].choices).get(value,value) if hasattr(form.fields[key],'choices') else value
            if key=='min_price':label='From '+value
            elif key=='max_price':label='Up to '+value
            elif key in ['in_stock','verified','campus']:label=form.fields[key].label
            chips.append({'label':label,'url':'/search/?'+params.urlencode()})
    return {'form':form,'products':page.object_list,'page_obj':page,'result_count':page.paginator.count,'q':data.get('q',''),'active_filters':chips,'page_links':[{'number':n,'url':url(n),'current':n==page.number} for n in page.paginator.get_elided_page_range(page.number,on_each_side=2,on_ends=1) if isinstance(n,int)],'previous_url':url(page.previous_page_number()) if page.has_previous() else None,'next_url':url(page.next_page_number()) if page.has_next() else None}
