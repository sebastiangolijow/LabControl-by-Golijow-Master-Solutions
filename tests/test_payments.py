"""Tests for payments app following TDD principles."""
from datetime import date, timedelta
from decimal import Decimal
from django.utils import timezone
from tests.base import BaseTestCase
from apps.payments.models import Invoice, Payment
from rest_framework import status


class TestInvoiceModel(BaseTestCase):
    """Test cases for Invoice model."""

    def test_create_invoice(self):
        """Test creating an invoice."""
        patient = self.create_patient()
        invoice = self.create_invoice(patient=patient)

        assert invoice.patient == patient
        assert invoice.status == "pending"
        assert invoice.total_amount == Decimal("110.00")
        assert invoice.invoice_number is not None

    def test_invoice_has_uuid(self):
        """Test that invoice has UUID field."""
        invoice = self.create_invoice()
        self.assertUUID(invoice.uuid)

    def test_invoice_has_timestamps(self):
        """Test that invoice has timestamp fields."""
        invoice = self.create_invoice()
        self.assertIsNotNone(invoice.created_at)
        self.assertIsNotNone(invoice.updated_at)
        self.assertTimestampRecent(invoice.created_at)

    def test_invoice_has_audit_trail(self):
        """Test that invoice has history tracking."""
        invoice = self.create_invoice()
        assert hasattr(invoice, "history")
        assert invoice.history.count() == 1  # Created

        # Update invoice
        invoice.status = "paid"
        invoice.save()
        assert invoice.history.count() == 2  # Created + Updated

    def test_invoice_created_by(self):
        """Test created_by field."""
        admin = self.create_admin()
        invoice = self.create_invoice(created_by=admin)

        assert invoice.created_by == admin

    def test_invoice_str_representation(self):
        """Test invoice string representation."""
        invoice = self.create_invoice(
            invoice_number="INV-001",
            total_amount=Decimal("150.00"),
        )
        assert str(invoice) == "INV-001 - 150.00"

    def test_invoice_balance_due(self):
        """Test balance_due property."""
        invoice = self.create_invoice(
            total_amount=Decimal("100.00"),
            paid_amount=Decimal("0.00"),
        )
        assert invoice.balance_due == Decimal("100.00")

        invoice.paid_amount = Decimal("40.00")
        assert invoice.balance_due == Decimal("60.00")

    def test_invoice_is_paid_property(self):
        """Test is_paid property."""
        invoice = self.create_invoice(status="pending")
        assert invoice.is_paid is False

        invoice.status = "paid"
        invoice.save()
        assert invoice.is_paid is True

    def test_invoice_with_study(self):
        """Test invoice linked to a study."""
        patient = self.create_patient()
        study = self.create_study(patient=patient)
        invoice = self.create_invoice(patient=patient, study=study)

        assert invoice.study == study
        assert invoice in study.invoices.all()


class TestPaymentModel(BaseTestCase):
    """Test cases for Payment model."""

    def test_create_payment(self):
        """Test creating a payment."""
        invoice = self.create_invoice()
        payment = self.create_payment(invoice=invoice)

        assert payment.invoice == invoice
        assert payment.status == "completed"
        assert payment.transaction_id is not None

    def test_payment_has_uuid(self):
        """Test that payment has UUID field."""
        payment = self.create_payment()
        self.assertUUID(payment.uuid)

    def test_payment_has_timestamps(self):
        """Test that payment has timestamp fields."""
        payment = self.create_payment()
        self.assertIsNotNone(payment.created_at)
        self.assertIsNotNone(payment.updated_at)
        self.assertTimestampRecent(payment.created_at)

    def test_payment_has_audit_trail(self):
        """Test that payment has history tracking."""
        payment = self.create_payment()
        assert hasattr(payment, "history")
        assert payment.history.count() == 1  # Created

        # Update payment
        payment.status = "refunded"
        payment.save()
        assert payment.history.count() == 2  # Created + Updated

    def test_payment_created_by(self):
        """Test created_by field."""
        admin = self.create_admin()
        payment = self.create_payment(created_by=admin)

        assert payment.created_by == admin

    def test_payment_str_representation(self):
        """Test payment string representation."""
        payment = self.create_payment(
            transaction_id="TXN-001",
            amount=Decimal("50.00"),
        )
        assert str(payment) == "TXN-001 - 50.00"

    def test_payment_is_completed_property(self):
        """Test is_completed property."""
        payment = self.create_payment(status="pending")
        assert payment.is_completed is False

        payment.status = "completed"
        payment.save()
        assert payment.is_completed is True


