"""
Management command to set up periodic tasks for Celery Beat.

This command creates the default periodic tasks in the database
for django-celery-beat scheduler.
"""
from django.core.management.base import BaseCommand
from django_celery_beat.models import CrontabSchedule, PeriodicTask
import json


class Command(BaseCommand):
    help = "Set up periodic tasks for Celery Beat"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Setting up periodic tasks..."))

        # Create crontab schedules
        daily_9am, _ = CrontabSchedule.objects.get_or_create(
            minute="0",
            hour="9",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
        )

        weekly_sunday_2am, _ = CrontabSchedule.objects.get_or_create(
            minute="0",
            hour="2",
            day_of_week="0",  # Sunday
            day_of_month="*",
            month_of_year="*",
        )

        # Create periodic tasks
        task1, created1 = PeriodicTask.objects.get_or_create(
            name="Send Appointment Reminders",
            defaults={
                "task": "apps.appointments.tasks.send_appointment_reminders",
                "crontab": daily_9am,
                "enabled": True,
            },
        )
        if created1:
            self.stdout.write(
                self.style.SUCCESS("✓ Created: Send Appointment Reminders (Daily 9 AM)")
            )
        else:
            self.stdout.write(
                self.style.WARNING("○ Already exists: Send Appointment Reminders")
            )

        task2, created2 = PeriodicTask.objects.get_or_create(
            name="Cleanup Old Notifications",
            defaults={
                "task": "apps.notifications.tasks.cleanup_old_notifications",
                "crontab": weekly_sunday_2am,
                "enabled": True,
            },
        )
        if created2:
            self.stdout.write(
                self.style.SUCCESS(
                    "✓ Created: Cleanup Old Notifications (Weekly Sunday 2 AM)"
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING("○ Already exists: Cleanup Old Notifications")
            )

        self.stdout.write(
            self.style.SUCCESS("\n✓ Periodic tasks setup complete!")
        )
        self.stdout.write(
            "\nYou can manage these tasks in Django Admin -> Periodic Tasks"
        )
