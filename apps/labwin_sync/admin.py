from django.contrib import admin

from .models import SyncedRecord, SyncLog


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = [
        "started_at",
        "status",
        "lab_client_id",
        "studies_created",
        "patients_created",
        "error_count",
        "completed_at",
    ]
    list_filter = ["status", "lab_client_id"]
    readonly_fields = [
        "uuid",
        "started_at",
        "completed_at",
        "celery_task_id",
        "errors",
        "last_synced_numero",
        "last_synced_fecha",
    ]
    ordering = ["-started_at"]


@admin.register(SyncedRecord)
class SyncedRecordAdmin(admin.ModelAdmin):
    list_display = [
        "source_table",
        "source_key",
        "target_model",
        "target_uuid",
        "lab_client_id",
        "synced_at",
    ]
    list_filter = ["source_table", "target_model", "lab_client_id"]
    search_fields = ["source_key", "target_uuid"]
    readonly_fields = ["synced_at"]
