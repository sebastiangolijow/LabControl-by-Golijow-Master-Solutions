"""Celery tasks for appointments app."""
from celery import shared_task
from django.utils import timezone


@shared_task
def send_appointment_reminders():
    """
    Send reminders for upcoming appointments.

    This task runs daily to send reminders to patients
    with appointments in the next 24 hours.
    """
    from .models import Appointment

    # Get appointments for tomorrow that haven't been reminded
    tomorrow = timezone.now().date() + timezone.timedelta(days=1)
    appointments = Appointment.objects.filter(
        scheduled_date=tomorrow,
        status__in=["scheduled", "confirmed"],
        reminder_sent=False,
    )

    for appointment in appointments:
        # TODO: Send email/SMS reminder
        # Example: send_email(appointment.patient.email, "Appointment Reminder", ...)

        # Mark reminder as sent
        appointment.reminder_sent = True
        appointment.reminder_sent_at = timezone.now()
        appointment.save(update_fields=["reminder_sent", "reminder_sent_at"])

    return f"Sent {appointments.count()} reminders"
