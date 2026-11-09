from oscar.apps.shipping.methods import FixedPrice

class MerchantShipping(FixedPrice):
    """Oscar shipping method with tenant pricing and collection metadata."""
    def __init__(self,shop,fee,fulfilment='delivery'):
        super().__init__(charge_excl_tax=fee,charge_incl_tax=fee)
        self.code=f'merchant-{shop.pk}-{fulfilment}'
        self.name=f'{shop.name}: '+('Click & collect' if fulfilment=='collection' else 'Delivery')
