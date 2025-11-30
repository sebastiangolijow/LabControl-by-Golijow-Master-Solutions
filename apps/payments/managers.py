"""Custom managers for Payment models."""
from django.db import models
from django.utils import timezone
from decimal import Decimal

from apps.core.managers import LabClientManager, LabClientQuerySet


class InvoiceQuerySet(LabClientQuerySet):
    """
    Custom queryset for Invoice model with chainable domain-specific methods.
    """

    def draft(self):
        """Return draft invoices."""
        return self.filter(status="draft")

    def pending(self):
        """Return pending invoices."""
        return self.filter(status="pending")

    def paid(self):
        """Return fully paid invoices."""
        return self.filter(status="paid")

    def partially_paid(self):
        """Return partially paid invoices."""
        return self.filter(status="partially_paid")

    def cancelled(self):
        """Return cancelled invoices."""
        return self.filter(status="cancelled")

    def refunded(self):
        """Return refunded invoices."""
        return self.filter(status="refunded")

    def unpaid(self):
        """Return unpaid invoices (pending or partially_paid)."""
        return self.filter(status__in=["pending", "partially_paid"])

    def overdue(self):
        """Return overdue invoices."""
        today = timezone.now().date()
        return self.filter(due_date__lt=today, status__in=["pending", "partially_paid"])

    def due_soon(self, days=7):
        """Return invoices due within N days."""
        today = timezone.now().date()
        future_date = today + timezone.timedelta(days=days)
        return self.filter(
            due_date__gte=today,
            due_date__lte=future_date,
            status__in=["pending", "partially_paid"],
        )

    def for_patient(self, patient):
        """Return invoices for a specific patient."""
        return self.filter(patient=patient)

    def for_study(self, study):
        """Return invoices related to a specific study."""
        return self.filter(study=study)

    def with_balance(self):
        """Return invoices with outstanding balance."""
        return self.exclude(status="paid").exclude(total_amount=models.F("paid_amount"))


class InvoiceManager(LabClientManager):
    """
    Custom manager for Invoice model.

    Provides convenient methods for common invoice queries.
    """

    def get_queryset(self):
        """Return custom queryset."""
        return InvoiceQuerySet(self.model, using=self._db)

    def draft(self):
        """Get all draft invoices."""
        return self.get_queryset().draft()

    def pending(self):
        """Get all pending invoices."""
        return self.get_queryset().pending()

    def paid(self):
        """Get all paid invoices."""
        return self.get_queryset().paid()

    def partially_paid(self):
        """Get all partially paid invoices."""
        return self.get_queryset().partially_paid()

    def cancelled(self):
        """Get all cancelled invoices."""
        return self.get_queryset().cancelled()

    def refunded(self):
        """Get all refunded invoices."""
        return self.get_queryset().refunded()

    def unpaid(self):
        """Get all unpaid invoices."""
        return self.get_queryset().unpaid()

    def overdue(self):
        """Get all overdue invoices."""
        return self.get_queryset().overdue()

    def due_soon(self, days=7):
        """Get invoices due soon."""
        return self.get_queryset().due_soon(days=days)

    def for_patient(self, patient):
        """Get invoices for a specific patient."""
        return self.get_queryset().for_patient(patient)

    def for_study(self, study):
        """Get invoices for a specific study."""
        return self.get_queryset().for_study(study)

    def with_balance(self):
        """Get invoices with outstanding balance."""
        return self.get_queryset().with_balance()


class PaymentQuerySet(models.QuerySet):
    """
    Custom queryset for Payment model with chainable domain-specific methods.
    """

    def pending(self):
        """Return pending payments."""
        return self.filter(status="pending")

    def processing(self):
        """Return processing payments."""
        return self.filter(status="processing")

    def completed(self):
        """Return completed payments."""
        return self.filter(status="completed")

    def failed(self):
        """Return failed payments."""
        return self.filter(status="failed")

    def refunded(self):
        """Return refunded payments."""
        return self.filter(status="refunded")

    def successful(self):
        """Return successful payments (completed or refunded)."""
        return self.filter(status__in=["completed", "refunded"])

    def for_invoice(self, invoice):
        """Return payments for a specific invoice."""
        return self.filter(invoice=invoice)

    def by_method(self, payment_method):
        """Return payments by payment method."""
        return self.filter(payment_method=payment_method)

    def cash_payments(self):
        """Return cash payments."""
        return self.filter(payment_method="cash")

    def card_payments(self):
        """Return card payments (credit or debit)."""
        return self.filter(payment_method__in=["credit_card", "debit_card"])

    def online_payments(self):
        """Return online payments."""
        return self.filter(payment_method="online")

    def by_gateway(self, gateway):
        """Return payments by gateway."""
        return self.filter(gateway=gateway)


class PaymentManager(models.Manager):
    """
    Custom manager for Payment model.

    Provides convenient methods for common payment queries.
    """

    def get_queryset(self):
        """Return custom queryset."""
        return PaymentQuerySet(self.model, using=self._db)

    def pending(self):
        """Get all pending payments."""
        return self.get_queryset().pending()

    def processing(self):
        """Get all processing payments."""
        return self.get_queryset().processing()

    def completed(self):
        """Get all completed payments."""
        return self.get_queryset().completed()

    def failed(self):
        """Get all failed payments."""
        return self.get_queryset().failed()

    def refunded(self):
        """Get all refunded payments."""
        return self.get_queryset().refunded()

    def successful(self):
        """Get all successful payments."""
        return self.get_queryset().successful()

    def for_invoice(self, invoice):
        """Get payments for a specific invoice."""
        return self.get_queryset().for_invoice(invoice)

    def by_method(self, payment_method):
        """Get payments by payment method."""
        return self.get_queryset().by_method(payment_method)

    def cash_payments(self):
        """Get cash payments."""
        return self.get_queryset().cash_payments()

    def card_payments(self):
        """Get card payments."""
        return self.get_queryset().card_payments()

    def online_payments(self):
        """Get online payments."""
        return self.get_queryset().online_payments()

    def by_gateway(self, gateway):
        """Get payments by gateway."""
        return self.get_queryset().by_gateway(gateway)
