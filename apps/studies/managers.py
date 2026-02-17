"""Custom managers and querysets for studies app."""

from django.db import models
from django.db.models import OuterRef, Q

from apps.core.managers import LabClientManager, LabClientQuerySet
from apps.core.querysets import SubqueryCount


class StudyQuerySet(LabClientQuerySet):
    """
    Custom queryset for Study model with chainable methods.

    Provides domain-specific query methods that can be chained together.
    """

    def pending(self):
        """Return studies with pending status."""
        return self.filter(status="pending")

    def sample_collected(self):
        """Return studies where sample has been collected."""
        return self.filter(status="sample_collected")

    def in_progress(self):
        """Return studies currently being processed."""
        return self.filter(status="in_progress")

    def completed(self):
        """Return completed studies."""
        return self.filter(status="completed")

    def cancelled(self):
        """Return cancelled studies."""
        return self.filter(status="cancelled")

    def for_patient(self, patient):
        """Filter studies for a specific patient."""
        return self.filter(patient=patient)

    def for_practice(self, practice):
        """Filter studies for a specific practice."""
        return self.filter(practice=practice)

    def with_results(self):
        """Return studies that have results."""
        return self.exclude(Q(results="") | Q(results__isnull=True))

    def without_results(self):
        """Return studies without results yet."""
        return self.filter(Q(results="") | Q(results__isnull=True))

    def ordered_by(self, user):
        """Return studies ordered by a specific user."""
        return self.filter(ordered_by=user)

    def with_appointment_count(self):
        """
        Annotate each study with its appointment count.

        Uses efficient subquery to avoid N+1 queries.
        """
        from apps.appointments.models import Appointment

        return self.annotate(
            appointment_count=SubqueryCount(
                Appointment.objects.filter(study=OuterRef("pk"))
            )
        )


class StudyManager(LabClientManager):
    """
    Custom manager for Study model.

    Provides convenient methods for common queries.
    """

    def get_queryset(self):
        """Return custom queryset."""
        return StudyQuerySet(self.model, using=self._db)

    def pending(self):
        """Get all pending studies."""
        return self.get_queryset().pending()

    def completed(self):
        """Get all completed studies."""
        return self.get_queryset().completed()

    def in_progress(self):
        """Get studies currently in progress."""
        return self.get_queryset().in_progress()

    def for_patient(self, patient):
        """Get all studies for a patient."""
        return self.get_queryset().for_patient(patient)
