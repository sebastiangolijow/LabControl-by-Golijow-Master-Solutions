"""Admin configuration for appointments app."""

from django.contrib import admin

from .models import Appointment


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    """Admin interface for Appointment model."""

    list_display = [
        "appointment_number",
        "patient",
        "scheduled_date",
        "scheduled_time",
        "status",
        "reminder_sent",
    ]
    list_filter = ["status", "scheduled_date", "reminder_sent"]
    search_fields = ["appointment_number", "patient__email"]
    ordering = ["-scheduled_date", "-scheduled_time"]
    readonly_fields = ["created_at", "updated_at"]
