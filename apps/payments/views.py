"""Views for payments app."""

from rest_framework import permissions, viewsets

from .models import Invoice, Payment
from .serializers import InvoiceSerializer, PaymentSerializer


class InvoiceViewSet(viewsets.ModelViewSet):
    """ViewSet for managing invoices."""

    queryset = Invoice.objects.all()
    serializer_class = InvoiceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Filter invoices based on user role.

        Invoices belonging to soft-deleted patients are hidden by default;
        admin/lab_manager opt-in via ?include_deleted=true (mirrors users
        + studies).
        """
        user = self.request.user

        if user.is_superuser or user.role in ["admin", "lab_manager"]:
            if user.lab_client_id:
                qs = Invoice.objects.filter(lab_client_id=user.lab_client_id)
            else:
                qs = Invoice.objects.all()
        elif user.is_patient:
            qs = Invoice.objects.filter(patient=user)
        else:
            if user.lab_client_id:
                qs = Invoice.objects.filter(lab_client_id=user.lab_client_id)
            else:
                return Invoice.objects.none()

        include_deleted = (
            self.request.query_params.get("include_deleted", "").lower() == "true"
        )
        can_see_deleted = user.is_superuser or user.role in ("admin", "lab_manager")
        if not (include_deleted and can_see_deleted):
            qs = qs.filter(patient__deleted_at__isnull=True)

        return qs


class PaymentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing payments."""

    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Filter payments based on user role.

        Payments inherit visibility from their invoice's patient — same
        soft-delete filter as InvoiceViewSet.
        """
        user = self.request.user

        if user.is_superuser or user.role in ["admin", "lab_manager"]:
            if user.lab_client_id:
                qs = Payment.objects.filter(invoice__lab_client_id=user.lab_client_id)
            else:
                qs = Payment.objects.all()
        elif user.is_patient:
            qs = Payment.objects.filter(invoice__patient=user)
        else:
            if user.lab_client_id:
                qs = Payment.objects.filter(invoice__lab_client_id=user.lab_client_id)
            else:
                return Payment.objects.none()

        include_deleted = (
            self.request.query_params.get("include_deleted", "").lower() == "true"
        )
        can_see_deleted = user.is_superuser or user.role in ("admin", "lab_manager")
        if not (include_deleted and can_see_deleted):
            qs = qs.filter(invoice__patient__deleted_at__isnull=True)

        return qs
