"""Views for studies app."""

from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from apps.notifications.models import Notification

from .models import Study, StudyType
from .serializers import StudyResultUploadSerializer, StudySerializer, StudyTypeSerializer


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

    @action(
        detail=True,
        methods=["post"],
        parser_classes=[MultiPartParser],
        permission_classes=[permissions.IsAuthenticated],
    )
    def upload_result(self, request, pk=None):
        """
        Upload study results (PDF or file).

        Only lab staff, lab managers, and admins can upload results.
        """
        study = self.get_object()
        user = request.user

        # Check permissions - only lab staff can upload results
        if not (
            user.is_superuser
            or user.role in ["admin", "lab_manager", "lab_staff", "technician", "staff"]
        ):
            return Response(
                {"error": "Only lab staff can upload results."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check if result already exists
        if study.is_completed and study.results_file:
            return Response(
                {
                    "error": "Results already uploaded. Delete existing results first."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = StudyResultUploadSerializer(study, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(
            status="completed",
            completed_at=timezone.now(),
        )

        # Send notification to patient
        Notification.objects.create(
            user=study.patient,
            title="Test Results Ready",
            message=f"Your {study.study_type.name} results are now available.",
            notification_type="result_ready",
            related_study_id=study.id,
            channel="in_app",
            status="sent",
            sent_at=timezone.now(),
            created_by=request.user,
        )

        return Response(
            {
                "message": "Results uploaded successfully.",
                "study": StudySerializer(study).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(
        detail=True,
        methods=["get"],
        permission_classes=[permissions.IsAuthenticated],
    )
    def download_result(self, request, pk=None):
        """
        Download study results file.

        Patients can only download their own results.
        Lab staff can download any results in their lab.
        """
        study = self.get_object()
        user = request.user

        # Check if results exist
        if not study.results_file:
            return Response(
                {"error": "No results file available for this study."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Permission check - patients can only download their own results
        if user.is_patient and study.patient != user:
            return Response(
                {"error": "You do not have permission to access these results."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Return file response
        try:
            return FileResponse(
                study.results_file.open("rb"),
                as_attachment=True,
                filename=f"results_{study.order_number}.pdf",
            )
        except Exception as e:
            raise Http404(f"File not found: {str(e)}")
