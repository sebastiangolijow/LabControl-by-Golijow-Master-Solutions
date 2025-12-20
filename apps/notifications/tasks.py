"""Celery tasks for notifications app."""

import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


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
        logger.info(f"Email sent to {user.email}")
        return f"Email sent to {user.email}"
    except User.DoesNotExist:
        logger.error(f"User {user_id} not found")
        return f"User {user_id} not found"
    except Exception as e:
        logger.error(f"Error sending email to user {user_id}: {str(e)}")
        return f"Error: {str(e)}"


@shared_task(bind=True, max_retries=3)
def send_result_notification_email(self, user_id, study_id, study_type_name):
    """
    Send HTML email notification when lab results are ready.

    Args:
        user_id: ID of the patient
        study_id: ID of the study
        study_type_name: Name of the study type (e.g., "Blood Test")

    This task will retry up to 3 times if email sending fails.
    """
    from apps.users.models import User

    try:
        user = User.objects.get(id=user_id)

        # Prepare context for email template
        context = {
            "patient_name": user.get_full_name() or user.email,
            "study_type_name": study_type_name,
            "login_url": f"{settings.FRONTEND_URL or 'http://localhost:8000'}/login",
        }

        # Render HTML email
        html_content = render_to_string("emails/result_ready.html", context)
        text_content = strip_tags(html_content)  # Fallback plain text

        # Create email
        subject = f"Your {study_type_name} Results Are Ready"
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        email.attach_alternative(html_content, "text/html")

        # Send email
        email.send(fail_silently=False)

        logger.info(f"Result notification email sent to {user.email} for study {study_id}")
        return f"Email sent to {user.email}"

    except User.DoesNotExist:
        logger.error(f"User {user_id} not found")
        return f"User {user_id} not found"

    except Exception as e:
        logger.error(f"Error sending result notification email: {str(e)}")
        # Retry the task with exponential backoff
        try:
            raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for user {user_id}, study {study_id}")
            return f"Failed after retries: {str(e)}"


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
