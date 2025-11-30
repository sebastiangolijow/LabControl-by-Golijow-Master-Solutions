"""Serializers for payments app."""
from rest_framework import serializers

from .models import Invoice, Payment


class PaymentSerializer(serializers.ModelSerializer):
    """Serializer for Payment model."""

    class Meta:
        model = Payment
        fields = [
            "id",
            "uuid",
            "transaction_id",
            "amount",
            "payment_method",
            "status",
            "notes",
            "created_at",
            "completed_at",
        ]
        read_only_fields = ["uuid", "transaction_id", "created_at"]


class InvoiceSerializer(serializers.ModelSerializer):
    """Serializer for Invoice model."""

    payments = PaymentSerializer(many=True, read_only=True)
    balance_due = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    patient_email = serializers.EmailField(source="patient.email", read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "uuid",
            "invoice_number",
            "patient",
            "patient_email",
            "study",
            "status",
            "subtotal",
            "tax_amount",
            "discount_amount",
            "total_amount",
            "paid_amount",
            "balance_due",
            "issue_date",
            "due_date",
            "paid_date",
            "notes",
            "payments",
            "created_at",
        ]
        read_only_fields = ["uuid", "invoice_number", "created_at"]
