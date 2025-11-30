"""Appointments app configuration."""

from django.apps import AppConfig


class AppointmentsConfig(AppConfig):
    """Configuration for the appointments application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.appointments"
    verbose_name = "Appointments"
