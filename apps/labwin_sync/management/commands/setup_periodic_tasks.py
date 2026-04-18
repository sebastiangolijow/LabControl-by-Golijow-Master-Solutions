"""
Management command to create/update Celery Beat periodic tasks.

Usage:
    python manage.py setup_periodic_tasks
"""

from django.core.management.base import BaseCommand
from django_celery_beat.models import CrontabSchedule, IntervalSchedule, PeriodicTask


class Command(BaseCommand):
    help = (
        "Create or update Celery Beat periodic tasks for LabWin sync and FTP PDF fetch"
    )

    TASKS = [
        {
            "name": "Sync LabWin results (nightly 2 AM)",
            "task": "apps.labwin_sync.tasks.sync_labwin_results",
            "schedule_type": "crontab",
            "crontab": {"hour": "2", "minute": "0"},
        },
        {
            "name": "Fetch FTP PDFs (every 30 min)",
            "task": "apps.labwin_sync.tasks.fetch_ftp_pdfs",
            "schedule_type": "interval",
            "interval": {"every": 30, "period": IntervalSchedule.MINUTES},
        },
        {
            "name": "Cleanup FTP PDFs (weekly Sunday 3 AM)",
            "task": "apps.labwin_sync.tasks.cleanup_ftp_pdfs",
            "schedule_type": "crontab",
            "crontab": {"hour": "3", "minute": "0", "day_of_week": "0"},
        },
    ]

    def handle(self, *args, **options):
        for task_def in self.TASKS:
            if task_def["schedule_type"] == "crontab":
                schedule, _ = CrontabSchedule.objects.get_or_create(
                    **task_def["crontab"],
                    defaults={"timezone": "UTC"},
                )
                task, created = PeriodicTask.objects.update_or_create(
                    name=task_def["name"],
                    defaults={
                        "task": task_def["task"],
                        "crontab": schedule,
                        "interval": None,
                        "enabled": True,
                    },
                )
            else:
                schedule, _ = IntervalSchedule.objects.get_or_create(
                    every=task_def["interval"]["every"],
                    period=task_def["interval"]["period"],
                )
                task, created = PeriodicTask.objects.update_or_create(
                    name=task_def["name"],
                    defaults={
                        "task": task_def["task"],
                        "interval": schedule,
                        "crontab": None,
                        "enabled": True,
                    },
                )

            status = "created" if created else "updated"
            self.stdout.write(
                f"  {'+'if created else '~'} {task_def['name']} — {status}"
            )

        self.stdout.write(self.style.SUCCESS("\nPeriodic tasks configured!"))
