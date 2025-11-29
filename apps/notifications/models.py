"""Models for notifications app."""
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Notification(models.Model):
    """
    System notification for users.

    Tracks in-app notifications, emails, and SMS messages.
    """

    TYPE_CHOICES = [
        ("info", _("Information")),
        ("warning", _("Warning")),
        ("error", _("Error")),
        ("success", _("Success")),
        ("appointment_reminder", _("Appointment Reminder")),
        ("result_ready", _("Result Ready")),
        ("payment_due", _("Payment Due")),
    ]

    CHANNEL_CHOICES = [
        ("in_app", _("In-App")),
        ("email", _("Email")),
        ("sms", _("SMS")),
        ("push", _("Push Notification")),
    ]

    STATUS_CHOICES = [
        ("pending", _("Pending")),
        ("sent", _("Sent")),
        ("delivered", _("Delivered")),
        ("failed", _("Failed")),
        ("read", _("Read")),
    ]

    # Relationships
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )

    # Notification details
    title = models.CharField(_("title"), max_length=200)
    message = models.TextField(_("message"))
    notification_type = models.CharField(
        _("type"),
        max_length=30,
        choices=TYPE_CHOICES,
        default="info",
    )
    channel = models.CharField(
        _("channel"),
        max_length=20,
        choices=CHANNEL_CHOICES,
        default="in_app",
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    # Related objects
    related_study_id = models.IntegerField(
        _("related study ID"),
        null=True,
        blank=True,
    )
    related_appointment_id = models.IntegerField(
        _("related appointment ID"),
        null=True,
        blank=True,
    )
    related_invoice_id = models.IntegerField(
        _("related invoice ID"),
        null=True,
        blank=True,
    )

    # Metadata
    metadata = models.JSONField(
        _("metadata"),
        blank=True,
        null=True,
        help_text=_("Additional data for the notification"),
    )

    # Delivery information
    sent_at = models.DateTimeField(_("sent at"), null=True, blank=True)
    delivered_at = models.DateTimeField(_("delivered at"), null=True, blank=True)
    read_at = models.DateTimeField(_("read at"), null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["user", "read_at"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.title} - {self.user.email}"

    @property
    def is_read(self):
        """Check if notification has been read."""
        return self.read_at is not None

    @property
    def is_unread(self):
        """Check if notification is unread."""
        return self.read_at is None
