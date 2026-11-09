from oscar.core.loading import get_model

def saved_lines(user):
    return get_model('wishlists','Line').objects.filter(wishlist__owner=user,wishlist__name='Saved finds',wishlist__visibility='Private')

def save_find(user,product):
    WishList=get_model('wishlists','WishList')
    wishlist=WishList.objects.filter(owner=user,name='Saved finds',visibility=WishList.PRIVATE).first()
    if not wishlist:wishlist=WishList.objects.create(owner=user,name='Saved finds',visibility=WishList.PRIVATE)
    if not wishlist.lines.filter(product=product.oscar_product).exists():wishlist.add(product.oscar_product)
    return wishlist
