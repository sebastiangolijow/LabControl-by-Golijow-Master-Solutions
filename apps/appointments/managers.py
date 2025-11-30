"""Custom managers for Appointment model."""
from django.db import models
from django.utils import timezone

from apps.core.managers import LabClientManager, LabClientQuerySet


class AppointmentQuerySet(LabClientQuerySet):
    """
    Custom queryset for Appointment model with chainable domain-specific methods.
    """

    def scheduled(self):
        """Return appointments with 'scheduled' status."""
        return self.filter(status="scheduled")

    def confirmed(self):
        """Return appointments with 'confirmed' status."""
        return self.filter(status="confirmed")

    def in_progress(self):
        """Return appointments currently in progress."""
        return self.filter(status="in_progress")

    def completed(self):
        """Return completed appointments."""
        return self.filter(status="completed")

    def cancelled(self):
        """Return cancelled appointments."""
        return self.filter(status="cancelled")

    def no_show(self):
        """Return no-show appointments."""
        return self.filter(status="no_show")

    def upcoming(self):
        """Return upcoming appointments (scheduled or confirmed, in the future)."""
        today = timezone.now().date()
        return self.filter(
            scheduled_date__gte=today,
            status__in=["scheduled", "confirmed"],
        )

    def past(self):
        """Return past appointments."""
        today = timezone.now().date()
        return self.filter(scheduled_date__lt=today)

    def today(self):
        """Return today's appointments."""
        today = timezone.now().date()
        return self.filter(scheduled_date=today)

    def for_patient(self, patient):
        """Return appointments for a specific patient."""
        return self.filter(patient=patient)

    def for_study(self, study):
        """Return appointments related to a specific study."""
        return self.filter(study=study)

    def needs_reminder(self):
        """Return appointments that need a reminder sent."""
        tomorrow = timezone.now().date() + timezone.timedelta(days=1)
        return self.filter(
            scheduled_date=tomorrow,
            status__in=["scheduled", "confirmed"],
            reminder_sent=False,
        )

    def checked_in(self):
        """Return appointments where patient has checked in."""
        return self.exclude(checked_in_at__isnull=True)

    def not_checked_in(self):
        """Return appointments where patient has not checked in."""
        return self.filter(checked_in_at__isnull=True)


class AppointmentManager(LabClientManager):
    """
    Custom manager for Appointment model.

    Provides convenient methods for common appointment queries.
    """

    def get_queryset(self):
        """Return custom queryset."""
        return AppointmentQuerySet(self.model, using=self._db)

    def scheduled(self):
        """Get all scheduled appointments."""
        return self.get_queryset().scheduled()

    def confirmed(self):
        """Get all confirmed appointments."""
        return self.get_queryset().confirmed()

    def in_progress(self):
        """Get all in-progress appointments."""
        return self.get_queryset().in_progress()

    def completed(self):
        """Get all completed appointments."""
        return self.get_queryset().completed()

    def cancelled(self):
        """Get all cancelled appointments."""
        return self.get_queryset().cancelled()

    def no_show(self):
        """Get all no-show appointments."""
        return self.get_queryset().no_show()

    def upcoming(self):
        """Get all upcoming appointments."""
        return self.get_queryset().upcoming()

    def past(self):
        """Get all past appointments."""
        return self.get_queryset().past()

    def today(self):
        """Get today's appointments."""
        return self.get_queryset().today()

    def for_patient(self, patient):
        """Get appointments for a specific patient."""
        return self.get_queryset().for_patient(patient)

    def for_study(self, study):
        """Get appointments for a specific study."""
        return self.get_queryset().for_study(study)

    def needs_reminder(self):
        """Get appointments that need a reminder."""
        return self.get_queryset().needs_reminder()

    def checked_in(self):
        """Get appointments where patient has checked in."""
        return self.get_queryset().checked_in()

    def not_checked_in(self):
        """Get appointments where patient has not checked in."""
        return self.get_queryset().not_checked_in()
