"""Admin configuration for studies app."""

from config.admin import admin
from config.admin import admin_site

from .models import Study
from .models import StudyType


class StudyTypeAdmin(admin.ModelAdmin):
    """Admin interface for StudyType model."""

    list_display = [
        "name",
        "code",
        "category",
        "base_price",
        "requires_fasting",
        "is_active",
    ]
    list_filter = ["is_active", "requires_fasting", "category"]
    search_fields = ["name", "code", "description"]
    ordering = ["name"]


class StudyAdmin(admin.ModelAdmin):
    """Admin interface for Study model."""

    list_display = [
        "order_number",
        "patient",
        "study_type",
        "status",
        "created_at",
        "completed_at",
    ]
    list_filter = ["status", "created_at", "completed_at"]
    search_fields = ["order_number", "patient__email", "sample_id"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at", "updated_at"]


# Register with custom admin site
admin_site.register(StudyType, StudyTypeAdmin)
admin_site.register(Study, StudyAdmin)
