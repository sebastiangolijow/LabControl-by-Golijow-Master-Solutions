"""Admin configuration for users app."""

from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from config.admin import admin
from config.admin import admin_site

from .models import User


class UserAdmin(BaseUserAdmin):
    """Custom admin interface for User model."""

    list_display = [
        "email",
        "first_name",
        "last_name",
        "role",
        "lab_client_id",
        "is_active",
        "is_verified",
        "is_staff",
        "date_joined",
    ]
    list_filter = [
        "is_staff",
        "is_active",
        "is_verified",
        "role",
        "date_joined",
    ]
    search_fields = ["email", "first_name", "last_name", "phone_number"]
    ordering = ["-date_joined"]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            _("Personal Info"),
            {"fields": ("first_name", "last_name", "phone_number")},
        ),
        (
            _("Role & Permissions"),
            {
                "fields": (
                    "role",
                    "lab_client_id",
                    "is_active",
                    "is_verified",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            _("Important Dates"),
            {"fields": ("last_login", "date_joined", "updated_at")},
        ),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "first_name",
                    "last_name",
                    "role",
                    "is_staff",
                    "is_active",
                ),
            },
        ),
    )

    readonly_fields = ["date_joined", "last_login", "updated_at"]


# Register with custom admin site (superuser-only access)
admin_site.register(User, UserAdmin)
