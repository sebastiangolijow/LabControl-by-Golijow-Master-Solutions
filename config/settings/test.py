"""
Test settings for LabControl platform.

These settings are optimized for fast test execution:
- In-memory SQLite database for local testing (fast, no I/O)
- PostgreSQL for CI pipeline (DATABASE_URL environment variable)
- Disabled migrations for SQLite (fast), enabled for PostgreSQL (required)
- Fast password hashing
- Synchronous Celery execution
"""

import os

import dj_database_url

from .base import *  # noqa

# Database configuration
# Use DATABASE_URL if available (CI/CD), otherwise use in-memory SQLite (local)
DATABASES = {
    "default": dj_database_url.config(
        default="sqlite:///:memory:",
        conn_max_age=600,
    )
}

# Detect if we're using PostgreSQL (CI) or SQLite (local)
using_postgres = DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"


# Disable migrations only for SQLite (faster local tests)
# Enable migrations for PostgreSQL (CI pipeline requires real migrations)
if not using_postgres:

    class DisableMigrations:
        """
        Disable migrations during tests.

        This significantly speeds up test database creation.
        Only used for SQLite (local development).
        """

        def __contains__(self, item):
            return True

        def __getitem__(self, item):
            return None

    MIGRATION_MODULES = DisableMigrations()

# Fast password hashing for tests (MD5 is insecure but fast for tests)
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Celery runs synchronously in tests (tasks execute immediately)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Disable debug toolbar and extensions in tests
INSTALLED_APPS = [
    app for app in INSTALLED_APPS if app not in ["debug_toolbar", "django_extensions"]
]  # noqa
MIDDLEWARE = [m for m in MIDDLEWARE if "debug_toolbar" not in m]  # noqa
DEBUG = False

# Simpler logging for tests
LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "handlers": {
        "null": {
            "class": "logging.NullHandler",
        },
    },
    "root": {
        "handlers": ["null"],
    },
}

# Disable password validators in tests
AUTH_PASSWORD_VALIDATORS = []

# Use simple email backend for tests
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
DEFAULT_FROM_EMAIL = "noreply@labcontrol.test"

# Frontend URL for email templates
FRONTEND_URL = "http://localhost:3000"

# Disable template caching
for template in TEMPLATES:  # noqa
    template["OPTIONS"]["debug"] = True

# No file storage in tests
DEFAULT_FILE_STORAGE = "django.core.files.storage.InMemoryStorage"

# Use simple static files storage (no manifest/compression)
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

# Simple history doesn't need middleware in tests
MIDDLEWARE = [m for m in MIDDLEWARE if "HistoryRequestMiddleware" not in m]  # noqa
