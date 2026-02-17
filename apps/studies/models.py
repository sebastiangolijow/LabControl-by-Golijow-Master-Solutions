"""Models for studies app."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.core.models import BaseModel, LabClientModel

from .managers import StudyManager


class Determination(BaseModel):
    """
    Determination/analyte that can be measured in a practice.

    Examples: Glucose, Hemoglobin, White Blood Cell Count, etc.
    One determination can be part of multiple practices.
    """

    name = models.CharField(_("name"), max_length=200)
    code = models.CharField(_("code"), max_length=50, unique=True)
    unit = models.CharField(
        _("unit"),
        max_length=50,
        blank=True,
        help_text=_("Unit of measurement (e.g., mg/dL, g/L, cells/μL)"),
    )
    reference_range = models.CharField(
        _("reference range"),
        max_length=200,
        blank=True,
        help_text=_("Normal reference range for this determination"),
    )
    description = models.TextField(_("description"), blank=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("determination")
        verbose_name_plural = _("determinations")
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


class Practice(BaseModel):
    """
    Medical practice/test that can be ordered.

    Each practice represents a specific medical test or procedure with its
    requirements and specifications. A practice can include multiple determinations.
    """

    name = models.CharField(_("name"), max_length=200)
    technique = models.CharField(
        _("technique"),
        max_length=200,
        blank=True,
        help_text=_("Laboratory technique used for this practice"),
    )

    # Sample information
    sample_type = models.CharField(
        _("sample type"),
        max_length=100,
        blank=True,
        help_text=_("Type of sample required (e.g., blood, urine, tissue)"),
    )
    sample_quantity = models.CharField(
        _("sample quantity"),
        max_length=100,
        blank=True,
        help_text=_("Required quantity of sample"),
    )
    sample_instructions = models.TextField(
        _("sample instructions"),
        blank=True,
        help_text=_("Special instructions for sample collection"),
    )

    # Conservation and transport
    conservation_transport = models.TextField(
        _("conservation and transport"),
        blank=True,
        help_text=_("Instructions for sample conservation and transport"),
    )

    # Processing time
    delay_days = models.IntegerField(
        _("delay (days)"),
        default=0,
        help_text=_("Expected delay in days for results"),
    )

    # Pricing
    price = models.DecimalField(
        _("price"),
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text=_("Price for this practice"),
    )

    # Determinations relationship
    determinations = models.ManyToManyField(
        Determination,
        related_name="practices",
        blank=True,
        verbose_name=_("determinations"),
        help_text=_("Determinations/analytes included in this practice"),
    )

    # Status
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("practice")
        verbose_name_plural = _("practices")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Study(BaseModel, LabClientModel):
    """
    Individual study/test order for a patient.

    Tracks the lifecycle of a medical test from order to completion.
    """

    STATUS_CHOICES = [
        ("pending", _("Pending")),
        ("sample_collected", _("Sample Collected")),
        ("in_progress", _("In Progress")),
        ("completed", _("Completed")),
        ("cancelled", _("Cancelled")),
    ]

    # Relationships
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="studies",
        limit_choices_to={"role": "patient"},
    )
    practice = models.ForeignKey(
        Practice,
        on_delete=models.PROTECT,
        related_name="studies",
        help_text=_("The practice/test being ordered"),
    )
    ordered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordered_studies",
        limit_choices_to={"role": "doctor"},
        help_text=_("Doctor who ordered the study"),
    )

    # Study details
    protocol_number = models.CharField(
        _("protocol number"),
        max_length=50,
        unique=True,
        help_text=_("Unique protocol identifier for this study"),
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    # Dates
    solicited_date = models.DateField(
        _("solicited date"),
        null=True,
        blank=True,
        help_text=_("Date the study was requested/ordered by the doctor"),
    )

    # Sample information
    sample_id = models.CharField(_("sample ID"), max_length=50, blank=True)
    sample_collected_at = models.DateTimeField(
        _("sample collected at"),
        null=True,
        blank=True,
        help_text=_("Date and time the physical sample was collected from the patient"),
    )

    # Results
    results = models.TextField(_("results"), blank=True)
    results_file = models.FileField(
        _("results file"),
        upload_to="study_results/%Y/%m/",
        blank=True,
        null=True,
    )
    completed_at = models.DateTimeField(_("completed at"), null=True, blank=True)

    # Notes
    notes = models.TextField(_("notes"), blank=True)
    internal_notes = models.TextField(
        _("internal notes"),
        blank=True,
        help_text=_("Internal notes not visible to patient"),
    )

    # Soft delete
    is_deleted = models.BooleanField(
        _("is deleted"),
        default=False,
        help_text=_("Soft delete flag - deleted studies are hidden but preserved"),
    )

    # Custom manager
    objects = StudyManager()

    # Audit trail
    # Configure history to use UUID for history_user_id (matches User model UUID)
    history = HistoricalRecords(
        history_user_id_field=models.UUIDField(null=True, blank=True)
    )

    class Meta:
        verbose_name = _("study")
        verbose_name_plural = _("studies")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["protocol_number"]),
            models.Index(fields=["patient", "status"]),
            models.Index(fields=["lab_client_id"]),
        ]

    def __str__(self):
        return f"{self.protocol_number} - {self.practice.name}"

    def clean(self):
        """Validate that ordered_by is a doctor."""
        super().clean()
        if self.ordered_by and self.ordered_by.role != "doctor":
            raise ValidationError(
                {
                    "ordered_by": _(
                        "Only users with 'doctor' role can be assigned to ordered_by field."
                    )
                }
            )

    @property
    def is_completed(self):
        """Check if the study is completed."""
        return self.status == "completed"

    @property
    def is_pending(self):
        """Check if the study is pending."""
        return self.status == "pending"


class UserDetermination(BaseModel):
    """
    Stores the result value of a determination for a specific user/study.

    Links a patient's study with specific determination results.
    """

    study = models.ForeignKey(
        Study,
        on_delete=models.CASCADE,
        related_name="determination_results",
        help_text=_("The study this result belongs to"),
    )
    determination = models.ForeignKey(
        Determination,
        on_delete=models.PROTECT,
        related_name="user_results",
        help_text=_("The determination being measured"),
    )
    value = models.CharField(
        _("value"),
        max_length=200,
        help_text=_("The measured value for this determination"),
    )
    is_abnormal = models.BooleanField(
        _("abnormal"),
        default=False,
        help_text=_("Flag if value is outside normal range"),
    )
    notes = models.TextField(
        _("notes"),
        blank=True,
        help_text=_("Additional notes about this result"),
    )

    class Meta:
        verbose_name = _("user determination")
        verbose_name_plural = _("user determinations")
        ordering = ["study", "determination"]
        unique_together = [["study", "determination"]]

    def __str__(self):
        return f"{self.study.protocol_number} - {self.determination.name}: {self.value}"
