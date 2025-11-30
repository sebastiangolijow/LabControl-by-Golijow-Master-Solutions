"""Celery tasks for notifications app."""

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail


@shared_task
def send_email_notification(user_id, subject, message):
    """
    Send email notification to a user.

    Args:
        user_id: ID of the user to send email to
        subject: Email subject
        message: Email message body
    """
    from apps.users.models import User

    try:
        user = User.objects.get(id=user_id)
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        return f"Email sent to {user.email}"
    except User.DoesNotExist:
        return f"User {user_id} not found"


@shared_task
def cleanup_old_notifications():
    """
    Clean up old read notifications (older than 90 days).

    This task runs weekly to keep the database clean.
    """
    from datetime import timedelta

    from django.utils import timezone

    from .models import Notification

    cutoff_date = timezone.now() - timedelta(days=90)
    deleted_count, _ = Notification.objects.filter(
        status="read", read_at__lt=cutoff_date
    ).delete()

    return f"Deleted {deleted_count} old notifications"


@shared_task
def send_bulk_notification(user_ids, title, message, notification_type="info"):
    """
    Send notification to multiple users.

    Args:
        user_ids: List of user IDs
        title: Notification title
        message: Notification message
        notification_type: Type of notification
    """
    from .models import Notification

    notifications = [
        Notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type=notification_type,
            channel="in_app",
            status="sent",
        )
        for user_id in user_ids
    ]

    Notification.objects.bulk_create(notifications)
    return f"Created {len(notifications)} notifications"
