"""Views for users app."""

from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import User
from .serializers import (
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
