"""Admin configuration for appointments app."""

from django.contrib import admin

from config.admin import admin_site

from .models import Appointment


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


# Register with custom admin site
admin_site.register(Appointment, AppointmentAdmin)
