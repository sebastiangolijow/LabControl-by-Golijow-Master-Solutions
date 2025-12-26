"""Email verification token generation and validation."""

import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone


def generate_verification_token():
    """
    Generate a secure random token for email verification.

    Returns a URL-safe 32-character token.
    """
    return secrets.token_urlsafe(32)


def is_token_expired(created_at, expiry_hours=24):
    """
    Check if a verification token has expired.

    Args:
        created_at: DateTime when the token was created
        expiry_hours: Number of hours until expiration (default: 24)

    Returns:
        True if token is expired, False otherwise
    """
    expiry_time = created_at + timedelta(hours=expiry_hours)
    return timezone.now() > expiry_time