class TestInvoiceManager(BaseTestCase):
    """Test cases for Invoice custom manager."""

    def test_pending_invoices(self):
        """Test InvoiceManager.pending() method."""
        pending = self.create_invoice(status="pending")
        paid = self.create_invoice(status="paid")

        pending_invoices = Invoice.objects.pending()
        assert pending in pending_invoices
        assert paid not in pending_invoices

    def test_paid_invoices(self):
        """Test InvoiceManager.paid() method."""
        pending = self.create_invoice(status="pending")
        paid = self.create_invoice(status="paid")

        paid_invoices = Invoice.objects.paid()
        assert paid in paid_invoices
        assert pending not in paid_invoices

    def test_partially_paid_invoices(self):
        """Test InvoiceManager.partially_paid() method."""
        pending = self.create_invoice(status="pending")
        partially = self.create_invoice(status="partially_paid")

        partially_paid_invoices = Invoice.objects.partially_paid()
        assert partially in partially_paid_invoices
        assert pending not in partially_paid_invoices

    def test_unpaid_invoices(self):
        """Test InvoiceManager.unpaid() method."""
        pending = self.create_invoice(status="pending")
        partially = self.create_invoice(status="partially_paid")
        paid = self.create_invoice(status="paid")

        unpaid_invoices = Invoice.objects.unpaid()
        assert pending in unpaid_invoices
        assert partially in unpaid_invoices
        assert paid not in unpaid_invoices

    def test_overdue_invoices(self):
        """Test InvoiceManager.overdue() method."""
        past_date = timezone.now().date() - timedelta(days=7)
        future_date = timezone.now().date() + timedelta(days=7)

        overdue = self.create_invoice(
            status="pending",
            due_date=past_date,
        )
        not_overdue = self.create_invoice(
            status="pending",
            due_date=future_date,
        )

        overdue_invoices = Invoice.objects.overdue()
        assert overdue in overdue_invoices
        assert not_overdue not in overdue_invoices

    def test_due_soon_invoices(self):
        """Test InvoiceManager.due_soon() method."""
        today = timezone.now().date()
        tomorrow = today + timedelta(days=1)
        next_month = today + timedelta(days=30)

        due_soon = self.create_invoice(
            status="pending",
            due_date=tomorrow,
        )
        not_due_soon = self.create_invoice(
            status="pending",
            due_date=next_month,
        )

        due_soon_invoices = Invoice.objects.due_soon(days=7)
        assert due_soon in due_soon_invoices
        assert not_due_soon not in due_soon_invoices

    def test_for_patient(self):
        """Test InvoiceManager.for_patient() method."""
        patient1 = self.create_patient()
        patient2 = self.create_patient(email="patient2@test.com")

        inv1 = self.create_invoice(patient=patient1)
        inv2 = self.create_invoice(patient=patient2)

        patient1_invoices = Invoice.objects.for_patient(patient1)
        assert inv1 in patient1_invoices
        assert inv2 not in patient1_invoices

    def test_for_study(self):
        """Test InvoiceManager.for_study() method."""
        patient = self.create_patient()
        study1 = self.create_study(patient=patient)
        study2 = self.create_study(patient=patient)

        inv1 = self.create_invoice(patient=patient, study=study1)
        inv2 = self.create_invoice(patient=patient, study=study2)

        study1_invoices = Invoice.objects.for_study(study1)
        assert inv1 in study1_invoices
        assert inv2 not in study1_invoices

    def test_for_lab(self):
        """Test InvoiceManager.for_lab() method."""
        lab1_invoice = self.create_invoice(lab_client_id=1)
        lab2_invoice = self.create_invoice(lab_client_id=2)

        lab1_invoices = Invoice.objects.for_lab(1)
        assert lab1_invoice in lab1_invoices
        assert lab2_invoice not in lab1_invoices

    def test_chainable_queries(self):
        """Test that manager methods are chainable."""
        today = timezone.now().date()
        past_date = today - timedelta(days=7)

        lab1_overdue = self.create_invoice(
            lab_client_id=1,
            status="pending",
            due_date=past_date,
        )
        lab2_overdue = self.create_invoice(
            lab_client_id=2,
            status="pending",
            due_date=past_date,
        )
        lab1_paid = self.create_invoice(
            lab_client_id=1,
            status="paid",
            due_date=past_date,
        )

        # Chain: overdue unpaid invoices in lab 1
        result = Invoice.objects.for_lab(1).overdue().unpaid()

        assert lab1_overdue in result
        assert lab2_overdue not in result
        assert lab1_paid not in result


