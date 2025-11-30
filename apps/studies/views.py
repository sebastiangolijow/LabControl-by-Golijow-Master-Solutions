"""Views for studies app."""

from rest_framework import permissions, viewsets

from .models import Study, StudyType
from .serializers import StudySerializer, StudyTypeSerializer


class StudyTypeViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing study types."""

    queryset = StudyType.objects.filter(is_active=True)
    serializer_class = StudyTypeSerializer
    permission_classes = [permissions.IsAuthenticated]


class StudyViewSet(viewsets.ModelViewSet):
    """ViewSet for managing studies."""

    queryset = Study.objects.all()
    serializer_class = StudySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Filter studies based on user role."""
        user = self.request.user

        if user.is_superuser or user.role in ["admin", "lab_manager"]:
            # Admins and lab managers see all studies in their lab
            if user.lab_client_id:
                return Study.objects.filter(lab_client_id=user.lab_client_id)
            return Study.objects.all()
        elif user.is_patient:
            # Patients only see their own studies
            return Study.objects.filter(patient=user)
        else:
            # Doctors and technicians see all studies in their lab
            if user.lab_client_id:
                return Study.objects.filter(lab_client_id=user.lab_client_id)
            return Study.objects.none()
