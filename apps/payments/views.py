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
        """Filter invoices based on user role."""
        user = self.request.user

        if user.is_superuser or user.role in ["admin", "lab_manager"]:
            # Admins and lab managers see all invoices in their lab
            if user.lab_client_id:
                return Invoice.objects.filter(lab_client_id=user.lab_client_id)
            return Invoice.objects.all()
        elif user.is_patient:
            # Patients only see their own invoices
            return Invoice.objects.filter(patient=user)
        else:
            # Staff see all invoices in their lab
            if user.lab_client_id:
                return Invoice.objects.filter(lab_client_id=user.lab_client_id)
            return Invoice.objects.none()


class PaymentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing payments."""

    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Filter payments based on user role."""
        user = self.request.user

        if user.is_superuser or user.role in ["admin", "lab_manager"]:
            # Admins see all payments in their lab
            if user.lab_client_id:
                return Payment.objects.filter(
                    invoice__lab_client_id=user.lab_client_id
                )
            return Payment.objects.all()
        elif user.is_patient:
            # Patients see payments for their invoices
            return Payment.objects.filter(invoice__patient=user)
        else:
            # Staff see all payments in their lab
            if user.lab_client_id:
                return Payment.objects.filter(
                    invoice__lab_client_id=user.lab_client_id
                )
            return Payment.objects.none()
