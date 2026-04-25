"""
Custom authentication views with enhanced security.

These views extend dj-rest-auth views with:
- Stricter rate limiting
- Enhanced logging for security monitoring
- IP-based throttling for brute-force protection
"""

import logging

from dj_rest_auth.registration.views import RegisterView
from dj_rest_auth.views import LoginView as DjRestAuthLoginView
from dj_rest_auth.views import PasswordResetView as DjRestAuthPasswordResetView
from rest_framework import status

from .throttles import (
    LoginRateThrottle,
    PasswordResetRateThrottle,
    RegistrationRateThrottle,
)

logger = logging.getLogger(__name__)


def _client_ip(request):
    """Best-effort client IP for security logs. Honors X-Forwarded-For."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        # First entry is the original client when proxies append.
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "?")


class LoginView(DjRestAuthLoginView):
    """
    Custom login view with strict rate limiting.

    Security Features:
    - 5 login attempts per 15 minutes per IP address
    - Prevents brute-force attacks
    - Prevents account enumeration
    - Logs failed login attempts for monitoring

    Rate Limit: 5 attempts per 15 minutes per IP
    """

    throttle_classes = [LoginRateThrottle]

    def post(self, request, *args, **kwargs):
        # Capture the email BEFORE delegating so we can log on failure.
        # Never log the password.
        email = (request.data.get("email") or "").strip().lower()
        ip = _client_ip(request)
        response = super().post(request, *args, **kwargs)
        if response.status_code >= 400:
            # Don't include the actual password attempt; the email + IP +
            # status are enough to recognize a brute-force pattern.
            logger.warning(
                "Login FAILED — email=%s ip=%s status=%s",
                email or "<missing>",
                ip,
                response.status_code,
            )
        elif response.status_code == status.HTTP_200_OK:
            logger.info("Login OK — email=%s ip=%s", email, ip)
        return response


class PasswordResetView(DjRestAuthPasswordResetView):
    """
    Custom password reset view with rate limiting.

    Security Features:
    - 3 password reset requests per hour per IP address
    - Prevents spam attacks
    - Prevents email enumeration
    - Prevents account takeover attempts

    Rate Limit: 3 requests per hour per IP
    """

    throttle_classes = [PasswordResetRateThrottle]

    def post(self, request, *args, **kwargs):
        # Log every reset request so we can spot spam / enumeration. The
        # email is necessary context — same trade-off as the audit logs in
        # most SaaS systems.
        email = (request.data.get("email") or "").strip().lower()
        ip = _client_ip(request)
        logger.info(
            "Password reset requested — email=%s ip=%s",
            email or "<missing>",
            ip,
        )
        return super().post(request, *args, **kwargs)


class RegistrationView(RegisterView):
    """
    Custom registration view with rate limiting.

    Security Features:
    - 5 registrations per hour per IP address
    - Prevents mass account creation
    - Prevents spam registrations
    - Prevents resource exhaustion attacks

    Rate Limit: 5 registrations per hour per IP
    """

    throttle_classes = [RegistrationRateThrottle]

    def post(self, request, *args, **kwargs):
        email = (request.data.get("email") or "").strip().lower()
        ip = _client_ip(request)
        response = super().post(request, *args, **kwargs)
        if 200 <= response.status_code < 300:
            logger.info("Registration OK — email=%s ip=%s", email, ip)
        else:
            logger.warning(
                "Registration FAILED — email=%s ip=%s status=%s",
                email or "<missing>",
                ip,
                response.status_code,
            )
        return response
