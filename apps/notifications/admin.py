"""Admin configuration for notifications app."""

from config.admin import admin, admin_site

from .models import Notification


class NotificationAdmin(admin.ModelAdmin):
    """Admin interface for Notification model."""

    list_display = [
        "title",
        "user",
        "notification_type",
        "channel",
        "status",
        "created_at",
        "read_at",
    ]
    list_filter = [
        "notification_type",
        "channel",
        "status",
        "created_at",
    ]
    search_fields = ["title", "message", "user__email"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at", "sent_at", "delivered_at", "read_at"]


# Register with custom admin site
admin_site.register(Notification, NotificationAdmin)
