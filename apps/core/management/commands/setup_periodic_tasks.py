"""
Management command to set up periodic tasks for Celery Beat.

This command creates the default periodic tasks in the database
for django-celery-beat scheduler.
"""

import json

from django.core.management.base import BaseCommand
from django_celery_beat.models import CrontabSchedule, PeriodicTask


class Command(BaseCommand):
    help = "Set up periodic tasks for Celery Beat"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Setting up periodic tasks..."))

        # Create crontab schedules
        weekly_sunday_2am, _ = CrontabSchedule.objects.get_or_create(
            minute="0",
            hour="2",
            day_of_week="0",  # Sunday
            day_of_month="*",
            month_of_year="*",
        )

        # Create periodic tasks

        # Note: Appointment reminders disabled — feature not yet implemented
        # task1, created1 = PeriodicTask.objects.get_or_create(
        #     name="Send Appointment Reminders",
        #     defaults={
        #         "task": "apps.appointments.tasks.send_appointment_reminders",
        #         "crontab": daily_9am,
        #         "enabled": False,
        #     },
        # )

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

        # Nightly LabWin backup import at 02:30 ART (= 05:30 UTC; Beat runs in
        # UTC per CELERY_TIMEZONE). The lab uploads .fbk.gz at 02:00 ART, which
        # takes ~2 min. import_uploaded_backup restores the new file and then
        # internally calls sync_labwin_results synchronously (BackupImporter.run
        # → trigger_sync), so we get a fresh-data sync in one job. 30 min
        # headroom is enough to absorb a slow upload or a network blip.
        nightly_530utc, _ = CrontabSchedule.objects.get_or_create(
            minute="30",
            hour="5",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
        )

        task_import, created_import = PeriodicTask.objects.get_or_create(
            name="Import LabWin Backup",
            defaults={
                "task": "apps.labwin_sync.tasks.import_uploaded_backup",
                "crontab": nightly_530utc,
                "enabled": True,
                "kwargs": json.dumps({"lab_client_id": 1}),
                "description": (
                    "Restores the latest .fbk.gz from /srv/labwin_backups/incoming "
                    "and triggers sync_labwin_results synchronously. Replaces the "
                    "standalone Sync LabWin Results schedule (which ran against "
                    "stale Firebird data)."
                ),
            },
        )
        if created_import:
            self.stdout.write(
                self.style.SUCCESS(
                    "✓ Created: Import LabWin Backup (Nightly 02:30 ART / 05:30 UTC)"
                )
            )
        else:
            if task_import.crontab_id != nightly_530utc.id:
                task_import.crontab = nightly_530utc
                task_import.interval = None
                task_import.enabled = True
                task_import.save(update_fields=["crontab", "interval", "enabled"])
                self.stdout.write(
                    self.style.SUCCESS(
                        "↻ Updated: Import LabWin Backup → 02:30 ART (05:30 UTC)"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        "○ Already exists: Import LabWin Backup (02:30 ART / 05:30 UTC)"
                    )
                )

        # Disable the standalone Sync LabWin Results schedule. It runs against
        # the stale Firebird container — the live data only arrives after
        # import_uploaded_backup restores last night's .fbk.gz. Since that task
        # chains to sync_labwin_results internally, leaving this row enabled
        # would sync twice (once on fresh data, once on stale). We keep the
        # PeriodicTask row + the task code itself so it can still be triggered
        # ad-hoc via management command (`sync_labwin --use-celery`).
        try:
            existing_sync = PeriodicTask.objects.get(name="Sync LabWin Results")
            if existing_sync.enabled:
                existing_sync.enabled = False
                existing_sync.save(update_fields=["enabled"])
                self.stdout.write(
                    self.style.SUCCESS(
                        "↻ Disabled: Sync LabWin Results "
                        "(now driven by Import LabWin Backup)"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING("○ Already disabled: Sync LabWin Results")
                )
        except PeriodicTask.DoesNotExist:
            self.stdout.write(
                self.style.WARNING("○ Sync LabWin Results not present (skipped)")
            )

        # Fetch FTP PDFs every 30 minutes
        from django_celery_beat.models import IntervalSchedule

        every_30_min, _ = IntervalSchedule.objects.get_or_create(
            every=30,
            period=IntervalSchedule.MINUTES,
        )

        task4, created4 = PeriodicTask.objects.get_or_create(
            name="Fetch FTP PDFs",
            defaults={
                "task": "apps.labwin_sync.tasks.fetch_ftp_pdfs",
                "interval": every_30_min,
                "enabled": True,
            },
        )
        if created4:
            self.stdout.write(
                self.style.SUCCESS("✓ Created: Fetch FTP PDFs (Every 30 min)")
            )
        else:
            self.stdout.write(self.style.WARNING("○ Already exists: Fetch FTP PDFs"))

        # Cleanup FTP PDFs weekly Sunday 3 AM
        weekly_sunday_3am, _ = CrontabSchedule.objects.get_or_create(
            minute="0",
            hour="3",
            day_of_week="0",
            day_of_month="*",
            month_of_year="*",
        )

        task5, created5 = PeriodicTask.objects.get_or_create(
            name="Cleanup FTP PDFs",
            defaults={
                "task": "apps.labwin_sync.tasks.cleanup_ftp_pdfs",
                "crontab": weekly_sunday_3am,
                "enabled": True,
            },
        )
        if created5:
            self.stdout.write(
                self.style.SUCCESS("✓ Created: Cleanup FTP PDFs (Weekly Sunday 3 AM)")
            )
        else:
            self.stdout.write(self.style.WARNING("○ Already exists: Cleanup FTP PDFs"))

        # Obsolete since 2026-05-08: this task moved orphan PDFs from chroot
        # root to /results/, which made sense in the old architecture where
        # the connector read from /results/. After the 2026-05-07 PDF upload
        # rebuild the connector reads from chroot root directly
        # (LABWIN_FTP_DIRECTORY=/) — moving files to /results/ would now
        # *hide* them from fetch_ftp_pdfs. Disable it on the live PeriodicTask
        # row to stop it firing. The task code stays in the repo for now in
        # case the lab's separate (broken) .FDB-pushing task needs it again.
        PeriodicTask.objects.filter(name="Cleanup Misplaced FTP Uploads").update(
            enabled=False
        )
        self.stdout.write(
            self.style.WARNING(
                "○ Disabled (obsolete): Cleanup Misplaced FTP Uploads"
            )
        )

        self.stdout.write(self.style.SUCCESS("\n✓ Periodic tasks setup complete!"))
        self.stdout.write(
            "\nYou can manage these tasks in Django Admin -> Periodic Tasks"
        )
