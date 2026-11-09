from django.db import models
from oscar.apps.address.abstract_models import AbstractUserAddress

class UserAddress(AbstractUserAddress):
    """Oscar address book, with a marketplace label and Ghana-friendly UI aliases."""
    label=models.CharField(max_length=60,default='Home')
    class Meta(AbstractUserAddress.Meta):
        abstract=False
        ordering=['-is_default_for_shipping','-num_orders_as_shipping_address','-date_created','-pk']
    @property
    def data(self):
        return {'recipient':self.name,'phone':str(self.phone_number),'country':self.country_id,'region':self.state,'city':self.line4,'street':self.line1,'landmark':self.line2,'digital_address':self.postcode,'instructions':self.notes}
    @property
    def is_default(self):return self.is_default_for_shipping
    @is_default.setter
    def is_default(self,value):self.is_default_for_shipping=value

# Register the remaining Oscar models unchanged.
from oscar.apps.address.models import *  # noqa: F401,F403,E402
