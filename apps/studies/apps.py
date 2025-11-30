"""Studies app configuration."""

from django.apps import AppConfig


class StudiesConfig(AppConfig):
    """Configuration for the studies application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.studies"
    verbose_name = "Medical Studies"
