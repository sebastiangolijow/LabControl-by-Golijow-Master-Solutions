"""Views for studies app."""

import os

from django.http import FileResponse, Http404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from apps.notifications.models import Notification
from apps.notifications.tasks import send_result_notification_email
from apps.users.permissions import IsAdminOrLabManager

from .filters import DeterminationFilter, StudyFilter
from .models import Determination, Practice, Study, UserDetermination
from .serializers import (
    DeterminationSerializer,
    PracticeSerializer,
    StudyCreateSerializer,
    StudyResultUploadSerializer,
    StudySerializer,
    UserDeterminationCreateSerializer,
    UserDeterminationSerializer,
)


class PracticeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing practices (medical tests).

    Permissions:
    - All authenticated users can view practices (GET)
    - Only admins can create, update, or delete practices (POST, PUT, PATCH, DELETE)

    Search:
    - search: Search by name, technique, sample_type
    """

    queryset = Practice.objects.filter(is_active=True)
    serializer_class = PracticeSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "technique", "sample_type"]
    ordering_fields = ["name", "price", "delay_days", "created_at"]
    ordering = ["name"]

    def get_permissions(self):
        """Allow all authenticated users to read, only admins to write."""
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [IsAdminOrLabManager()]


class DeterminationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing determinations (lab test measurements).

    Permissions:
    - All authenticated users can view determinations (GET)
    - Only admins can create, update, or delete determinations (POST, PUT, PATCH, DELETE)

    Filters:
    - search: Search by name, code, description
    - is_active: Filter by active status (true/false)
    """

    queryset = Determination.objects.filter(is_active=True)
    serializer_class = DeterminationSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = DeterminationFilter
    ordering_fields = ["name", "code", "created_at"]
    ordering = ["name"]

    def get_permissions(self):
        """Allow all authenticated users to read, only admins to write."""
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [IsAdminOrLabManager()]


class UserDeterminationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing user determination results.

    Permissions:
    - Lab staff and admins can create and update results
    - Patients can view their own results
    - Doctors can view results for studies they ordered
    """

    queryset = UserDetermination.objects.all()
    serializer_class = UserDeterminationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action in ["create", "update", "partial_update"]:
            return UserDeterminationCreateSerializer
        return UserDeterminationSerializer

    def get_permissions(self):
        """Only lab staff and admins can create/update results."""
        if self.action in ["create", "update", "partial_update", "destroy"]:
            return [IsAdminOrLabManager()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        """Filter results based on user role."""
        user = self.request.user
        queryset = UserDetermination.objects.all()

        if user.is_superuser or user.role in ["admin", "lab_staff"]:
            # Admins and lab staff see all results
            return queryset
        elif user.role == "patient":
            # Patients only see their own results
            return queryset.filter(study__patient=user)
        elif user.role == "doctor":
            # Doctors see results for studies they ordered
            return queryset.filter(study__ordered_by=user)
        else:
            return UserDetermination.objects.none()


class StudyViewSet(viewsets.ModelViewSet):
    """ViewSet for managing studies."""

    queryset = Study.objects.all()
    serializer_class = StudySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        filters.OrderingFilter,
    ]
    filterset_class = StudyFilter
    ordering_fields = ["created_at", "completed_at", "protocol_number"]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == "create":
            return StudyCreateSerializer
        return StudySerializer

    def get_permissions(self):
        """Only admin and lab_staff can create studies."""
        if self.action in ["create", "last_protocol_number"]:
            return [IsAdminOrLabManager()]
        return super().get_permissions()

    def get_parsers(self):
        """Use MultiPartParser for create so files can be uploaded at creation time."""
        if getattr(self, "action", None) == "create":
            return [MultiPartParser()]
        return super().get_parsers()

    def create(self, request, *args, **kwargs):
        """
        Create a new study, optionally with a results file attached.

        - If results_file is provided → study is created as 'completed',
          completed_at is set, and the patient receives a notification.
        - If no results_file → study is created as 'pending'.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        lab_client_id = (
            request.user.lab_client_id
            if hasattr(request.user, "lab_client_id")
            else None
        )

        has_file = bool(serializer.validated_data.get("results_file"))
        study_status = "completed" if has_file else "pending"
        completed_at = timezone.now() if has_file else None

        study = serializer.save(
            lab_client_id=lab_client_id,
            status=study_status,
            completed_at=completed_at,
        )

        # If file was attached, notify patient immediately
        if has_file:
            Notification.objects.create(
                user=study.patient,
                title="Test Results Ready",
                message=f"Your {study.practice.name} results are now available.",
                notification_type="result_ready",
                related_study_id=study.pk,
                channel="in_app",
                status="sent",
                sent_at=timezone.now(),
                created_by=request.user,
            )
            send_result_notification_email.delay(
                user_id=study.patient.pk,
                study_id=study.pk,
                study_type_name=study.practice.name,
            )

        return Response(
            {
                "message": "Study created successfully.",
                "study": StudySerializer(study).data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=False,
        methods=["get"],
        permission_classes=[IsAdminOrLabManager],
        url_path="last-protocol-number",
    )
    def last_protocol_number(self, request):
        """
        Return the last used protocol number for the current lab.

        Used by the frontend to hint the next sequential number to the staff.
        """
        user = request.user
        qs = Study.objects.filter(is_deleted=False)
        if user.lab_client_id:
            qs = qs.filter(lab_client_id=user.lab_client_id)

        last = qs.order_by("-protocol_number").values_list("protocol_number", flat=True).first()
        return Response({"last_protocol_number": last})

    def get_queryset(self):
        """Filter studies based on user role."""
        user = self.request.user

        # Base queryset: exclude soft-deleted studies
        base_queryset = Study.objects.filter(is_deleted=False)

        if user.is_superuser or user.role == "admin":
            # Admins see all non-deleted studies in their lab
            # if user.lab_client_id:
            #     return base_queryset.filter(lab_client_id=user.lab_client_id)
            return base_queryset
        elif user.role == "lab_staff":
            # Lab staff see all non-deleted studies in their lab
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
        is_admin = user.is_superuser or user.role == "admin"
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
                "message": f"Study {study.protocol_number} has been deleted successfully.",
                "study_id": str(study.pk),
                "protocol_number": study.protocol_number,
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

        Only lab staff and admins can upload results.
        """
        study = self.get_object()
        user = request.user

        # Check permissions - only lab staff can upload results
        if not (user.is_superuser or user.role in ["admin", "lab_staff"]):
            return Response(
                {"error": "Only lab staff can upload results."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check if result already exists (warn but allow re-upload for admins)
        if study.is_completed and study.results_file:
            if not (user.is_superuser or user.role == "admin"):
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
            message=f"Your {study.practice.name} results are now available.",
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
            study_type_name=study.practice.name,
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
                filename=f"results_{study.protocol_number}.pdf",
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
        Delete study result file (admin and lab staff only).

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
        List all studies with uploaded results (admin and lab staff only).

        This endpoint helps admins manage and review all uploaded results.

        Query Parameters:
            - search: Search by protocol_number, patient email/name
            - status: Filter by status
            - patient: Filter by patient ID
            - practice: Filter by practice ID
            - ordering: Sort results (e.g., -completed_at, protocol_number)
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

    @action(
        detail=False,
        methods=["get"],
        permission_classes=[IsAdminOrLabManager],
        url_path="available-for-upload",
    )
    def available_for_upload(self, request):
        """
        List studies available for result upload (admin and lab staff only).

        Returns studies that are pending or in_progress and don't have results yet.
        This endpoint is used by the upload results modal to show available studies.

        Query Parameters:
            - search: Search by protocol_number, patient name
            - patient: Filter by patient ID
            - practice: Filter by practice ID
            - ordering: Sort results (default: -created_at)

        Returns:
            List of studies without uploaded results
        """
        queryset = self.filter_queryset(self.get_queryset())

        # Filter only studies without results
        queryset = queryset.filter(
            results_file__in=["", None],
            status__in=["pending", "in_progress"],
        )

        # Paginate results
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
