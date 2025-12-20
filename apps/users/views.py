"""Views for users app."""

from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import User
from .permissions import IsAdminOrLabManager
from .serializers import (
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
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["role", "is_active", "lab_client_id"]
    search_fields = ["email", "first_name", "last_name", "phone_number"]
    ordering_fields = ["date_joined", "email", "first_name", "last_name"]
    ordering = ["-date_joined"]

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == "create":
            return UserCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return UserUpdateSerializer
        elif self.action == "retrieve":
            return UserDetailSerializer
        return UserSerializer

    def get_queryset(self):
        """
        Filter queryset based on user role and permissions.

        - Superusers and admins can see all users
        - Lab managers can see users in their lab
        - Others can only see themselves
        """
        user = self.request.user

        if user.is_superuser or user.role == "admin":
            return User.objects.all()
        elif user.role == "lab_manager" and user.lab_client_id:
            return User.objects.filter(lab_client_id=user.lab_client_id)
        else:
            return User.objects.filter(id=user.id)

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
        Search for patients (admin and lab manager only).

        This endpoint allows admins and lab managers to search for patients
        when assigning lab results or managing appointments.

        Query Parameters:
            - search: Search by email, first_name, last_name, phone_number
            - email: Filter by exact email
            - lab_client_id: Filter by lab (lab managers see only their lab)
            - ordering: Sort results (e.g., -created_at, email)

        Example: /api/v1/users/search-patients/?search=john&ordering=last_name
        """
        user = request.user

        # Start with patients only
        queryset = User.objects.filter(role="patient")

        # Lab managers can only see patients in their lab
        if user.role == "lab_manager" and user.lab_client_id:
            queryset = queryset.filter(lab_client_id=user.lab_client_id)

        # Apply search filter if provided
        search_query = request.query_params.get("search", None)
        if search_query:
            queryset = queryset.filter(
                Q(email__icontains=search_query)
                | Q(first_name__icontains=search_query)
                | Q(last_name__icontains=search_query)
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
        """Create a new patient account."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        return Response(
            {
                "message": "Registration successful. Please check your email to verify your account.",
                "user": UserDetailSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )
