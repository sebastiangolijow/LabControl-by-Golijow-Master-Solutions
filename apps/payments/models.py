"""Models for payments app."""
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.core.models import BaseModel, LabClientModel
from .managers import InvoiceManager, PaymentManager


class Invoice(BaseModel, LabClientModel):
    """
    Invoice for medical services rendered.

    Tracks billing and payment status for studies and services.
    """

    STATUS_CHOICES = [
        ("draft", _("Draft")),
        ("pending", _("Pending Payment")),
        ("paid", _("Paid")),
        ("partially_paid", _("Partially Paid")),
        ("cancelled", _("Cancelled")),
        ("refunded", _("Refunded")),
    ]

    # Relationships
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="invoices",
        limit_choices_to={"role": "patient"},
    )
    study = models.ForeignKey(
        "studies.Study",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
    )

    # Invoice details
    invoice_number = models.CharField(
        _("invoice number"),
        max_length=50,
        unique=True,
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default="draft",
    )

    # Amounts
    subtotal = models.DecimalField(
        _("subtotal"),
        max_digits=10,
        decimal_places=2,
    )
    tax_amount = models.DecimalField(
        _("tax amount"),
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    discount_amount = models.DecimalField(
        _("discount amount"),
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    total_amount = models.DecimalField(
        _("total amount"),
        max_digits=10,
        decimal_places=2,
    )
    paid_amount = models.DecimalField(
        _("paid amount"),
        max_digits=10,
        decimal_places=2,
        default=0,
    )

    # Dates
    issue_date = models.DateField(_("issue date"))
    due_date = models.DateField(_("due date"))
    paid_date = models.DateField(_("paid date"), null=True, blank=True)

    # Notes
    notes = models.TextField(_("notes"), blank=True)

    # Audit trail - track all changes to invoice records
    history = HistoricalRecords()

    # Custom manager
    objects = InvoiceManager()

    class Meta:
        verbose_name = _("invoice")
        verbose_name_plural = _("invoices")
        ordering = ["-issue_date"]
        indexes = [
            models.Index(fields=["uuid"]),
            models.Index(fields=["invoice_number"]),
            models.Index(fields=["patient", "status"]),
            models.Index(fields=["lab_client_id"]),
            models.Index(fields=["status", "due_date"]),  # Common query pattern
        ]

    def __str__(self):
        return f"{self.invoice_number} - {self.total_amount}"

    @property
    def balance_due(self):
        """Calculate remaining balance."""
        return self.total_amount - self.paid_amount

    @property
    def is_paid(self):
        """Check if invoice is fully paid."""
        return self.status == "paid"


class Payment(BaseModel):
    """
    Payment transaction for an invoice.

    Records individual payment transactions and integrates with payment gateways.
    """

    PAYMENT_METHOD_CHOICES = [
        ("cash", _("Cash")),
        ("credit_card", _("Credit Card")),
        ("debit_card", _("Debit Card")),
        ("bank_transfer", _("Bank Transfer")),
        ("online", _("Online Payment")),
    ]

    STATUS_CHOICES = [
        ("pending", _("Pending")),
        ("processing", _("Processing")),
        ("completed", _("Completed")),
        ("failed", _("Failed")),
        ("refunded", _("Refunded")),
    ]

    # Relationships
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="payments",
    )

    # Payment details
    transaction_id = models.CharField(
        _("transaction ID"),
        max_length=100,
        unique=True,
    )
    amount = models.DecimalField(
        _("amount"),
        max_digits=10,
        decimal_places=2,
    )
    payment_method = models.CharField(
        _("payment method"),
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default="cash",
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    # Payment gateway integration (e.g., Stripe)
    gateway = models.CharField(_("payment gateway"), max_length=50, blank=True)
    gateway_transaction_id = models.CharField(
        _("gateway transaction ID"),
        max_length=200,
        blank=True,
    )
    gateway_response = models.JSONField(
        _("gateway response"),
        blank=True,
        null=True,
    )

    # Notes
    notes = models.TextField(_("notes"), blank=True)

    # Additional timestamp
    completed_at = models.DateTimeField(_("completed at"), null=True, blank=True)

    # Audit trail - track all changes to payment records
    history = HistoricalRecords()

    # Custom manager
    objects = PaymentManager()

    class Meta:
        verbose_name = _("payment")
        verbose_name_plural = _("payments")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["uuid"]),
            models.Index(fields=["transaction_id"]),
            models.Index(fields=["invoice", "status"]),
            models.Index(fields=["status", "created_at"]),  # Common query pattern
        ]

    def __str__(self):
        return f"{self.transaction_id} - {self.amount}"

    @property
    def is_completed(self):
        """Check if payment is completed."""
        return self.status == "completed"
