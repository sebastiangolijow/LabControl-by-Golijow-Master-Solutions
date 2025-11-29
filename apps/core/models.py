"""
Base models and mixins for LabControl platform.

These base classes provide common functionality following production best practices:
- Timestamp tracking (created_at, updated_at)
- UUID support for better security and distribution
- Creator tracking
- Soft delete capability
- Audit trail with django-simple-history
"""
import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class TimeStampedModel(models.Model):
    """
    Abstract base class that provides timestamp tracking.

    Automatically tracks when records are created and last updated.
    """

    created_at = models.DateTimeField(
        _("created at"),
        auto_now_add=True,
        help_text=_("Timestamp when the record was created"),
    )
    updated_at = models.DateTimeField(
        _("updated at"),
        auto_now=True,
        help_text=_("Timestamp when the record was last updated"),
    )

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class UUIDModel(models.Model):
    """
    Abstract base class that provides UUID field.

    UUIDs are better than auto-increment IDs for:
    - Security (no enumeration attacks)
    - Distributed systems
    - Merging databases
    """

    uuid = models.UUIDField(
        _("UUID"),
        default=uuid.uuid4,
        editable=False,
        unique=True,
        help_text=_("Unique identifier for this record"),
    )

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["uuid"]),
        ]


class CreatedByModel(models.Model):
    """
    Abstract base class that tracks who created the record.

    Uses dynamic related_name to avoid conflicts.
    """

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_created",
        verbose_name=_("created by"),
        help_text=_("User who created this record"),
    )

    class Meta:
        abstract = True


class SoftDeletableModel(models.Model):
    """
    Abstract base class for soft delete functionality.

    Instead of actually deleting records, mark them as deleted.
    This preserves data integrity and allows for audit trails.
    """

    is_deleted = models.BooleanField(
        _("is deleted"),
        default=False,
        help_text=_("Indicates if this record has been soft-deleted"),
    )
    deleted_at = models.DateTimeField(
        _("deleted at"),
        null=True,
        blank=True,
        help_text=_("Timestamp when the record was deleted"),
    )
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_deleted",
        verbose_name=_("deleted by"),
        help_text=_("User who deleted this record"),
    )

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["is_deleted"]),
        ]

    def soft_delete(self, user=None):
        """Soft delete the record."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = user
        self.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])

    def restore(self):
        """Restore a soft-deleted record."""
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])


class BaseModel(TimeStampedModel, UUIDModel, CreatedByModel):
    """
    Base model combining the most common mixins.

    Provides:
    - Timestamps (created_at, updated_at)
    - UUID field
    - Creator tracking (created_by)

    Most models in the system should inherit from this.
    """

    class Meta:
        abstract = True


class LabClientModel(models.Model):
    """
    Abstract base class for multi-tenant support.

    Models that need to be isolated per laboratory client should inherit this.
    """

    lab_client_id = models.IntegerField(
        _("laboratory client ID"),
        null=True,
        blank=True,
        db_index=True,
        help_text=_("ID of the laboratory client this record belongs to"),
    )

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["lab_client_id"]),
        ]


class FullBaseModel(BaseModel, LabClientModel):
    """
    Full-featured base model with multi-tenant support.

    Provides:
    - Timestamps (created_at, updated_at)
    - UUID field
    - Creator tracking (created_by)
    - Multi-tenant support (lab_client_id)

    Use this for models that need all features.
    """

    class Meta:
        abstract = True
