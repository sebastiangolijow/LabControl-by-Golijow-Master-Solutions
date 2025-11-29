"""
Production settings for LabControl platform.

These settings are optimized for production deployment:
- DEBUG disabled
- Strict security settings
- Sentry error tracking
- Cloud storage for media files
"""
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

from .base import *  # noqa

# Production mode - NEVER set DEBUG = True in production!
DEBUG = False

# Allowed hosts must be explicitly set in production
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

# Security Settings - CRITICAL for production
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Cookie settings
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Strict"
CSRF_COOKIE_SAMESITE = "Strict"

# Email Configuration for Production
# Use a proper email backend like SendGrid, Mailgun, or AWS SES
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

# Google Cloud Storage for media files
USE_GCS = env.bool("USE_GCS", default=False)

if USE_GCS:
    DEFAULT_FILE_STORAGE = "storages.backends.gcloud.GoogleCloudStorage"
    GS_BUCKET_NAME = env("GCS_BUCKET_NAME")
    GS_PROJECT_ID = env("GCS_PROJECT_ID")
    GS_AUTO_CREATE_BUCKET = False
    GS_DEFAULT_ACL = "private"
    GS_FILE_OVERWRITE = False
    # Use the credentials file path from environment
    if env("GOOGLE_APPLICATION_CREDENTIALS", default=None):
        GS_CREDENTIALS = env("GOOGLE_APPLICATION_CREDENTIALS")

# Sentry Error Tracking
SENTRY_DSN = env("SENTRY_DSN", default=None)
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # Adjust this value in production.
        traces_sample_rate=0.1,
        # If you wish to associate users to errors (assuming you are using
        # django.contrib.auth) you may enable sending PII data.
        send_default_pii=False,
        environment="production",
    )

# Production logging - send to cloud logging service
LOGGING["handlers"]["console"]["level"] = "WARNING"  # noqa
LOGGING["root"]["level"] = "WARNING"  # noqa

# Database connection pooling for production
DATABASES["default"]["CONN_MAX_AGE"] = 600  # noqa

# Cache configuration for production - use Redis
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "CONNECTION_POOL_KWARGS": {"max_connections": 50},
        },
        "KEY_PREFIX": "labcontrol",
    }
}

# Enable admin panel security
ADMIN_URL = env("ADMIN_URL", default="admin/")
