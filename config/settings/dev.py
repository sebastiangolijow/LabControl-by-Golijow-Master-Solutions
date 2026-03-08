"""
Development settings for LabControl platform.

These settings are optimized for local development:
- DEBUG enabled
- Django Debug Toolbar
- Console email backend
- Relaxed security settings
"""

from .base import *  # noqa

# Development mode
DEBUG = True

# Allow all hosts in development
ALLOWED_HOSTS = ["*"]

# Additional apps for development
INSTALLED_APPS += [
    "debug_toolbar",
    "django_extensions",
]

# Debug Toolbar middleware (must be early in the list)
MIDDLEWARE = [
    "debug_toolbar.middleware.DebugToolbarMiddleware",
] + MIDDLEWARE

# Internal IPs for Debug Toolbar
INTERNAL_IPS = [
    "127.0.0.1",
    "localhost",
]

# Debug Toolbar Configuration
DEBUG_TOOLBAR_CONFIG = {
    "SHOW_TOOLBAR_CALLBACK": lambda request: DEBUG,
}

# Console email backend for development (prints to console)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Disable password validation in development for easier testing
AUTH_PASSWORD_VALIDATORS = []

# Less strict CORS in development
# NOTE: Cannot use CORS_ALLOW_ALL_ORIGINS=True with CORS_ALLOW_CREDENTIALS=True
# Browsers require explicit origins when credentials are included
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8080",
]
CORS_ALLOW_METHODS = [
    "DELETE",
    "GET",
    "OPTIONS",
    "PATCH",
    "POST",
    "PUT",
]
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]

# CSRF settings for local development
CSRF_COOKIE_HTTPONLY = False  # Allow JavaScript to read CSRF cookie
CSRF_COOKIE_SAMESITE = "Lax"  # Less restrictive for local dev
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_USE_SESSIONS = False  # Use cookies, not sessions for CSRF
CSRF_COOKIE_SECURE = False  # Don't require HTTPS for CSRF cookie in dev
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# Development-specific logging
LOGGING["loggers"]["django"]["level"] = "DEBUG"  # noqa
LOGGING["loggers"]["apps"] = {  # noqa
    "handlers": ["console"],
    "level": "DEBUG",
    "propagate": False,
}

# Add browsable API renderer for development
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [  # noqa
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
]

# Disable throttling in development
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []  # noqa
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {}  # noqa
