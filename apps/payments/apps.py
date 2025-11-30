"""Payments app configuration."""

from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    """Configuration for the payments application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.payments"
    verbose_name = "Payments & Billing"
