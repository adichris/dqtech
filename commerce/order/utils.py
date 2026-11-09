from oscar.apps.order.utils import OrderCreator as CoreOrderCreator,OrderNumberGenerator  # noqa: F401

class OrderCreator(CoreOrderCreator):
    def create_line_models(self,order,basket_line,extra_line_fields=None):
        values={'status':order.status,**(extra_line_fields or {})}
        return super().create_line_models(order,basket_line,values)
