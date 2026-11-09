from django.http import HttpResponseForbidden
class OscarStaffOnlyMiddleware:
    def __init__(self,get_response):self.get_response=get_response
    def __call__(self,request):
        if request.path.startswith('/engine/'):
            if not request.user.is_authenticated or not request.user.is_staff:return HttpResponseForbidden('Platform staff access required.')
            from oscar.apps.basket.middleware import BasketMiddleware
            return BasketMiddleware(self.get_response)(request)
        return self.get_response(request)
