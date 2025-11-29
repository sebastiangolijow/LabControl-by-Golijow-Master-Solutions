"""
Base settings for LabControl platform.

These settings are common across all environments (dev, staging, prod).
Environment-specific settings should be in dev.py, prod.py, etc.
"""

import os
from pathlib import Path

import environ


# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Initialize environment variables
env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, []),
)

# Read .env file if it exists
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("DJANGO_SECRET_KEY", default="somethingsecret")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env("DJANGO_DEBUG")

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

# Application definition
INSTALLED_APPS = [
    # Django core apps
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    # Third-party apps
    "rest_framework",
    "rest_framework.authtoken",
    "drf_spectacular",
    "django_filters",
    "corsheaders",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "dj_rest_auth",
    "dj_rest_auth.registration",
    "django_celery_beat",
    "django_celery_results",
    "simple_history",
    # Local apps
    "apps.core",  # Core utilities and base classes
    "apps.users",
    "apps.studies",
    "apps.appointments",
    "apps.payments",
    "apps.notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # Serve static files
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",  # Audit trail
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases
DATABASES = {
    "default": env.db("DATABASE_URL"),
}

# Custom User Model
AUTH_USER_MODEL = "users.User"

# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {
            "min_length": 8,
        },
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []

# WhiteNoise configuration for serving static files
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Media files (User uploads)
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Django Sites Framework (required for django-allauth)
SITE_ID = 1

# Django REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
    },
}

# DRF Spectacular (API Documentation)
SPECTACULAR_SETTINGS = {
    "TITLE": "LabControl API",
    "DESCRIPTION": "Multi-client medical laboratory management platform",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/v1",
}

# Django Allauth Configuration
ACCOUNT_AUTHENTICATION_METHOD = "email"
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_USER_MODEL_USERNAME_FIELD = None

# Email Configuration
EMAIL_BACKEND = env(
    "EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@labcontrol.com")

# Celery Configuration
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
CELERY_RESULT_BACKEND = "django-db"
CELERY_CACHE_BACKEND = "django-cache"

# Redis Cache Configuration
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://localhost:6379/0"),
    }
}

# CORS Configuration
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS", default=["http://localhost:8080"]
)
CORS_ALLOW_CREDENTIALS = True

# CSRF Configuration
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS", default=["http://localhost:8000"]
)

# Security Settings (will be overridden in production)
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Logging Configuration
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": env("DJANGO_LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
        "celery": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
