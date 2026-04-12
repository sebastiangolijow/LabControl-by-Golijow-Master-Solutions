"""
Models for tracking LabWin Firebird database synchronization.

SyncLog tracks each sync execution (nightly or manual).
SyncedRecord maps individual LabWin records to LabControl objects for deduplication.
"""

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class SyncLog(models.Model):
    """Tracks each LabWin sync execution."""

    STATUS_CHOICES = [
        ("started", "Started"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("partial", "Partial"),
    ]

    uuid = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default="started",
    )
    started_at = models.DateTimeField(_("started at"), auto_now_add=True)
    completed_at = models.DateTimeField(_("completed at"), null=True, blank=True)
    lab_client_id = models.IntegerField(
        _("laboratory client ID"),
        null=True,
        blank=True,
        db_index=True,
    )

    # Counters
    patients_created = models.IntegerField(default=0)
    patients_updated = models.IntegerField(default=0)
    doctors_created = models.IntegerField(default=0)
    doctors_updated = models.IntegerField(default=0)
    practices_created = models.IntegerField(default=0)
    studies_created = models.IntegerField(default=0)
    studies_updated = models.IntegerField(default=0)

    # Error tracking
    errors = models.JSONField(default=list, blank=True)
    error_count = models.IntegerField(default=0)

    # Cursor: highest NUMERO_FLD + FECHA_FLD processed in this run
    last_synced_numero = models.BigIntegerField(null=True, blank=True)
    last_synced_fecha = models.CharField(max_length=8, blank=True)

    # Celery task ID for correlation
    celery_task_id = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = _("sync log")
        verbose_name_plural = _("sync logs")
        ordering = ["-started_at"]

    def __str__(self):
        return f"SyncLog {self.started_at:%Y-%m-%d %H:%M} - {self.status}"


class SyncedRecord(models.Model):
    """Maps a LabWin record to a LabControl object for deduplication."""

    source_table = models.CharField(
        _("source table"),
        max_length=50,
        help_text=_("LabWin table name (e.g. PACIENTES, DETERS, MEDICOS)"),
    )
    source_key = models.CharField(
        _("source key"),
        max_length=100,
        db_index=True,
        help_text=_("LabWin primary key (e.g. NUMERO_FLD or composite key)"),
    )
    target_model = models.CharField(
        _("target model"),
        max_length=50,
        help_text=_("LabControl model name (e.g. User, Study, Practice)"),
    )
    target_uuid = models.UUIDField(
        _("target UUID"),
        db_index=True,
        help_text=_("UUID of the created/updated LabControl object"),
    )
    lab_client_id = models.IntegerField(
        _("laboratory client ID"),
        null=True,
        blank=True,
        db_index=True,
    )
    synced_at = models.DateTimeField(_("synced at"), auto_now_add=True)
    sync_log = models.ForeignKey(
        SyncLog,
        on_delete=models.CASCADE,
        related_name="records",
        verbose_name=_("sync log"),
    )

    class Meta:
        verbose_name = _("synced record")
        verbose_name_plural = _("synced records")
        unique_together = [["source_table", "source_key", "lab_client_id"]]
        indexes = [
            models.Index(fields=["source_table", "source_key"]),
        ]

    def __str__(self):
        return f"{self.source_table}:{self.source_key} -> {self.target_model}:{self.target_uuid}"
