from django.contrib import admin
from django.urls import path,include
from django.contrib.auth import views as auth
from mall import views as v
from mall import security as sec
urlpatterns=[path('admin/',admin.site.urls),path('',v.home,name='home'),path('product/<int:pk>/',v.detail,name='detail'),path('shops/<slug:slug>/',v.store,name='store'),path('bag/',v.bag,name='bag'),path('bag/add/<int:pk>/',v.add,name='add'),path('bag/remove/<int:pk>/',v.remove,name='remove'),path('signup/',v.signup,name='signup'),path('login/',sec.LoginView.as_view(),name='login'),path('logout/',auth.LogoutView.as_view(),name='logout'),path('start-selling/',v.onboard,name='onboard'),path('seller/',v.seller,name='seller'),path('seller/products/new/',v.edit_product,name='new_product'),path('seller/products/<int:pk>/',v.edit_product,name='edit_product'),path('seller/payments/',v.payments,name='payments'),path('seller/payments/<int:pk>/toggle/',v.payment_toggle,name='payment_toggle'),path('seller/orders/<int:pk>/',v.order_update,name='order_update'),path('orders/',v.orders,name='orders'),path('orders/<int:pk>/reference/',v.reference,name='reference')]

urlpatterns += [path('seller/team/',v.team,name='team'),path('workspaces/',v.workspaces,name='workspaces'),path('operations/<slug:slug>/export/',v.finance_export,name='finance_export'),path('operations/<slug:slug>/<str:area>/',v.operations,name='operations')]

from mall import commerce_views as c
urlpatterns += [path('seller/gateway/',c.gateway,name='gateway'),path('orders/<int:pk>/pay/',c.pay,name='pay'),path('payment/callback/',c.callback,name='payment_callback'),path('webhooks/paystack/<uuid:gateway_id>/',c.webhook,name='paystack_webhook'),path('webhooks/paystack/platform/',c.platform_webhook,name='platform_paystack_webhook'),path('seller/mall-pay/',c.mall_pay,name='mall_pay'),path('orders/<int:pk>/cancel/',c.cancel_order,name='cancel_order'),path('orders/<int:pk>/return/',c.return_order,name='return_order'),path('seller/returns/',c.returns,name='returns'),path('seller/settings/',c.store_settings,name='store_settings'),path('seller/verification/',c.verification,name='verification'),path('notifications/',c.notifications,name='notifications'),path('orders/<int:pk>/invoice/',c.invoice,name='invoice')]
urlpatterns += [path('password-reset/',sec.ratelimit('password-reset',20,3600)(sec.PasswordResetView.as_view(template_name='form.html',extra_context={'title':'Reset your password'})),name='password_reset'),path('password-reset/done/',auth.PasswordResetDoneView.as_view(template_name='message.html',extra_context={'title':'Check your email','body':'If your email matches an account, password reset instructions have been sent.'}),name='password_reset_done'),path('reset/<uidb64>/<token>/',auth.PasswordResetConfirmView.as_view(template_name='form.html',extra_context={'title':'Choose a new password'}),name='password_reset_confirm'),path('reset/done/',auth.PasswordResetCompleteView.as_view(template_name='message.html',extra_context={'title':'Password updated','body':'You can now sign in with your new password.'}),name='password_reset_complete')]

from mall import discovery_views as d
urlpatterns += [path('search/suggestions/',d.autocomplete,name='autocomplete'),path('product/<int:pk>/quick-view/',d.quick_view,name='quick_view'),path('product/<int:pk>/save/',d.save_product,name='save_product'),path('product/<int:pk>/review/',d.submit_review,name='submit_review'),path('wishlist/',d.wishlist,name='wishlist'),path('shops/',d.shops,name='shops')]

from django.apps import apps
urlpatterns += [path('engine/',include(apps.get_app_config('oscar').urls[0])),path('',v.home,name='home')]

from django.views.generic import RedirectView
urlpatterns += [path('preview.html',RedirectView.as_view(url='/',permanent=False))]

urlpatterns += [path('search/',d.search_page,name='search')]

from mall import basket_views as b
urlpatterns += [path('bag/quantity/<int:pk>/',b.update_quantity,name='update_quantity'),path('bag/save/<int:pk>/',b.save_for_later,name='save_for_later')]

urlpatterns += [path('product/<int:pk>/report/',d.report_listing,name='report_listing')]

from mall import tracking_views as t,whatsapp_views as w
urlpatterns += [path('orders/<int:pk>/track/',t.tracking,name='tracking'),path('seller/orders/<int:pk>/tracking/',t.tracking_update,name='tracking_update'),path('seller/sms/',t.sms_settings,name='sms_settings'),path('seller/messages/',t.message_log,name='message_log'),path('seller/messages/<int:pk>/retry/',t.retry_message,name='retry_message'),path('seller/whatsapp/',w.whatsapp_settings,name='whatsapp_settings'),path('seller/orders/<int:pk>/whatsapp/',w.message_customer,name='message_customer'),path('webhooks/whatsapp/<int:shop_id>/',w.webhook,name='whatsapp_webhook')]

from mall import address_views as a
urlpatterns += [path('account/addresses/',a.address_book,name='address_book'),path('account/addresses/new/',a.address_edit,name='address_new'),path('account/addresses/<int:pk>/edit/',a.address_edit,name='address_edit'),path('account/addresses/<int:pk>/default/',a.address_default,name='address_default'),path('account/addresses/<int:pk>/delete/',a.address_delete,name='address_delete')]
