"""Admin configuration for studies app."""

from config.admin import admin, admin_site

from .models import Determination, Practice, Study, UserDetermination


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
    filter_horizontal = ["determinations"]
    ordering = ["name"]


class DeterminationAdmin(admin.ModelAdmin):
    """Admin interface for Determination model."""

    list_display = [
        "name",
        "code",
        "unit",
        "reference_range",
        "is_active",
    ]
    list_filter = ["is_active"]
    search_fields = ["name", "code", "description"]
    ordering = ["name"]


class StudyAdmin(admin.ModelAdmin):
    """Admin interface for Study model."""

    list_display = [
        "protocol_number",
        "patient",
        "practice",
        "status",
        "created_at",
        "completed_at",
    ]
    list_filter = ["status", "created_at", "completed_at"]
    search_fields = ["protocol_number", "patient__email", "sample_id"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at", "updated_at"]


class UserDeterminationAdmin(admin.ModelAdmin):
    """Admin interface for UserDetermination model."""

    list_display = [
        "study",
        "determination",
        "value",
        "is_abnormal",
        "created_at",
    ]
    list_filter = ["is_abnormal", "determination"]
    search_fields = ["study__protocol_number", "determination__name", "value"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at", "updated_at"]


# Register with custom admin site
admin_site.register(Practice, PracticeAdmin)
admin_site.register(Determination, DeterminationAdmin)
admin_site.register(Study, StudyAdmin)
admin_site.register(UserDetermination, UserDeterminationAdmin)
