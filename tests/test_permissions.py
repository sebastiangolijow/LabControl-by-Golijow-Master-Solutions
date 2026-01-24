"""Tests for Phase 1: Backend Permission Verification.

Tests for:
1. Django admin access (superuser-only restriction)
2. User DELETE endpoint permissions
3. Permission class behavior
"""

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from rest_framework import status

from apps.users.permissions import IsAdmin, IsAdminOrLabManager
from config.admin import SuperUserAdminSite, admin_site
from tests.base import BaseTestCase

User = get_user_model()


class TestDjangoAdminPermissions(BaseTestCase):
    """Test cases for Django admin panel access restrictions."""

    def setUp(self):
        """Set up test fixtures."""
        super().setUp()
        self.factory = RequestFactory()
        self.site = admin_site

    def test_admin_site_is_custom_superuser_site(self):
        """Test that the admin site is our custom SuperUserAdminSite."""
        assert isinstance(self.site, SuperUserAdminSite)
        assert not isinstance(self.site, AdminSite) or isinstance(
            self.site, SuperUserAdminSite
        )

    def test_superuser_can_access_admin(self):
        """Test that superusers can access Django admin."""
        superuser = self.create_admin(is_superuser=True, is_staff=True)
        request = self.factory.get("/admin/")
        request.user = superuser

        assert self.site.has_permission(request) is True

    def test_admin_role_without_superuser_cannot_access(self):
        """Test that admin role without superuser flag cannot access Django admin."""
        admin_user = self.create_user(
            email="admin@test.com",
            role="admin",
            is_staff=True,
            is_superuser=False,  # Not a superuser
        )
        request = self.factory.get("/admin/")
        request.user = admin_user

        assert self.site.has_permission(request) is False

    def test_lab_manager_cannot_access_admin(self):
        """Test that lab managers cannot access Django admin."""
        lab_manager = self.create_lab_manager(is_staff=True, is_superuser=False)
        request = self.factory.get("/admin/")
        request.user = lab_manager

        assert self.site.has_permission(request) is False

    def test_staff_user_without_superuser_cannot_access(self):
        """Test that is_staff=True users without superuser cannot access."""
        staff_user = self.create_user(
            email="staff@test.com",
            role="lab_staff",
            is_staff=True,
            is_superuser=False,
        )
        request = self.factory.get("/admin/")
        request.user = staff_user

        assert self.site.has_permission(request) is False

    def test_patient_cannot_access_admin(self):
        """Test that patients cannot access Django admin."""
        patient = self.create_patient()
        request = self.factory.get("/admin/")
        request.user = patient

        assert self.site.has_permission(request) is False

    def test_inactive_superuser_cannot_access_admin(self):
        """Test that inactive superusers cannot access Django admin."""
        inactive_superuser = self.create_admin(
            is_superuser=True, is_staff=True, is_active=False
        )
        request = self.factory.get("/admin/")
        request.user = inactive_superuser

        assert self.site.has_permission(request) is False


class TestPermissionClasses(BaseTestCase):
    """Test cases for custom permission classes."""

    def setUp(self):
        """Set up test fixtures."""
        super().setUp()
        self.factory = RequestFactory()

    def test_is_admin_permission_allows_superuser(self):
        """Test IsAdmin permission allows superusers."""
        superuser = self.create_admin(is_superuser=True)
        request = self.factory.get("/api/v1/users/")
        request.user = superuser

        permission = IsAdmin()
        assert permission.has_permission(request, None) is True

    def test_is_admin_permission_allows_admin_role(self):
        """Test IsAdmin permission allows users with role='admin'."""
        admin_user = self.create_user(role="admin", is_superuser=False)
        request = self.factory.get("/api/v1/users/")
        request.user = admin_user

        permission = IsAdmin()
        assert permission.has_permission(request, None) is True

    def test_is_admin_permission_denies_lab_manager(self):
        """Test IsAdmin permission denies lab managers."""
        lab_manager = self.create_lab_manager()
        request = self.factory.get("/api/v1/users/")
        request.user = lab_manager

        permission = IsAdmin()
        assert permission.has_permission(request, None) is False

    def test_is_admin_permission_denies_patient(self):
        """Test IsAdmin permission denies patients."""
        patient = self.create_patient()
        request = self.factory.get("/api/v1/users/")
        request.user = patient

        permission = IsAdmin()
        assert permission.has_permission(request, None) is False

    def test_is_admin_or_lab_manager_allows_superuser(self):
        """Test IsAdminOrLabManager permission allows superusers."""
        superuser = self.create_admin(is_superuser=True)
        request = self.factory.get("/api/v1/users/")
        request.user = superuser

        permission = IsAdminOrLabManager()
        assert permission.has_permission(request, None) is True

    def test_is_admin_or_lab_manager_allows_admin(self):
        """Test IsAdminOrLabManager permission allows admins."""
        admin = self.create_user(role="admin", is_superuser=False)
        request = self.factory.get("/api/v1/users/")
        request.user = admin

        permission = IsAdminOrLabManager()
        assert permission.has_permission(request, None) is True

    def test_is_admin_or_lab_manager_allows_lab_manager(self):
        """Test IsAdminOrLabManager permission allows lab managers."""
        lab_manager = self.create_lab_manager()
        request = self.factory.get("/api/v1/users/")
        request.user = lab_manager

        permission = IsAdminOrLabManager()
        assert permission.has_permission(request, None) is True

    def test_is_admin_or_lab_manager_denies_patient(self):
        """Test IsAdminOrLabManager permission denies patients."""
        patient = self.create_patient()
        request = self.factory.get("/api/v1/users/")
        request.user = patient

        permission = IsAdminOrLabManager()
        assert permission.has_permission(request, None) is False


