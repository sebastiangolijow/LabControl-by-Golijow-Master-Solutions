"""Custom managers for Notification model."""
from django.db import models


class NotificationQuerySet(models.QuerySet):
    """
    Custom queryset for Notification model with chainable domain-specific methods.
    """

    def unread(self):
        """Return unread notifications."""
        return self.filter(read_at__isnull=True)

    def read(self):
        """Return read notifications."""
        return self.filter(read_at__isnull=False)

    def pending(self):
        """Return pending notifications."""
        return self.filter(status="pending")

    def sent(self):
        """Return sent notifications."""
        return self.filter(status="sent")

    def delivered(self):
        """Return delivered notifications."""
        return self.filter(status="delivered")

    def failed(self):
        """Return failed notifications."""
        return self.filter(status="failed")

    def for_user(self, user):
        """Return notifications for a specific user."""
        return self.filter(user=user)

    def by_type(self, notification_type):
        """Return notifications by type."""
        return self.filter(notification_type=notification_type)

    def by_channel(self, channel):
        """Return notifications by channel."""
        return self.filter(channel=channel)

    def in_app(self):
        """Return in-app notifications."""
        return self.filter(channel="in_app")

    def email(self):
        """Return email notifications."""
        return self.filter(channel="email")

    def sms(self):
        """Return SMS notifications."""
        return self.filter(channel="sms")

    def push(self):
        """Return push notifications."""
        return self.filter(channel="push")

    def appointment_reminders(self):
        """Return appointment reminder notifications."""
        return self.filter(notification_type="appointment_reminder")

    def result_ready(self):
        """Return result ready notifications."""
        return self.filter(notification_type="result_ready")

    def payment_due(self):
        """Return payment due notifications."""
        return self.filter(notification_type="payment_due")

    def info(self):
        """Return info notifications."""
        return self.filter(notification_type="info")

    def warnings(self):
        """Return warning notifications."""
        return self.filter(notification_type="warning")

    def errors(self):
        """Return error notifications."""
        return self.filter(notification_type="error")

    def success(self):
        """Return success notifications."""
        return self.filter(notification_type="success")


class NotificationManager(models.Manager):
    """
    Custom manager for Notification model.

    Provides convenient methods for common notification queries.
    """

    def get_queryset(self):
        """Return custom queryset."""
        return NotificationQuerySet(self.model, using=self._db)

    def unread(self):
        """Get all unread notifications."""
        return self.get_queryset().unread()

    def read(self):
        """Get all read notifications."""
        return self.get_queryset().read()

    def pending(self):
        """Get all pending notifications."""
        return self.get_queryset().pending()

    def sent(self):
        """Get all sent notifications."""
        return self.get_queryset().sent()

    def delivered(self):
        """Get all delivered notifications."""
        return self.get_queryset().delivered()

    def failed(self):
        """Get all failed notifications."""
        return self.get_queryset().failed()

    def for_user(self, user):
        """Get notifications for a specific user."""
        return self.get_queryset().for_user(user)

    def by_type(self, notification_type):
        """Get notifications by type."""
        return self.get_queryset().by_type(notification_type)

    def by_channel(self, channel):
        """Get notifications by channel."""
        return self.get_queryset().by_channel(channel)

    def in_app(self):
        """Get in-app notifications."""
        return self.get_queryset().in_app()

    def email(self):
        """Get email notifications."""
        return self.get_queryset().email()

    def sms(self):
        """Get SMS notifications."""
        return self.get_queryset().sms()

    def push(self):
        """Get push notifications."""
        return self.get_queryset().push()

    def appointment_reminders(self):
        """Get appointment reminder notifications."""
        return self.get_queryset().appointment_reminders()

    def result_ready(self):
        """Get result ready notifications."""
        return self.get_queryset().result_ready()

    def payment_due(self):
        """Get payment due notifications."""
        return self.get_queryset().payment_due()

    def info(self):
        """Get info notifications."""
        return self.get_queryset().info()

    def warnings(self):
        """Get warning notifications."""
        return self.get_queryset().warnings()

    def errors(self):
        """Get error notifications."""
        return self.get_queryset().errors()

    def success(self):
        """Get success notifications."""
        return self.get_queryset().success()
