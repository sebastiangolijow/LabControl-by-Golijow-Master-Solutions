"""
Custom Admin Site Configuration.

Restricts Django admin panel access to superusers only for enhanced security.
"""

from django.contrib import admin


class SuperUserAdminSite(admin.AdminSite):
    """
    Custom admin site that restricts access to superusers only.

    This ensures that only users with is_superuser=True can access the Django admin panel,
    regardless of their is_staff status or role.

    Security Rationale:
    - Regular admin users (role='admin') should use the API/frontend for management tasks
    - Django admin provides powerful database access and should be reserved for superusers
    - This prevents privilege escalation through the admin interface
    """

    site_header = "LabControl Administration (Superuser Only)"
    site_title = "LabControl Admin"
    index_title = "Welcome to LabControl Admin Panel"

    def has_permission(self, request):
        """
        Check if the requesting user has permission to access the admin site.

        Only superusers can access the admin site.

        Args:
            request: The HTTP request object

        Returns:
            bool: True if user is active and superuser, False otherwise
        """
        return request.user.is_active and request.user.is_superuser


# Replace the default admin site with our custom one
admin_site = SuperUserAdminSite(name="admin")

# Re-export for backwards compatibility
site = admin_site
