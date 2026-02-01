"""Custom permissions for users app."""

from rest_framework import permissions


class IsAdminOrLabManager(permissions.BasePermission):
    """
    Permission class that only allows admins and lab staff.

    Used for sensitive operations like patient search and management.
    Note: Class name kept as IsAdminOrLabManager for backward compatibility.
    """

    def has_permission(self, request, view):
        """Check if user is admin or lab staff."""
        return (
            request.user
            and request.user.is_authenticated
            and (
                request.user.is_superuser
                or request.user.role in ["admin", "lab_staff"]
            )
        )


class IsAdmin(permissions.BasePermission):
    """
    Permission class that only allows admins.

    Used for highly sensitive operations.
    """

    def has_permission(self, request, view):
        """Check if user is admin."""
        return (
            request.user
            and request.user.is_authenticated
            and (request.user.is_superuser or request.user.role == "admin")
        )
