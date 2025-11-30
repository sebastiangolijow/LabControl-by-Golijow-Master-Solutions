"""Tests for notifications app following TDD principles."""
from django.utils import timezone
from tests.base import BaseTestCase
from apps.notifications.models import Notification
from rest_framework import status


class TestNotificationModel(BaseTestCase):
    """Test cases for Notification model."""

    def test_create_notification(self):
        """Test creating a notification."""
        user = self.create_patient()
        notification = self.create_notification(user=user)

        assert notification.user == user
        assert notification.status == "sent"
        assert notification.title == "Test Notification"

    def test_notification_has_uuid(self):
        """Test that notification has UUID field."""
        notification = self.create_notification()
        self.assertUUID(notification.uuid)

    def test_notification_has_timestamps(self):
        """Test that notification has timestamp fields."""
        notification = self.create_notification()
        self.assertIsNotNone(notification.created_at)
        self.assertIsNotNone(notification.updated_at)
        self.assertTimestampRecent(notification.created_at)

    def test_notification_has_audit_trail(self):
        """Test that notification has history tracking."""
        notification = self.create_notification()
        assert hasattr(notification, "history")
        assert notification.history.count() == 1  # Created

        # Update notification
        notification.status = "read"
        notification.save()
        assert notification.history.count() == 2  # Created + Updated

    def test_notification_created_by(self):
        """Test created_by field."""
        admin = self.create_admin()
        notification = self.create_notification(created_by=admin)

        assert notification.created_by == admin

    def test_notification_str_representation(self):
        """Test notification string representation."""
        user = self.create_patient(email="patient@test.com")
        notification = self.create_notification(
            user=user,
            title="Important Notice",
        )
        assert str(notification) == "Important Notice - patient@test.com"

    def test_notification_is_read_property(self):
        """Test is_read property."""
        notification = self.create_notification()
        assert notification.is_read is False

        notification.read_at = timezone.now()
        notification.save()
        assert notification.is_read is True

    def test_notification_is_unread_property(self):
        """Test is_unread property."""
        notification = self.create_notification()
        assert notification.is_unread is True

        notification.read_at = timezone.now()
        notification.save()
        assert notification.is_unread is False


