from oscar.apps.partner.strategy import Default
from oscar.core.loading import get_class

class MarketplaceStrategy(Default):
    def select_stockrecord(self,product):
        listing=getattr(product,'tenant_listing',None)
        if listing is None:return super().select_stockrecord(product)
        return product.stockrecords.filter(partner_id=listing.shop.oscar_partner_id,price_currency=listing.shop.currency).first()
    def availability_policy(self,product,stockrecord):
        listing=getattr(product,'tenant_listing',None)
        if listing and (not listing.shop.active or listing.classified or not product.is_public):
            return get_class('partner.availability','Unavailable')()
        return super().availability_policy(product,stockrecord)

class Selector:
    def strategy(self,request=None,user=None,**kwargs):
        strategy=MarketplaceStrategy(request)
        if user is not None:strategy.user=user
        return strategy
