"""Tests for notifications app."""
import pytest
from apps.notifications.models import Notification
from rest_framework import status


@pytest.fixture
def notification(db, user):
    """Fixture for creating a notification."""
    return Notification.objects.create(
        user=user,
        title="Test Notification",
        message="This is a test notification",
        notification_type="info",
        channel="in_app",
        status="sent",
    )


@pytest.mark.django_db
class TestNotificationModel:
    """Test cases for Notification model."""

    def test_create_notification(self, notification):
        """Test creating a notification."""
        assert notification.title == "Test Notification"
        assert notification.notification_type == "info"
        assert notification.is_unread is True

    def test_notification_read_status(self, notification):
        """Test notification read status."""
        assert notification.is_read is False
        from django.utils import timezone

        notification.read_at = timezone.now()
        assert notification.is_read is True
        assert notification.is_unread is False


@pytest.mark.django_db
class TestNotificationAPI:
    """Test cases for Notification API endpoints."""

    def test_list_user_notifications(self, authenticated_client, notification):
        """Test user can see their own notifications."""
        response = authenticated_client.get("/api/v1/notifications/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_mark_notification_as_read(self, authenticated_client, notification):
        """Test marking a notification as read."""
        response = authenticated_client.post(
            f"/api/v1/notifications/{notification.id}/mark_as_read/"
        )
        assert response.status_code == status.HTTP_200_OK
        notification.refresh_from_db()
        assert notification.is_read is True

    def test_unread_count(self, authenticated_client, notification):
        """Test getting unread notification count."""
        response = authenticated_client.get("/api/v1/notifications/unread_count/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["unread_count"] == 1