class TestPaymentManager(BaseTestCase):
    """Test cases for Payment custom manager."""

    def test_pending_payments(self):
        """Test PaymentManager.pending() method."""
        pending = self.create_payment(status="pending")
        completed = self.create_payment(status="completed")

        pending_payments = Payment.objects.pending()
        assert pending in pending_payments
        assert completed not in pending_payments

    def test_completed_payments(self):
        """Test PaymentManager.completed() method."""
        pending = self.create_payment(status="pending")
        completed = self.create_payment(status="completed")

        completed_payments = Payment.objects.completed()
        assert completed in completed_payments
        assert pending not in completed_payments

    def test_failed_payments(self):
        """Test PaymentManager.failed() method."""
        completed = self.create_payment(status="completed")
        failed = self.create_payment(status="failed")

        failed_payments = Payment.objects.failed()
        assert failed in failed_payments
        assert completed not in failed_payments

    def test_successful_payments(self):
        """Test PaymentManager.successful() method."""
        completed = self.create_payment(status="completed")
        refunded = self.create_payment(status="refunded")
        failed = self.create_payment(status="failed")

        successful_payments = Payment.objects.successful()
        assert completed in successful_payments
        assert refunded in successful_payments
        assert failed not in successful_payments

    def test_for_invoice(self):
        """Test PaymentManager.for_invoice() method."""
        invoice1 = self.create_invoice()
        invoice2 = self.create_invoice()

        pay1 = self.create_payment(invoice=invoice1)
        pay2 = self.create_payment(invoice=invoice2)

        invoice1_payments = Payment.objects.for_invoice(invoice1)
        assert pay1 in invoice1_payments
        assert pay2 not in invoice1_payments

    def test_by_method(self):
        """Test PaymentManager.by_method() method."""
        cash = self.create_payment(payment_method="cash")
        card = self.create_payment(payment_method="credit_card")

        cash_payments = Payment.objects.by_method("cash")
        assert cash in cash_payments
        assert card not in cash_payments

    def test_cash_payments(self):
        """Test PaymentManager.cash_payments() method."""
        cash = self.create_payment(payment_method="cash")
        card = self.create_payment(payment_method="credit_card")

        cash_payments = Payment.objects.cash_payments()
        assert cash in cash_payments
        assert card not in cash_payments

    def test_card_payments(self):
        """Test PaymentManager.card_payments() method."""
        cash = self.create_payment(payment_method="cash")
        credit = self.create_payment(payment_method="credit_card")
        debit = self.create_payment(payment_method="debit_card")

        card_payments = Payment.objects.card_payments()
        assert credit in card_payments
        assert debit in card_payments
        assert cash not in card_payments


class TestPaymentAPI(BaseTestCase):
    """Test cases for Payment API endpoints."""

    def test_list_patient_invoices(self):
        """Test patient can see their own invoices."""
        client, patient = self.authenticate_as_patient()
        invoice = self.create_invoice(patient=patient)

        response = client.get("/api/v1/payments/invoices/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["invoice_number"] == invoice.invoice_number

    def test_patient_cannot_see_other_invoices(self):
        """Test patient cannot see other patients' invoices."""
        client, patient1 = self.authenticate_as_patient()
        patient2 = self.create_patient(email="other@test.com")

        own_invoice = self.create_invoice(patient=patient1)
        other_invoice = self.create_invoice(patient=patient2)

        response = client.get("/api/v1/payments/invoices/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["id"] == own_invoice.id

    def test_lab_manager_can_see_lab_invoices(self):
        """Test lab manager can see all invoices for their lab."""
        client, manager = self.authenticate_as_lab_manager(lab_client_id=1)

        # Create invoices for different labs
        lab1_inv = self.create_invoice(lab_client_id=1)
        lab2_inv = self.create_invoice(lab_client_id=2)

        response = client.get("/api/v1/payments/invoices/")
        assert response.status_code == status.HTTP_200_OK

        invoice_ids = [inv["id"] for inv in response.data["results"]]
        assert lab1_inv.id in invoice_ids
        assert lab2_inv.id not in invoice_ids

    def test_invoice_uuid_in_api_response(self):
        """Test that UUID is included in API responses."""
        client, patient = self.authenticate_as_patient()
        invoice = self.create_invoice(patient=patient)

        response = client.get("/api/v1/payments/invoices/")
        assert response.status_code == status.HTTP_200_OK
        assert "uuid" in response.data["results"][0]
        self.assertUUID(invoice.uuid)

    def test_payment_uuid_in_api_response(self):
        """Test that Payment UUID is included in nested API responses."""
        client, patient = self.authenticate_as_patient()
        invoice = self.create_invoice(patient=patient)
        payment = self.create_payment(invoice=invoice)

        response = client.get("/api/v1/payments/invoices/")
        assert response.status_code == status.HTTP_200_OK
        payments_list = response.data["results"][0]["payments"]
        assert len(payments_list) == 1
        assert "uuid" in payments_list[0]
        self.assertUUID(payment.uuid)
