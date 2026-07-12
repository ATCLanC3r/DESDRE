"""
Session management utilities for Remember Me functionality and login rate limiting.
"""
from django.contrib.auth.views import LoginView
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from typing import Callable, Any
from django.core.cache import cache
from django.contrib.auth.signals import user_login_failed
from django.dispatch import receiver
import logging

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 5
_LOCKOUT_SECONDS = 15 * 60   # 15 minutes
_WINDOW_SECONDS  = 15 * 60   # count attempts within 15-minute window


def _get_ip(request) -> str:
    return (
        request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
        or request.META.get('REMOTE_ADDR', 'unknown')
    )


def _rate_limit_key(ip: str, username: str) -> str:
    # Keyed per (IP, username) so shared IPs don't affect each other's accounts
    safe_username = username.lower().strip()[:100]
    return f"login_attempts:{ip}:{safe_username}"


class LoginRateLimitMixin:
    """
    Mixin for Django's LoginView that enforces a per-IP-per-username rate limit
    and logs every attempt to the LoginAttempt audit table (TC-022).

    Keying by (IP + username) means users sharing a network (NAT, university
    Wi-Fi) each have independent counters and cannot lock each other out.
    """

    def dispatch(self, request, *args, **kwargs):
        ip = _get_ip(request)
        username = request.POST.get('username', '')
        key = _rate_limit_key(ip, username)
        attempts = cache.get(key, 0)
        if attempts >= _MAX_ATTEMPTS:
            from django.contrib import messages as dj_messages
            dj_messages.error(
                request,
                "Too many failed login attempts. Please wait 15 minutes before trying again."
            )
            return self.get(request, *args, **kwargs)
        return super().dispatch(request, *args, **kwargs)

    def form_invalid(self, form):
        from mainApp.models import LoginAttempt
        request = self.request
        ip = _get_ip(request)
        username = form.cleaned_data.get('username', '') or form.data.get('username', '')
        key = _rate_limit_key(ip, username)
        attempts = cache.get(key, 0) + 1
        cache.set(key, attempts, _WINDOW_SECONDS)

        LoginAttempt.objects.create(username=username, ip_address=ip, success=False)
        logger.warning("Failed login attempt %d/5 for IP %s (username: %s)", attempts, ip, username)
        return super().form_invalid(form)

    def form_valid(self, form):
        from mainApp.models import LoginAttempt
        request = self.request
        ip = _get_ip(request)
        username = form.cleaned_data.get('username', '')
        cache.delete(_rate_limit_key(ip, username))
        LoginAttempt.objects.create(username=username, ip_address=ip, success=True)
        return super().form_valid(form)


class RememberMeLoginMixin(LoginRateLimitMixin):
    """
    Mixin for LoginView that handles 'remember_me' checkbox.
    
    - If checked: Session persists for SESSION_AGE_REMEMBERED
    - If unchecked: Session expires when browser closes
    """
    SESSION_AGE_REMEMBERED = 60 * 60 * 24 * 7   # 7 days
    SESSION_AGE_BROWSER = 0  # Expires when browser closes
    
    def form_valid(self, form) -> HttpResponse:
        """Override to handle remember_me checkbox."""
        # Call parent's form_valid to log user in
        response = super().form_valid(form)  # type: ignore[misc]
        
        # Handle session expiry based on remember_me
        remember_me = form.cleaned_data.get('remember_me', False)
        
        if remember_me:
            # Persistent session
            self.request.session.set_expiry(self.SESSION_AGE_REMEMBERED)
            self.request.session['remember_me'] = True
        else:
            # Session expires when browser closes
            self.request.session.set_expiry(self.SESSION_AGE_BROWSER)
            if 'remember_me' in self.request.session:
                del self.request.session['remember_me']
        
        return response
