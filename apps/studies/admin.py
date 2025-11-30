"""Admin configuration for studies app."""

from django.contrib import admin

from .models import Study, StudyType


@admin.register(StudyType)
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


@admin.register(Study)
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
