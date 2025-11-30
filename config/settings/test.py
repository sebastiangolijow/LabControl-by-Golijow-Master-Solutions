"""
Test settings for LabControl platform.

These settings are optimized for fast test execution:
- In-memory SQLite database (fast, no I/O)
- Disabled migrations
- Fast password hashing
- Synchronous Celery execution
"""
from .base import *  # noqa

# Use in-memory SQLite for blazing fast tests
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}


# Disable migrations for faster tests
class DisableMigrations:
    """
    Disable migrations during tests.

    This significantly speeds up test database creation.
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

# Disable debug toolbar in tests
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != "debug_toolbar"]  # noqa
MIDDLEWARE = [m for m in MIDDLEWARE if "debug_toolbar" not in m]  # noqa

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

# Disable template caching
for template in TEMPLATES:  # noqa
    template["OPTIONS"]["debug"] = True

# No file storage in tests
DEFAULT_FILE_STORAGE = "django.core.files.storage.InMemoryStorage"

# Use simple static files storage (no manifest/compression)
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

# Simple history doesn't need middleware in tests
MIDDLEWARE = [m for m in MIDDLEWARE if "HistoryRequestMiddleware" not in m]  # noqa