class TestUserDeleteEndpoint(BaseTestCase):
    """Test cases for user DELETE endpoint (soft delete)."""

    def test_admin_can_delete_user(self):
        """Test that admins can delete users."""
        client, admin = self.authenticate_as_admin()
        patient = self.create_patient()

        response = client.delete(f"/api/v1/users/{patient.id}/")

        assert response.status_code == status.HTTP_200_OK
        assert "deactivated successfully" in response.data["message"]
        assert response.data["email"] == patient.email

        # Verify soft delete (is_active=False)
        patient.refresh_from_db()
        assert patient.is_active is False

    def test_patient_cannot_delete_users(self):
        """Test that patients cannot delete users."""
        client, patient1 = self.authenticate_as_patient()
        patient2 = self.create_patient(email="patient2@test.com")

        response = client.delete(f"/api/v1/users/{patient2.id}/")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_lab_manager_cannot_delete_users(self):
        """Test that lab managers cannot delete users."""
        client, lab_manager = self.authenticate_as_lab_manager()
        patient = self.create_patient()

        response = client.delete(f"/api/v1/users/{patient.id}/")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_user_cannot_delete_themselves(self):
        """Test that users cannot delete their own account."""
        client, admin = self.authenticate_as_admin()

        response = client.delete(f"/api/v1/users/{admin.id}/")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "cannot delete your own account" in response.data["error"]

        # Verify user is still active
        admin.refresh_from_db()
        assert admin.is_active is True

    def test_admin_cannot_delete_superuser(self):
        """Test that non-superuser admins cannot delete superusers."""
        # Create an admin without superuser flag
        admin_user = self.create_user(
            email="admin@test.com", role="admin", is_superuser=False
        )
        client = self.authenticate(admin_user)

        # Create a superuser
        superuser = self.create_admin(
            email="super@test.com", is_superuser=True, is_staff=True
        )

        response = client.delete(f"/api/v1/users/{superuser.id}/")

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "cannot delete a superuser account" in response.data["error"]

        # Verify superuser is still active
        superuser.refresh_from_db()
        assert superuser.is_active is True

    def test_superuser_can_delete_superuser(self):
        """Test that superusers can delete other superusers."""
        client, superuser1 = self.authenticate_as_admin(is_superuser=True)
        superuser2 = self.create_admin(
            email="super2@test.com", is_superuser=True, is_staff=True
        )

        response = client.delete(f"/api/v1/users/{superuser2.id}/")

        assert response.status_code == status.HTTP_200_OK
        assert "deactivated successfully" in response.data["message"]

        # Verify soft delete
        superuser2.refresh_from_db()
        assert superuser2.is_active is False

    def test_delete_is_soft_delete(self):
        """Test that delete operation is a soft delete (is_active=False)."""
        client, admin = self.authenticate_as_admin()
        patient = self.create_patient()
        patient_id = patient.id

        response = client.delete(f"/api/v1/users/{patient.id}/")

        assert response.status_code == status.HTTP_200_OK

        # User should still exist in database
        assert User.objects.filter(id=patient_id).exists()

        # But should be inactive
        patient.refresh_from_db()
        assert patient.is_active is False

    def test_unauthenticated_cannot_delete_users(self):
        """Test that unauthenticated users cannot delete users."""
        patient = self.create_patient()
        client = self.client  # Non-authenticated client

        response = client.delete(f"/api/v1/users/{patient.id}/")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_delete_nonexistent_user_returns_404(self):
        """Test that deleting a non-existent user returns 404."""
        client, admin = self.authenticate_as_admin()

        response = client.delete("/api/v1/users/99999/")

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestPermissionMatrix(BaseTestCase):
    """Test the complete permission matrix from PHASE1_PROGRESS.md."""

    def test_patient_permissions(self):
        """Test patient role permissions."""
        client, patient = self.authenticate_as_patient()

        # Can view own profile
        response = client.get("/api/v1/users/me/")
        assert response.status_code == status.HTTP_200_OK

        # Can edit self
        response = client.patch(
            "/api/v1/users/update_profile/", {"first_name": "Updated"}
        )
        assert response.status_code == status.HTTP_200_OK

        # Cannot view all users (only sees self)
        response = client.get("/api/v1/users/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

        # Cannot delete users
        other_patient = self.create_patient(email="other@test.com")
        response = client.delete(f"/api/v1/users/{other_patient.id}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_permissions(self):
        """Test admin role permissions."""
        client, admin = self.authenticate_as_admin()

        # Can view all users
        self.create_patient()
        self.create_patient(email="patient2@test.com")
        response = client.get("/api/v1/users/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) >= 3  # Admin + 2 patients

        # Can edit any user
        patient = self.create_patient(email="editable@test.com")
        response = client.patch(
            f"/api/v1/users/{patient.id}/", {"first_name": "AdminUpdated"}
        )
        assert response.status_code == status.HTTP_200_OK

        # Can delete users
        deletable_patient = self.create_patient(email="deletable@test.com")
        response = client.delete(f"/api/v1/users/{deletable_patient.id}/")
        assert response.status_code == status.HTTP_200_OK

    def test_lab_manager_permissions(self):
        """Test lab manager role permissions."""
        client, lab_manager = self.authenticate_as_lab_manager(lab_client_id=1)

        # Can view users in their lab only
        same_lab_user = self.create_patient(lab_client_id=1)
        other_lab_user = self.create_patient(email="other@test.com", lab_client_id=2)

        response = client.get("/api/v1/users/")
        assert response.status_code == status.HTTP_200_OK

        # Should see users from their lab
        user_ids = [user["id"] for user in response.data["results"]]
        assert same_lab_user.id in user_ids
        assert other_lab_user.id not in user_ids

        # Cannot delete users
        response = client.delete(f"/api/v1/users/{same_lab_user.id}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN
