"""Views for studies app."""

import os

from django.http import FileResponse
from django.http import Http404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from rest_framework import permissions
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from apps.notifications.models import Notification
from apps.notifications.tasks import send_result_notification_email
from apps.users.permissions import IsAdminOrLabManager

from .models import Study
from .models import StudyType
from .serializers import StudyResultUploadSerializer
from .serializers import StudySerializer
from .serializers import StudyTypeSerializer


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
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["status", "patient", "study_type", "lab_client_id"]
    search_fields = [
        "order_number",
        "patient__email",
        "patient__first_name",
        "patient__last_name",
    ]
    ordering_fields = ["created_at", "completed_at", "order_number"]
    ordering = ["-created_at"]

    def get_queryset(self):
        """Filter studies based on user role."""
        user = self.request.user

        # Base queryset: exclude soft-deleted studies
        base_queryset = Study.objects.filter(is_deleted=False)

        if user.is_superuser or user.role in ["admin", "lab_manager"]:
            # Admins and lab managers see all non-deleted studies in their lab
            if user.lab_client_id:
                return base_queryset.filter(lab_client_id=user.lab_client_id)
            return base_queryset
        elif user.is_patient:
            # Patients only see their own non-deleted studies
            return base_queryset.filter(patient=user)
        elif user.is_doctor:
            # Doctors only see studies they ordered
            return base_queryset.filter(ordered_by=user)
        else:
            # Technicians and other staff see all non-deleted studies in their lab
            if user.lab_client_id:
                return base_queryset.filter(lab_client_id=user.lab_client_id)
            return Study.objects.none()

    def destroy(self, request, *args, **kwargs):
        """
        Soft delete a study (set is_deleted=True).

        Permissions:
        - Admins can delete any study
        - Patients can only delete their own studies
        """
        study = self.get_object()
        user = request.user

        # Check permissions
        is_admin = user.is_superuser or user.role in ["admin", "lab_manager"]
        is_owner = user.is_patient and study.patient == user

        if not (is_admin or is_owner):
            return Response(
                {"error": "You do not have permission to delete this study."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Soft delete
        study.is_deleted = True
        study.save(update_fields=["is_deleted"])

        return Response(
            {
                "message": f"Study {study.order_number} has been deleted successfully.",
                "study_id": str(study.pk),
                "order_number": study.order_number,
            },
            status=status.HTTP_200_OK,
        )

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

        # Check if result already exists (warn but allow re-upload for admins)
        if study.is_completed and study.results_file:
            if not (user.is_superuser or user.role in ["admin", "lab_manager"]):
                return Response(
                    {
                        "error": "Results already uploaded. Only admins can replace results."
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            # For admins: delete old file before uploading new one
            if study.results_file:
                old_file_path = study.results_file.path
                if os.path.exists(old_file_path):
                    os.remove(old_file_path)

        serializer = StudyResultUploadSerializer(study, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(
            status="completed",
            completed_at=timezone.now(),
        )

        # Send in-app notification to patient
        Notification.objects.create(
            user=study.patient,
            title="Test Results Ready",
            message=f"Your {study.study_type.name} results are now available.",
            notification_type="result_ready",
            related_study_id=study.pk,
            channel="in_app",
            status="sent",
            sent_at=timezone.now(),
            created_by=request.user,
        )

        # Send email notification asynchronously via Celery
        send_result_notification_email.delay(
            user_id=study.patient.pk,
            study_id=study.pk,
            study_type_name=study.study_type.name,
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

        # Permission check
        # Patients can only download their own results
        # Doctors can only download results for studies they ordered
        if user.is_patient and study.patient != user:
            return Response(
                {"error": "You do not have permission to access these results."},
                status=status.HTTP_403_FORBIDDEN,
            )
        elif user.is_doctor and study.ordered_by != user:
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

    @action(
        detail=True,
        methods=["delete"],
        permission_classes=[IsAdminOrLabManager],
        url_path="delete-result",
    )
    def delete_result(self, request, pk=None):
        """
        Delete study result file (admin and lab manager only).

        This allows admins to remove incorrect or outdated results.
        The study status will be reset to 'in_progress'.
        """
        study = self.get_object()

        # Check if results exist
        if not study.results_file:
            return Response(
                {"error": "No results file to delete."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Delete the file from storage
        old_file_path = study.results_file.path
        if os.path.exists(old_file_path):
            os.remove(old_file_path)

        # Clear the file field and reset status
        study.results_file = None
        study.results = ""
        study.status = "in_progress"
        study.completed_at = None
        study.save(update_fields=["results_file", "results", "status", "completed_at"])

        return Response(
            {
                "message": "Results deleted successfully.",
                "study": StudySerializer(study).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(
        detail=False,
        methods=["get"],
        permission_classes=[IsAdminOrLabManager],
        url_path="with-results",
    )
    def with_results(self, request):
        """
        List all studies with uploaded results (admin and lab manager only).

        This endpoint helps admins manage and review all uploaded results.

        Query Parameters:
            - search: Search by order_number, patient email/name
            - status: Filter by status
            - patient: Filter by patient ID
            - study_type: Filter by study type ID
            - ordering: Sort results (e.g., -completed_at, order_number)
        """
        queryset = self.filter_queryset(self.get_queryset())

        # Filter only studies with results (must have actual file, not empty string)
        queryset = queryset.exclude(results_file="")

        # Paginate results
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
