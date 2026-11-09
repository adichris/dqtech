import os
from django.core.management.base import BaseCommand,CommandError
from django.contrib.auth import get_user_model
from django.conf import settings
from mall.models import Shop,Product,PaymentMethod
class Command(BaseCommand):
    help='Create sample catalogue. Requires DEBUG=1 and DEMO_PASSWORD.'
    def handle(self,*args,**kwargs):
        password=os.environ.get('DEMO_PASSWORD')
        if not settings.DEBUG or not password:raise CommandError('Set DEBUG=1 and DEMO_PASSWORD to seed local demo data.')
        entries=[('Ama Studio','ama-studio','Ama','Handmade style with a story.','Accra, Ghana','Independent'),('Everyday Objects','everyday-objects','Kojo','Considered essentials for your space.','Kumasi, Ghana','Independent'),('Campus Collective','campus-collective','Akua','The student edit. By students, for students.','Legon, Accra','STUDSMALL'),('The Tech Corner','tech-corner','Kofi','Useful technology for everyday life.','Tema, Ghana','Independent')]
        shops=[]
        for name,slug,username,desc,loc,prog in entries:
            u,created=get_user_model().objects.get_or_create(username=username.lower())
            if created:u.set_password(password);u.save()
            s,_=Shop.objects.get_or_create(slug=slug,defaults={'owner':u,'name':name,'description':desc,'location':loc,'programme':prog,'active':True})
            PaymentMethod.objects.get_or_create(shop=s,label='Pay on collection',defaults={'kind':'collection','instructions':'Demo only. Arrange collection with the seller. No online payment is processed.'})
            shops.append(s)
        products=[(0,'Everyday commuter backpack','Fashion','185.00','photo-1553062407-98eeb64c6a62'),(1,'Artisan ceramic breakfast set','Home & Living','240.00','photo-1578749556568-bc2c40e68b61'),(0,'Classic everyday cotton shirt','Fashion','320.00','photo-1598033129183-c4f50c736f10'),(3,'Wireless over-ear headphones','Electronics','450.00','photo-1546435770-a3e426bf472b'),(1,'Minimal desk lamp','Home & Living','275.00','photo-1507473885765-e6ed057f782c'),(2,'Campus everyday backpack','Campus essentials','210.00','photo-1622260614153-03223fb72052'),(0,'The crafted accent chair','Home & Living','165.00','photo-1594224457860-23bdb45f8e3d'),(2,'Pre-loved study desk','Campus essentials','350.00','photo-1518455027359-f3f8164ba6bd')]
        for i,name,cat,price,img in products:
            Product.objects.get_or_create(shop=shops[i],name=name,defaults={'category':cat,'price':price,'stock':12,'description':'A considered find from an independent seller. Demo catalogue item; contact your seller for materials, dimensions and collection details.','image':'https://images.unsplash.com/'+img+'?auto=format&fit=crop&w=700&q=85','classified':name.startswith('Pre-loved')})
        self.stdout.write(self.style.SUCCESS('Demo catalogue ready. Seller logins: ama, kojo, akua, kofi. Password comes from DEMO_PASSWORD.'))
