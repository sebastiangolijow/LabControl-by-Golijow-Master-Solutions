"""Tests for users app."""
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status

User = get_user_model()


@pytest.mark.django_db
class TestUserModel:
    """Test cases for User model."""

    def test_create_user(self):
        """Test creating a regular user."""
        user = User.objects.create_user(
            email="newuser@example.com",
            password="testpass123",
            first_name="New",
            last_name="User",
        )
        assert user.email == "newuser@example.com"
        assert user.check_password("testpass123")
        assert user.is_active is True
        assert user.is_staff is False
        assert user.is_superuser is False

    def test_create_superuser(self):
        """Test creating a superuser."""
        user = User.objects.create_superuser(
            email="super@example.com",
            password="superpass123",
        )
        assert user.email == "super@example.com"
        assert user.is_active is True
        assert user.is_staff is True
        assert user.is_superuser is True

    def test_user_str_representation(self):
        """Test user string representation."""
        user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
        )
        assert str(user) == "test@example.com"

    def test_get_full_name(self):
        """Test getting user's full name."""
        user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
            first_name="John",
            last_name="Doe",
        )
        assert user.get_full_name() == "John Doe"

    def test_user_role_properties(self):
        """Test user role property methods."""
        user = User.objects.create_user(
            email="doctor@example.com",
            password="testpass123",
            role="doctor",
        )
        assert user.is_doctor is True
        assert user.is_patient is False
        assert user.is_lab_manager is False


@pytest.mark.django_db
class TestUserAPI:
    """Test cases for User API endpoints."""

    def test_get_current_user_profile(self, authenticated_client, user):
        """Test getting current user's profile."""
        response = authenticated_client.get("/api/v1/users/me/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["email"] == user.email

    def test_update_user_profile(self, authenticated_client, user):
        """Test updating user profile."""
        data = {
            "first_name": "Updated",
            "last_name": "Name",
        }
        response = authenticated_client.put("/api/v1/users/update_profile/", data)
        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.first_name == "Updated"
        assert user.last_name == "Name"

    def test_list_users_as_admin(self, admin_client):
        """Test listing users as admin."""
        response = admin_client.get("/api/v1/users/")
        assert response.status_code == status.HTTP_200_OK

    def test_list_users_as_patient_restricted(self, authenticated_client, user):
        """Test that patients can only see themselves."""
        response = authenticated_client.get("/api/v1/users/")
        assert response.status_code == status.HTTP_200_OK
        # Should only see their own user
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["email"] == user.email
