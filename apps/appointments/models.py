"""Models for appointments app."""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.core.models import BaseModel, LabClientModel

from .managers import AppointmentManager


class Appointment(BaseModel, LabClientModel):
    """
    Patient appointment for sample collection or consultation.

    Manages scheduling and tracking of patient visits to the laboratory.
    """

    STATUS_CHOICES = [
        ("scheduled", _("Scheduled")),
        ("confirmed", _("Confirmed")),
        ("in_progress", _("In Progress")),
        ("completed", _("Completed")),
        ("cancelled", _("Cancelled")),
        ("no_show", _("No Show")),
    ]

    # Relationships
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="appointments",
        limit_choices_to={"role": "patient"},
    )
    study = models.ForeignKey(
        "studies.Study",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointments",
        help_text=_("Related study if this is for sample collection"),
    )

    # Appointment details
    appointment_number = models.CharField(
        _("appointment number"),
        max_length=50,
        unique=True,
    )
    scheduled_date = models.DateField(_("scheduled date"))
    scheduled_time = models.TimeField(_("scheduled time"))
    duration_minutes = models.IntegerField(
        _("duration (minutes)"),
        default=30,
    )

    # Status and confirmation
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default="scheduled",
    )
    confirmed_at = models.DateTimeField(_("confirmed at"), null=True, blank=True)

    # Check-in/Check-out
    checked_in_at = models.DateTimeField(_("checked in at"), null=True, blank=True)
    checked_out_at = models.DateTimeField(_("checked out at"), null=True, blank=True)

    # Notes
    reason = models.TextField(_("reason for visit"), blank=True)
    notes = models.TextField(_("notes"), blank=True)
    cancellation_reason = models.TextField(_("cancellation reason"), blank=True)

    # Reminders
    reminder_sent = models.BooleanField(_("reminder sent"), default=False)
    reminder_sent_at = models.DateTimeField(
        _("reminder sent at"), null=True, blank=True
    )

    # Audit trail - track all changes to appointment records
    history = HistoricalRecords()

    # Custom manager
    objects = AppointmentManager()

    class Meta:
        verbose_name = _("appointment")
        verbose_name_plural = _("appointments")
        ordering = ["scheduled_date", "scheduled_time"]
        indexes = [
            models.Index(fields=["uuid"]),
            models.Index(fields=["appointment_number"]),
            models.Index(fields=["patient", "status"]),
            models.Index(fields=["scheduled_date", "scheduled_time"]),
            models.Index(fields=["lab_client_id"]),
            models.Index(fields=["status", "scheduled_date"]),  # Common query pattern
        ]

    def __str__(self):
        return (
            f"{self.appointment_number} - {self.patient.email} on {self.scheduled_date}"
        )

    @property
    def is_upcoming(self):
        """Check if the appointment is upcoming."""
        from django.utils import timezone

        return self.scheduled_date >= timezone.now().date() and self.status in [
            "scheduled",
            "confirmed",
        ]

    @property
    def is_completed(self):
        """Check if the appointment is completed."""
        return self.status == "completed"
