"""Views for appointments app."""

from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.notifications.models import Notification

from .models import Appointment
from .serializers import AppointmentCreateSerializer, AppointmentSerializer


class AppointmentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing appointments."""

    queryset = Appointment.objects.all()
    serializer_class = AppointmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == "create":
            return AppointmentCreateSerializer
        return AppointmentSerializer

    def get_queryset(self):
        """Filter appointments based on user role.

        Appointments belonging to soft-deleted patients are hidden by
        default. Admin/lab_manager can opt-in with ?include_deleted=true
        for the same audit-recovery toggle used on the users list.
        """
        user = self.request.user

        if user.is_superuser or user.role in ["admin", "lab_manager"]:
            if user.lab_client_id:
                qs = Appointment.objects.filter(lab_client_id=user.lab_client_id)
            else:
                qs = Appointment.objects.all()
        elif user.is_patient:
            qs = Appointment.objects.filter(patient=user)
        else:
            if user.lab_client_id:
                qs = Appointment.objects.filter(lab_client_id=user.lab_client_id)
            else:
                return Appointment.objects.none()

        include_deleted = (
            self.request.query_params.get("include_deleted", "").lower() == "true"
        )
        can_see_deleted = user.is_superuser or user.role in ("admin", "lab_manager")
        if not (include_deleted and can_see_deleted):
            qs = qs.filter(patient__deleted_at__isnull=True)

        return qs

    def create(self, request, *args, **kwargs):
        """
        Create appointment and send confirmation notification.

        Override to return full serializer data in response.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # If user is a patient, force the patient field to be themselves
        if request.user.is_patient:
            appointment = serializer.save(
                patient=request.user,
                lab_client_id=request.user.lab_client_id,
            )
        else:
            appointment = serializer.save()

        # Send confirmation notification
        Notification.objects.create(
            user=appointment.patient,
            title="Appointment Confirmed",
            message=f"Your appointment on {appointment.scheduled_date} at {appointment.scheduled_time} has been confirmed.",
            notification_type="appointment_reminder",
            related_appointment_id=appointment.pk,
            channel="in_app",
            status="sent",
            sent_at=timezone.now(),
            created_by=request.user if not request.user.is_patient else None,
        )

        # Return full appointment data using the read serializer
        response_serializer = AppointmentSerializer(appointment)
        headers = self.get_success_headers(response_serializer.data)
        return Response(
            response_serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    @action(detail=False, methods=["get"])
    def upcoming(self, request):
        """Get upcoming appointments for the current user."""
        queryset = (
            self.get_queryset()
            .filter(
                scheduled_date__gte=timezone.now().date(),
                status__in=["scheduled", "confirmed"],
            )
            .order_by("scheduled_date", "scheduled_time")
        )

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Cancel an appointment."""
        appointment = self.get_object()

        if appointment.status == "cancelled":
            return Response(
                {"error": "Appointment is already cancelled."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if appointment.status == "completed":
            return Response(
                {"error": "Cannot cancel a completed appointment."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        appointment.status = "cancelled"
        appointment.save()

        # Send cancellation notification
        Notification.objects.create(
            user=appointment.patient,
            title="Appointment Cancelled",
            message=f"Your appointment on {appointment.scheduled_date} has been cancelled.",
            notification_type="info",
            related_appointment_id=appointment.pk,
            channel="in_app",
            status="sent",
            sent_at=timezone.now(),
            created_by=request.user,
        )

        return Response(
            {
                "message": "Appointment cancelled successfully.",
                "appointment": AppointmentSerializer(appointment).data,
            }
        )
