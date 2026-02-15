"""Models for studies app."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.core.models import BaseModel
from apps.core.models import LabClientModel

from .managers import StudyManager
from .managers import StudyTypeManager

# Class determinaciones(BaseModel):
#     nombre
#     cod
#     estimaciones = model.models.CharField(_(""), max_length=50)


# class userestimatmato:
#     fk
#     fk
#     valor

class Practice(BaseModel):
    """
    Medical practice/test that can be included in study types (protocols).

    Each practice represents a specific medical test or procedure with its
    requirements and specifications.
    """

    name = models.CharField(_("name"), max_length=200)
    technique = models.CharField(
        _("technique"),
        max_length=200,
        blank=True,
        help_text=_("Laboratory technique used for this practice"),
    )
    num_protocolo = models.CharField()

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

    # Status
    is_active = models.BooleanField(_("active"), default=True)
    determinaciones = ... -->

    class Meta:
        verbose_name = _("practice")
        verbose_name_plural = _("practices")
        ordering = ["name"]

    def __str__(self):
        return self.name


class StudyType(BaseModel):  # Protocolo | Estudio
    """
    Type of medical study/test offered by the laboratory.

    Examples: Blood Test, X-Ray, MRI, COVID-19 Test, etc.
    """

    name = models.CharField(_("name"), max_length=200)
    code = models.CharField(_("code"), max_length=50, unique=True)
    description = models.TextField(_("description"), blank=True)
    category = models.CharField(_("category"), max_length=100, blank=True)

    # Requirements
    requires_fasting = models.BooleanField(_("requires fasting"), default=False)
    preparation_instructions = models.TextField(
        _("preparation instructions"), blank=True
    )

    # Processing time
    estimated_processing_hours = models.IntegerField(
        _("estimated processing time (hours)"),
        default=24,
    )

    # Protocol practices (catalog information)
    # ManyToMany relationship with Practice model
    practices = models.ManyToManyField(
        Practice,
        related_name="study_types",
        blank=True,
        verbose_name=_("practices"),
        help_text=_("Practices/tests included in this protocol"),
    )

    # Status
    is_active = models.BooleanField(_("active"), default=True)

    # Custom manager
    objects = StudyTypeManager()

    class Meta:
        verbose_name = _("study type")
        verbose_name_plural = _("study types")
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


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
    study_type = models.ForeignKey(
        StudyType,
        on_delete=models.PROTECT,
        related_name="studies",
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
    order_number = models.CharField(
        _("order number"),
        max_length=50,
        unique=True,
        help_text=_("Unique identifier for this study"),
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    # Sample information
    sample_id = models.CharField(_("sample ID"), max_length=50, blank=True)
    sample_collected_at = models.DateTimeField(
        _("sample collected at"), null=True, blank=True
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
            models.Index(fields=["order_number"]),
            models.Index(fields=["patient", "status"]),
            models.Index(fields=["lab_client_id"]),
        ]

    def __str__(self):
        return f"{self.order_number} - {self.study_type.name}"

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
