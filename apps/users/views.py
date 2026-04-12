"""Views for users app."""

import csv
import io

from django.db.models import Q, Value
from django.db.models.functions import Concat
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .filters import UserFilter
from .models import User
from .permissions import IsAdmin, IsAdminOrLabManager
from .serializers import (
    AdminUserCreateSerializer,
    PatientRegistrationSerializer,
    UserCreateSerializer,
    UserDetailSerializer,
    UserSerializer,
    UserUpdateSerializer,
)


class UserViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing users.

    Provides CRUD operations for user management.
    """

    queryset = User.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        filters.OrderingFilter,
    ]
    filterset_class = UserFilter
    ordering_fields = ["date_joined", "email", "first_name", "last_name"]
    ordering = ["-date_joined"]

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == "create":
            return UserCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return UserUpdateSerializer
        elif self.action in ["retrieve", "list"]:
            return UserDetailSerializer
        return UserSerializer

    def get_permissions(self):
        """Set permissions based on action."""
        if self.action == "destroy":
            # Only admins and superusers can delete users
            return [IsAdmin()]
        return super().get_permissions()

    def get_queryset(self):
        """
        Filter queryset based on user role and permissions.

        - Superusers and admins can see all users
        - Lab staff can see users in their lab
        - Doctors can only see patients
        - Others can only see themselves
        - Only active users are shown (is_active=True)
        """
        user = self.request.user

        if user.is_superuser or user.role == "admin":
            return User.objects.filter(is_active=True)
        elif user.role == "lab_staff" and user.lab_client_id:
            return User.objects.filter(lab_client_id=user.lab_client_id, is_active=True)
        elif user.role == "doctor":
            # Doctors can only see their own patients (patients with studies ordered by them)
            return user.patients.filter(is_active=True)
        else:
            return User.objects.filter(pk=user.pk)

    def destroy(self, request, *args, **kwargs):
        """
        Delete a user (admin only).

        Implements soft delete by setting is_active=False instead of hard deletion.
        This preserves data integrity and allows for potential account recovery.

        Security checks:
        - Prevents users from deleting themselves
        - Prevents non-superusers from deleting superuser accounts
        - Requires IsAdmin permission (enforced by get_permissions)

        Returns:
            Response: Success message with 200 status or error with appropriate status
        """
        user_to_delete = self.get_object()

        # Prevent self-deletion
        if user_to_delete.pk == request.user.pk:
            return Response(
                {"error": "You cannot delete your own account."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Prevent deleting superusers (unless you're also a superuser)
        if user_to_delete.is_superuser and not request.user.is_superuser:
            return Response(
                {"error": "You cannot delete a superuser account."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Soft delete - deactivate the user instead of deleting
        user_to_delete.is_active = False
        user_to_delete.save(update_fields=["is_active"])

        # Log the deactivation for audit trail
        return Response(
            {
                "message": f"User {user_to_delete.email} has been deactivated successfully.",
                "user_id": str(user_to_delete.pk),
                "email": user_to_delete.email,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"])
    def me(self, request):
        """Get current user's profile."""
        serializer = UserDetailSerializer(request.user)
        return Response(serializer.data)

    @action(detail=False, methods=["put", "patch"])
    def update_profile(self, request):
        """Update current user's profile."""
        serializer = UserUpdateSerializer(
            request.user,
            data=request.data,
            partial=request.method == "PATCH",
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(
        detail=False,
        methods=["get"],
        permission_classes=[IsAdminOrLabManager],
        url_path="search-patients",
    )
    def search_patients(self, request):
        """
        Search for patients (admin and lab staff only).

        This endpoint allows admins and lab staff to search for patients
        when assigning lab results or managing appointments.

        Query Parameters:
            - search: Search by email, first_name, last_name, phone_number
            - email: Filter by exact email
            - lab_client_id: Filter by lab (lab staff see only their lab)
            - ordering: Sort results (e.g., -created_at, email)

        Example: /api/v1/users/search-patients/?search=john&ordering=last_name
        """
        user = request.user

        # Start with active patients only
        queryset = User.objects.filter(role="patient", is_active=True)

        # Lab staff can only see patients in their lab
        if user.role == "lab_staff" and user.lab_client_id:
            queryset = queryset.filter(lab_client_id=user.lab_client_id)

        # Apply search filter if provided
        search_query = request.query_params.get("search", None)
        if search_query:
            queryset = queryset.annotate(
                full_name=Concat("first_name", Value(" "), "last_name")
            ).filter(
                Q(email__icontains=search_query)
                | Q(first_name__icontains=search_query)
                | Q(last_name__icontains=search_query)
                | Q(full_name__icontains=search_query)
                | Q(phone_number__icontains=search_query)
            )

        # Apply email filter if provided
        email = request.query_params.get("email", None)
        if email:
            queryset = queryset.filter(email__iexact=email)

        # Apply lab_client_id filter if provided (admins only)
        if user.is_superuser or user.role == "admin":
            lab_client_id = request.query_params.get("lab_client_id", None)
            if lab_client_id:
                queryset = queryset.filter(lab_client_id=lab_client_id)

        # Apply ordering
        ordering = request.query_params.get("ordering", "-date_joined")
        queryset = queryset.order_by(ordering)

        # Paginate results
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = UserSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = UserSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(
        detail=False,
        methods=["post"],
        permission_classes=[IsAdmin],
        url_path="create-user",
    )
    def create_user(self, request):
        """
        Create a new user (admin only).

        Allows admins to create users with roles: admin, doctor, or patient.
        Created users receive an email with a link to set their password.

        Request Body:
            - email: string (required)
            - role: string (required) - One of: admin, doctor, patient
            - first_name: string (optional)
            - last_name: string (optional)
            - phone_number: string (optional)
            - dni: string (optional)
            - birthday: date (optional)
            - lab_client_id: int (optional)

        Example: POST /api/v1/users/create-user/
        {
            "email": "doctor@example.com",
            "role": "doctor",
            "first_name": "John",
            "last_name": "Smith",
            "phone_number": "+1234567890"
        }
        """
        serializer = AdminUserCreateSerializer(
            data=request.data, context={"created_by": request.user}
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Send password setup email asynchronously
        from apps.notifications.tasks import send_password_setup_email

        send_password_setup_email.delay(user.pk)

        return Response(
            {
                "message": f"User created successfully. An email has been sent to {user.email} to set their password.",
                "user": UserDetailSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=False,
        methods=["get"],
        permission_classes=[IsAdminOrLabManager],
        url_path="search-doctors",
    )
    def search_doctors(self, request):
        """
        Search for doctors (admin and lab staff only).

        This endpoint allows admins and lab staff to search for doctors
        when assigning studies or managing appointments.

        Query Parameters:
            - search: Search by email, first_name, last_name, phone_number
            - email: Filter by exact email
            - lab_client_id: Filter by lab (lab staff see only their lab)
            - ordering: Sort results (e.g., -created_at, email)

        Example: /api/v1/users/search-doctors/?search=john&ordering=last_name
        """
        user = request.user

        # Start with active doctors only
        queryset = User.objects.filter(role="doctor", is_active=True)

        # Lab staff can only see doctors in their lab
        if user.role == "lab_staff" and user.lab_client_id:
            queryset = queryset.filter(lab_client_id=user.lab_client_id)

        # Apply search filter if provided
        search_query = request.query_params.get("search", None)
        if search_query:
            queryset = queryset.annotate(
                full_name=Concat("first_name", Value(" "), "last_name")
            ).filter(
                Q(email__icontains=search_query)
                | Q(first_name__icontains=search_query)
                | Q(last_name__icontains=search_query)
                | Q(full_name__icontains=search_query)
                | Q(phone_number__icontains=search_query)
            )

        # Apply email filter if provided
        email = request.query_params.get("email", None)
        if email:
            queryset = queryset.filter(email__iexact=email)

        # Apply lab_client_id filter if provided (admins only)
        if user.is_superuser or user.role == "admin":
            lab_client_id = request.query_params.get("lab_client_id", None)
            if lab_client_id:
                queryset = queryset.filter(lab_client_id=lab_client_id)

        # Apply ordering
        ordering = request.query_params.get("ordering", "-date_joined")
        queryset = queryset.order_by(ordering)

        # Paginate results
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = UserSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = UserSerializer(queryset, many=True)
        return Response(serializer.data)


class PatientRegistrationView(generics.CreateAPIView):
    """
    Public endpoint for patient self-registration.

    Allows new patients to register without authentication.
    """

    permission_classes = [AllowAny]
    serializer_class = PatientRegistrationSerializer

    def create(self, request, *args, **kwargs):
        """Create a new patient account and send verification email."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Send verification email asynchronously
        from apps.notifications.tasks import send_verification_email

        send_verification_email.delay(user.pk)

        return Response(
            {
                "message": "Registration successful. Please check your email to verify your account.",
                "user": UserDetailSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


class VerifyEmailView(generics.GenericAPIView):
    """
    Public endpoint for email verification.

    Verifies a user's email address using the token sent via email.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        """Verify email address with token."""
        email = request.data.get("email")
        token = request.data.get("token")

        if not email or not token:
            return Response(
                {"error": "Email and token are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email=email)

            # Check if already verified
            if user.is_verified:
                return Response(
                    {"message": "Email is already verified."},
                    status=status.HTTP_200_OK,
                )

            # Verify token matches and is not expired
            if user.verification_token != token:
                return Response(
                    {"error": "Invalid verification token."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not user.is_verification_token_valid():
                return Response(
                    {
                        "error": "Verification token has expired. Please request a new one."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Verify the email
            user.verify_email()

            return Response(
                {
                    "message": "Email verified successfully! You can now log in.",
                    "user": UserDetailSerializer(user).data,
                },
                status=status.HTTP_200_OK,
            )

        except User.DoesNotExist:
            return Response(
                {"error": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )


class ResendVerificationEmailView(generics.GenericAPIView):
    """
    Public endpoint to resend verification email.

    Allows users to request a new verification email if the previous one expired.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        """Resend verification email."""
        email = request.data.get("email")

        if not email:
            return Response(
                {"error": "Email is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email=email)

            # Check if already verified
            if user.is_verified:
                return Response(
                    {"message": "Email is already verified."},
                    status=status.HTTP_200_OK,
                )

            # Send new verification email
            from apps.notifications.tasks import send_verification_email

            send_verification_email.delay(user.pk)

            return Response(
                {
                    "message": "Verification email has been resent. Please check your inbox."
                },
                status=status.HTTP_200_OK,
            )

        except User.DoesNotExist:
            # Don't reveal if email exists or not (security)
            return Response(
                {
                    "message": "If an account with this email exists, a verification email has been sent."
                },
                status=status.HTTP_200_OK,
            )


class SetPasswordView(generics.GenericAPIView):
    """
    Public endpoint for setting password for admin-created users.

    Allows users created by admin to set their password using the token sent via email.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        """Set password with token for admin-created users."""
        email = request.data.get("email")
        token = request.data.get("token")
        password = request.data.get("password")

        if not email or not token or not password:
            return Response(
                {"error": "Email, token, and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email=email)

            # Verify token matches and is not expired
            if user.verification_token != token:
                return Response(
                    {"error": "Invalid verification token."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not user.is_verification_token_valid():
                return Response(
                    {
                        "error": "Verification token has expired. Please contact support."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Set the password
            user.set_password(password)
            user.is_verified = True
            user.verification_token = None
            user.verification_token_created_at = None
            user.save(
                update_fields=[
                    "password",
                    "is_verified",
                    "verification_token",
                    "verification_token_created_at",
                ]
            )

            # Create EmailAddress for django-allauth authentication
            from allauth.account.models import EmailAddress

            EmailAddress.objects.update_or_create(
                user=user,
                email=user.email.lower(),
                defaults={
                    "verified": True,
                    "primary": True,
                },
            )

            return Response(
                {
                    "message": "Password set successfully! You can now log in.",
                    "user": UserDetailSerializer(user).data,
                },
                status=status.HTTP_200_OK,
            )

        except User.DoesNotExist:
            return Response(
                {"error": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )


class ImportDoctorsView(APIView):
    """
    Import doctors from CSV file asynchronously (admin and lab staff only).

    Expects CSV file with columns: NOMBRE_MEDICO, MATRICULA_O_ID
    Name formats supported:
    - "Last, First" (e.g., "Abadie, Joaquin")
    - "First Last" (e.g., "Juan Perez")
    - Single name (e.g., "ABACO SA") - treated as first_name only

    Returns task_id to track import progress.
    """

    permission_classes = [IsAdminOrLabManager]

    def post(self, request):
        """Queue import task and return task ID."""
        # Validate file upload
        if "file" not in request.FILES:
            return Response(
                {"error": "No file uploaded. Please provide a CSV file."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        csv_file = request.FILES["file"]

        # Validate file extension
        if not csv_file.name.endswith(".csv"):
            return Response(
                {"error": "Invalid file type. Please upload a CSV file."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Read and decode CSV content
            csv_content = csv_file.read().decode("utf-8")

            # Determine lab_client_id for task
            lab_client_id = None
            if request.user.role == "lab_staff" and request.user.lab_client_id:
                lab_client_id = request.user.lab_client_id

            # Queue the task
            from apps.users.tasks import import_doctors_task

            task = import_doctors_task.delay(csv_content, lab_client_id)

            return Response(
                {
                    "message": "Import task queued successfully. Use the task_id to check progress.",
                    "task_id": task.id,
                },
                status=status.HTTP_202_ACCEPTED,
            )

        except Exception as e:
            return Response(
                {"error": f"Failed to queue import task: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ImportDoctorsStatusView(APIView):
    """
    Check the status of a doctor import task.

    Returns task state and progress information.
    """

    permission_classes = [IsAdminOrLabManager]

    def get(self, request, task_id):
        """Get status of import task."""
        from celery.result import AsyncResult

        task = AsyncResult(task_id)

        if task.state == "PENDING":
            response = {
                "state": task.state,
                "status": "Task is waiting to be processed...",
            }
        elif task.state == "PROCESSING":
            response = {
                "state": task.state,
                "status": task.info.get("status", "Processing..."),
                "processed": task.info.get("processed", 0),
                "created": task.info.get("created", 0),
                "skipped": task.info.get("skipped", 0),
                "errors": task.info.get("errors", 0),
            }
        elif task.state == "SUCCESS":
            response = {
                "state": task.state,
                "status": "Import completed successfully",
                "result": task.info,
            }
        elif task.state == "FAILURE":
            response = {
                "state": task.state,
                "status": "Import failed",
                "error": str(task.info),
            }
        else:
            response = {
                "state": task.state,
                "status": str(task.info),
            }

        return Response(response)