class TestNotificationManager(BaseTestCase):
    """Test cases for Notification custom manager."""

    def test_unread_notifications(self):
        """Test NotificationManager.unread() method."""
        unread = self.create_notification(read_at=None)
        read = self.create_notification(read_at=timezone.now())

        unread_notifications = Notification.objects.unread()
        assert unread in unread_notifications
        assert read not in unread_notifications

    def test_read_notifications(self):
        """Test NotificationManager.read() method."""
        unread = self.create_notification(read_at=None)
        read = self.create_notification(read_at=timezone.now())

        read_notifications = Notification.objects.read()
        assert read in read_notifications
        assert unread not in read_notifications

    def test_pending_notifications(self):
        """Test NotificationManager.pending() method."""
        pending = self.create_notification(status="pending")
        sent = self.create_notification(status="sent")

        pending_notifications = Notification.objects.pending()
        assert pending in pending_notifications
        assert sent not in pending_notifications

    def test_sent_notifications(self):
        """Test NotificationManager.sent() method."""
        pending = self.create_notification(status="pending")
        sent = self.create_notification(status="sent")

        sent_notifications = Notification.objects.sent()
        assert sent in sent_notifications
        assert pending not in sent_notifications

    def test_delivered_notifications(self):
        """Test NotificationManager.delivered() method."""
        sent = self.create_notification(status="sent")
        delivered = self.create_notification(status="delivered")

        delivered_notifications = Notification.objects.delivered()
        assert delivered in delivered_notifications
        assert sent not in delivered_notifications

    def test_failed_notifications(self):
        """Test NotificationManager.failed() method."""
        sent = self.create_notification(status="sent")
        failed = self.create_notification(status="failed")

        failed_notifications = Notification.objects.failed()
        assert failed in failed_notifications
        assert sent not in failed_notifications

    def test_for_user(self):
        """Test NotificationManager.for_user() method."""
        user1 = self.create_patient()
        user2 = self.create_patient(email="patient2@test.com")

        notif1 = self.create_notification(user=user1)
        notif2 = self.create_notification(user=user2)

        user1_notifications = Notification.objects.for_user(user1)
        assert notif1 in user1_notifications
        assert notif2 not in user1_notifications

    def test_by_type(self):
        """Test NotificationManager.by_type() method."""
        info = self.create_notification(notification_type="info")
        warning = self.create_notification(notification_type="warning")

        info_notifications = Notification.objects.by_type("info")
        assert info in info_notifications
        assert warning not in info_notifications

    def test_by_channel(self):
        """Test NotificationManager.by_channel() method."""
        in_app = self.create_notification(channel="in_app")
        email = self.create_notification(channel="email")

        in_app_notifications = Notification.objects.by_channel("in_app")
        assert in_app in in_app_notifications
        assert email not in in_app_notifications

    def test_in_app_notifications(self):
        """Test NotificationManager.in_app() method."""
        in_app = self.create_notification(channel="in_app")
        email = self.create_notification(channel="email")

        in_app_notifications = Notification.objects.in_app()
        assert in_app in in_app_notifications
        assert email not in in_app_notifications

    def test_email_notifications(self):
        """Test NotificationManager.email() method."""
        in_app = self.create_notification(channel="in_app")
        email = self.create_notification(channel="email")

        email_notifications = Notification.objects.email()
        assert email in email_notifications
        assert in_app not in email_notifications

    def test_sms_notifications(self):
        """Test NotificationManager.sms() method."""
        in_app = self.create_notification(channel="in_app")
        sms = self.create_notification(channel="sms")

        sms_notifications = Notification.objects.sms()
        assert sms in sms_notifications
        assert in_app not in sms_notifications

    def test_appointment_reminders(self):
        """Test NotificationManager.appointment_reminders() method."""
        info = self.create_notification(notification_type="info")
        reminder = self.create_notification(notification_type="appointment_reminder")

        reminder_notifications = Notification.objects.appointment_reminders()
        assert reminder in reminder_notifications
        assert info not in reminder_notifications

    def test_info_notifications(self):
        """Test NotificationManager.info() method."""
        info = self.create_notification(notification_type="info")
        warning = self.create_notification(notification_type="warning")

        info_notifications = Notification.objects.info()
        assert info in info_notifications
        assert warning not in info_notifications

    def test_warnings_notifications(self):
        """Test NotificationManager.warnings() method."""
        info = self.create_notification(notification_type="info")
        warning = self.create_notification(notification_type="warning")

        warning_notifications = Notification.objects.warnings()
        assert warning in warning_notifications
        assert info not in warning_notifications

    def test_chainable_queries(self):
        """Test that manager methods are chainable."""
        user1 = self.create_patient()
        user2 = self.create_patient(email="patient2@test.com")

        user1_unread_in_app = self.create_notification(
            user=user1,
            channel="in_app",
            read_at=None,
        )
        user2_unread_in_app = self.create_notification(
            user=user2,
            channel="in_app",
            read_at=None,
        )
        user1_read_in_app = self.create_notification(
            user=user1,
            channel="in_app",
            read_at=timezone.now(),
        )
        user1_unread_email = self.create_notification(
            user=user1,
            channel="email",
            read_at=None,
        )

        # Chain: unread in-app notifications for user1
        result = Notification.objects.for_user(user1).unread().in_app()

        assert user1_unread_in_app in result
        assert user2_unread_in_app not in result
        assert user1_read_in_app not in result
        assert user1_unread_email not in result


class TestNotificationAPI(BaseTestCase):
    """Test cases for Notification API endpoints."""

    def test_list_user_notifications(self):
        """Test user can see their own notifications."""
        client, user = self.authenticate_as_patient()
        notification = self.create_notification(user=user)

        response = client.get("/api/v1/notifications/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["title"] == notification.title

    def test_user_cannot_see_other_notifications(self):
        """Test user cannot see other users' notifications."""
        client, user1 = self.authenticate_as_patient()
        user2 = self.create_patient(email="other@test.com")

        own_notification = self.create_notification(user=user1)
        other_notification = self.create_notification(user=user2)

        response = client.get("/api/v1/notifications/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["id"] == own_notification.id

    def test_mark_notification_as_read(self):
        """Test marking a notification as read."""
        client, user = self.authenticate_as_patient()
        notification = self.create_notification(user=user, read_at=None)

        response = client.post(f"/api/v1/notifications/{notification.id}/mark_as_read/")
        assert response.status_code == status.HTTP_200_OK
        notification.refresh_from_db()
        assert notification.is_read is True

    def test_unread_count(self):
        """Test getting unread notification count."""
        client, user = self.authenticate_as_patient()

        # Create unread notifications
        self.create_notification(user=user, read_at=None)
        self.create_notification(user=user, read_at=None)

        # Create read notification
        self.create_notification(user=user, read_at=timezone.now())

        response = client.get("/api/v1/notifications/unread_count/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["unread_count"] == 2

    def test_notification_uuid_in_api_response(self):
        """Test that UUID is included in API responses."""
        client, user = self.authenticate_as_patient()
        notification = self.create_notification(user=user)

        response = client.get("/api/v1/notifications/")
        assert response.status_code == status.HTTP_200_OK
        assert "uuid" in response.data["results"][0]
        self.assertUUID(notification.uuid)
