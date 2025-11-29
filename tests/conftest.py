"""Pytest configuration and fixtures."""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


@pytest.fixture
def api_client():
    """Fixture for DRF API client."""
    return APIClient()


@pytest.fixture
def user(db):
    """Fixture for creating a regular user."""
    return User.objects.create_user(
        email="test@example.com",
        password="testpass123",
        first_name="Test",
        last_name="User",
        role="patient",
    )


@pytest.fixture
def admin_user(db):
    """Fixture for creating an admin user."""
    return User.objects.create_user(
        email="admin@example.com",
        password="adminpass123",
        first_name="Admin",
        last_name="User",
        role="admin",
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
def lab_manager(db):
    """Fixture for creating a lab manager."""
    return User.objects.create_user(
        email="manager@example.com",
        password="managerpass123",
        first_name="Lab",
        last_name="Manager",
        role="lab_manager",
        lab_client_id=1,
    )


@pytest.fixture
def authenticated_client(api_client, user):
    """Fixture for authenticated API client."""
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def admin_client(api_client, admin_user):
    """Fixture for admin authenticated API client."""
    api_client.force_authenticate(user=admin_user)
    return api_client
