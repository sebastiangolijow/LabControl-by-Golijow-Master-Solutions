"""Custom throttle classes for user authentication."""

from rest_framework.throttling import (
    AnonRateThrottle,
    SimpleRateThrottle,
    UserRateThrottle,
)


class LoginRateThrottle(SimpleRateThrottle):
    """
    Throttle for login attempts to prevent brute-force attacks.

    Rate: 5 attempts per 15 minutes per IP address.

    This applies to both authenticated and unauthenticated users
    to prevent account enumeration and brute-force attacks.
    """

    scope = "login"
    rate = "5/15m"

    def parse_rate(self, rate):
        """
        Custom parse_rate to support multi-digit minute values like '15m'.

        Django REST Framework's default parse_rate only supports single-character
        periods (s, m, h, d) but we need '15m' for 15 minutes.
        """
        if rate is None:
            return (None, None)

        num, period = rate.split("/")
        num_requests = int(num)

        # Handle multi-digit periods (e.g., '15m', '30s', '24h')
        if period.endswith("s"):
            duration = int(period[:-1])
        elif period.endswith("m"):
            duration = int(period[:-1]) * 60
        elif period.endswith("h"):
            duration = int(period[:-1]) * 3600
        elif period.endswith("d"):
            duration = int(period[:-1]) * 86400
        else:
            raise ValueError(f"Invalid period format: {period}")

        return (num_requests, duration)

    def get_cache_key(self, request, view):
        """
        Generate cache key based on IP address.

        We use IP address rather than user identity because:
        1. Login attempts happen before authentication
        2. We want to prevent brute-force against any account
        3. IP-based throttling is more effective for login security
        """
        if request.method != "POST":
            # Only throttle POST requests (login attempts)
            return None

        # Get client IP address
        ident = self.get_ident(request)

        return self.cache_format % {"scope": self.scope, "ident": ident}


class PasswordResetRateThrottle(AnonRateThrottle):
    """
    Throttle for password reset requests to prevent abuse.

    Rate: 3 attempts per hour per IP address.

    This prevents:
    - Spam attacks sending many reset emails
    - Email enumeration attacks
    - Account takeover attempts
    """

    scope = "password_reset"


class RegistrationRateThrottle(AnonRateThrottle):
    """
    Throttle for user registration to prevent spam accounts.

    Rate: 5 registrations per hour per IP address.

    This prevents:
    - Mass account creation
    - Spam registrations
    - Resource exhaustion attacks
    """

    scope = "registration"
