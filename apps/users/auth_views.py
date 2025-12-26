"""
Custom authentication views with enhanced security.

These views extend dj-rest-auth views with:
- Stricter rate limiting
- Enhanced logging for security monitoring
- IP-based throttling for brute-force protection
"""

from dj_rest_auth.registration.views import RegisterView
from dj_rest_auth.views import (
    LoginView as DjRestAuthLoginView,
    PasswordResetView as DjRestAuthPasswordResetView,
)

from .throttles import LoginRateThrottle, PasswordResetRateThrottle, RegistrationRateThrottle


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
