"""Custom permissions for analytics app."""

from rest_framework import permissions


class CanViewAnalytics(permissions.BasePermission):
    """
    Permission to view analytics data.

    Only admin and lab_staff users can view analytics.
    Lab staff can only view their own lab's statistics.
    """

    def has_permission(self, request, view):
        """Check if user has permission to view analytics."""
        # User must be authenticated
        if not request.user or not request.user.is_authenticated:
            return False

        # Only admin and lab_staff can view analytics
        return request.user.role in ["admin", "lab_staff"]


class IsAdminOrLabManager(permissions.BasePermission):
    """
    Permission class for admin or lab staff access.

    This is an alias for CanViewAnalytics for consistency.
    Note: Class name kept as IsAdminOrLabManager for backward compatibility.
    """

    def has_permission(self, request, view):
        """Check if user is admin or lab staff."""
        if not request.user or not request.user.is_authenticated:
            return False

        return request.user.role in ["admin", "lab_staff"]
