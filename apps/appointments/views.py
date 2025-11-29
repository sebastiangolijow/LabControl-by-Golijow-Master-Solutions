"""Views for appointments app."""
from rest_framework import permissions, viewsets

from .models import Appointment
from .serializers import AppointmentSerializer


class AppointmentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing appointments."""

    queryset = Appointment.objects.all()
    serializer_class = AppointmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Filter appointments based on user role."""
        user = self.request.user

        if user.is_superuser or user.role in ["admin", "lab_manager"]:
            # Admins and lab managers see all appointments in their lab
            if user.lab_client_id:
                return Appointment.objects.filter(lab_client_id=user.lab_client_id)
            return Appointment.objects.all()
        elif user.is_patient:
            # Patients only see their own appointments
            return Appointment.objects.filter(patient=user)
        else:
            # Staff see all appointments in their lab
            if user.lab_client_id:
                return Appointment.objects.filter(lab_client_id=user.lab_client_id)
            return Appointment.objects.none()
