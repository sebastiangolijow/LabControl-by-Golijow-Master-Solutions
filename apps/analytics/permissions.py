"""Custom permissions for analytics app."""
from rest_framework import permissions


class CanViewAnalytics(permissions.BasePermission):
    """
    Permission to view analytics data.

    Only admin and lab_manager users can view analytics.
    Lab managers can only view their own lab's statistics.
    """

    def has_permission(self, request, view):
        """Check if user has permission to view analytics."""
        # User must be authenticated
        if not request.user or not request.user.is_authenticated:
            return False

        # Only admin and lab_manager can view analytics
        return request.user.role in ["admin", "lab_manager"]


class IsAdminOrLabManager(permissions.BasePermission):
    """
    Permission class for admin or lab manager access.

    This is an alias for CanViewAnalytics for consistency.
    """

    def has_permission(self, request, view):
        """Check if user is admin or lab manager."""
        if not request.user or not request.user.is_authenticated:
            return False

        return request.user.role in ["admin", "lab_manager"]
