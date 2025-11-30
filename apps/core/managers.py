"""
Custom managers and querysets for LabControl platform.

Provides reusable query logic that can be chained and composed.
"""

from django.db import models
from django.db.models import Q


class SoftDeletableQuerySet(models.QuerySet):
    """
    QuerySet for models with soft delete functionality.

    Provides methods to filter, exclude, or restore soft-deleted records.
    """

    def active(self):
        """Return only non-deleted records."""
        return self.filter(is_deleted=False)

    def deleted(self):
        """Return only deleted records."""
        return self.filter(is_deleted=True)

    def with_deleted(self):
        """Return all records including deleted ones."""
        return self.all()

    def hard_delete(self):
        """Permanently delete the records (use with caution!)."""
        return super().delete()


class SoftDeletableManager(models.Manager):
    """
    Manager for models with soft delete functionality.

    By default, filters out deleted records unless explicitly requested.
    """

    def get_queryset(self):
        """Override to exclude deleted records by default."""
        return SoftDeletableQuerySet(self.model, using=self._db).active()

    def active(self):
        """Explicitly get active records."""
        return self.get_queryset().active()

    def deleted(self):
        """Get deleted records."""
        return self.get_queryset().deleted()

    def with_deleted(self):
        """Get all records including deleted."""
        return SoftDeletableQuerySet(self.model, using=self._db)


class LabClientQuerySet(models.QuerySet):
    """
    QuerySet for models with multi-tenant support.

    Provides methods to filter by laboratory client.
    """

    def for_lab(self, lab_client_id):
        """Filter records for a specific laboratory client."""
        return self.filter(lab_client_id=lab_client_id)

    def for_user_lab(self, user):
        """Filter records for the user's laboratory client."""
        if user and hasattr(user, "lab_client_id") and user.lab_client_id:
            return self.filter(lab_client_id=user.lab_client_id)
        return self.none()


class LabClientManager(models.Manager):
    """
    Manager for models with multi-tenant support.
    """

    def get_queryset(self):
        return LabClientQuerySet(self.model, using=self._db)

    def for_lab(self, lab_client_id):
        return self.get_queryset().for_lab(lab_client_id)

    def for_user_lab(self, user):
        return self.get_queryset().for_user_lab(user)
