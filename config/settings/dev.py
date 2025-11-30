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
CORS_ALLOW_ALL_ORIGINS = True

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
