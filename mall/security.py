"""Abuse protection and HTTP hardening.

Rate limits use the Django cache. Configure REDIS_URL in production so every
Gunicorn worker shares one counter; the local-memory fallback is per process.
"""
import hashlib
from functools import wraps

from django.conf import settings
from django.contrib.auth import views as auth_views
from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import render


def client_ip(request):
    """Client address. Only trusts X-Forwarded-For entries appended by TRUSTED_PROXY_COUNT proxies."""
    count = getattr(settings, 'TRUSTED_PROXY_COUNT', 0)
    if count > 0:
        hops = [part.strip() for part in request.META.get('HTTP_X_FORWARDED_FOR', '').split(',') if part.strip()]
        if len(hops) >= count:
            return hops[-count]
    return request.META.get('REMOTE_ADDR', '')


def _key(name):
    return 'rl:' + hashlib.sha256(name.encode()).hexdigest()


def hit(name, limit, window):
    """Count one event. Returns True once the limit is exceeded within the window (seconds)."""
    if not getattr(settings, 'RATELIMIT_ENABLED', True):
        return False
    key = _key(name)
    cache.add(key, 0, window)
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, window)
        count = 1
    return count > limit


def peek(name):
    if not getattr(settings, 'RATELIMIT_ENABLED', True):
        return 0
    return cache.get(_key(name), 0)


def reset(name):
    cache.delete(_key(name))


def too_many(request, detail='Too many attempts. Please wait a few minutes and try again.'):
    if request.headers.get('HX-Request') == 'true':
        return HttpResponse(detail, status=429, content_type='text/plain')
    response = render(request, 'message.html', {'title': 'Please slow down', 'body': detail, 'hide_sign_in': True}, status=429)
    response['Retry-After'] = '60'
    return response


def ratelimit(scope, limit, window, key='ip', methods=('POST',)):
    """Decorator. key='user' counts per signed-in account (falling back to IP for visitors)."""
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method in methods:
                ident = 'u' + str(request.user.pk) if key == 'user' and request.user.is_authenticated else 'ip' + client_ip(request)
                if hit(scope + ':' + ident, limit, window):
                    return too_many(request)
            return view(request, *args, **kwargs)
        return wrapped
    return decorator


LOGIN_WINDOW = 15 * 60


class LoginView(auth_views.LoginView):
    """Locks out repeated failures per username and per client address for 15 minutes."""
    template_name = 'login.html'
    redirect_authenticated_user = True

    def _names(self):
        username = (self.request.POST.get('username') or '').strip().lower()
        return 'login-user:' + username, 'login-ip:' + client_ip(self.request)

    def post(self, request, *args, **kwargs):
        user_key, ip_key = self._names()
        if peek(user_key) >= settings.LOGIN_FAILURES_PER_ACCOUNT or peek(ip_key) >= settings.LOGIN_FAILURES_PER_IP:
            return too_many(request, 'Too many failed sign-in attempts. Wait 15 minutes, or reset your password.')
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        user_key, ip_key = self._names()
        hit(user_key, settings.LOGIN_FAILURES_PER_ACCOUNT, LOGIN_WINDOW)
        hit(ip_key, settings.LOGIN_FAILURES_PER_IP, LOGIN_WINDOW)
        return super().form_invalid(form)

    def form_valid(self, form):
        reset(self._names()[0])
        return super().form_valid(form)

    def get_default_redirect_url(self):
        """Owners go to their seller centre, staff to their workspaces, everyone else to the mall."""
        from .models import Shop, StaffMembership
        user = self.request.user
        if Shop.objects.filter(owner=user).exists():
            return '/seller/'
        if StaffMembership.objects.filter(user=user, active=True).exists():
            return '/workspaces/'
        return '/'


class PasswordResetView(auth_views.PasswordResetView):
    """At most PASSWORD_RESETS_PER_EMAIL emails per address per hour; the response never reveals this."""

    def form_valid(self, form):
        email = form.cleaned_data['email'].strip().lower()
        if hit('reset-email:' + email, settings.PASSWORD_RESETS_PER_EMAIL, 3600):
            from django.shortcuts import redirect
            return redirect(self.get_success_url())
        return super().form_valid(form)


class SecurityHeadersMiddleware:
    """Adds Content-Security-Policy and Permissions-Policy headers."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        policy = getattr(settings, 'CONTENT_SECURITY_POLICY', '')
        if policy and 'Content-Security-Policy' not in response:
            response['Content-Security-Policy'] = policy
        response.setdefault('Permissions-Policy', 'camera=(), microphone=(), payment=(), geolocation=(self)')
        return response
