"""Admin configuration for studies app."""

from config.admin import admin, admin_site

from .models import Practice, Study, StudyType


class PracticeAdmin(admin.ModelAdmin):
    """Admin interface for Practice model."""

    list_display = [
        "name",
        "technique",
        "sample_type",
        "price",
        "delay_days",
        "is_active",
    ]
    list_filter = ["is_active", "sample_type"]
    search_fields = ["name", "technique", "sample_type"]
    ordering = ["name"]


class StudyTypeAdmin(admin.ModelAdmin):
    """Admin interface for StudyType model."""

    list_display = [
        "name",
        "code",
        "category",
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
admin_site.register(Practice, PracticeAdmin)
admin_site.register(StudyType, StudyTypeAdmin)
admin_site.register(Study, StudyAdmin)
