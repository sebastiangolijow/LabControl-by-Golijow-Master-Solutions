"""Tests for payments app."""
import pytest
from decimal import Decimal
from datetime import date
from apps.payments.models import Invoice, Payment
from rest_framework import status


@pytest.fixture
def invoice(db, user):
    """Fixture for creating an invoice."""
    return Invoice.objects.create(
        patient=user,
        invoice_number="INV-2024-001",
        status="pending",
        subtotal=Decimal("100.00"),
        tax_amount=Decimal("10.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("110.00"),
        paid_amount=Decimal("0.00"),
        issue_date=date(2024, 1, 1),
        due_date=date(2024, 1, 15),
        lab_client_id=1,
    )


@pytest.fixture
def payment(db, invoice):
    """Fixture for creating a payment."""
    return Payment.objects.create(
        invoice=invoice,
        transaction_id="TXN-2024-001",
        amount=Decimal("110.00"),
        payment_method="credit_card",
        status="completed",
    )


@pytest.mark.django_db
class TestInvoiceModel:
    """Test cases for Invoice model."""

    def test_create_invoice(self, invoice):
        """Test creating an invoice."""
        assert invoice.invoice_number == "INV-2024-001"
        assert invoice.total_amount == Decimal("110.00")
        assert invoice.status == "pending"

    def test_invoice_balance_due(self, invoice):
        """Test calculating balance due."""
        assert invoice.balance_due == Decimal("110.00")
        invoice.paid_amount = Decimal("50.00")
        assert invoice.balance_due == Decimal("60.00")

    def test_invoice_is_paid(self, invoice):
        """Test invoice paid status."""
        assert invoice.is_paid is False
        invoice.status = "paid"
        assert invoice.is_paid is True


@pytest.mark.django_db
class TestPaymentModel:
    """Test cases for Payment model."""

    def test_create_payment(self, payment):
        """Test creating a payment."""
        assert payment.transaction_id == "TXN-2024-001"
        assert payment.amount == Decimal("110.00")
        assert payment.is_completed is True


@pytest.mark.django_db
class TestPaymentAPI:
    """Test cases for Payment API endpoints."""

    def test_list_patient_invoices(self, authenticated_client, invoice):
        """Test patient can see their own invoices."""
        response = authenticated_client.get("/api/v1/payments/invoices/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["invoice_number"] == invoice.invoice_number
