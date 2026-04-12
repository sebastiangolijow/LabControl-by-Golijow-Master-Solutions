"""
Management command to manually trigger LabWin sync.

Usage:
    python manage.py sync_labwin                  # Incremental sync (default)
    python manage.py sync_labwin --full           # Full sync (ignore cursor)
    python manage.py sync_labwin --lab-client-id 1
    python manage.py sync_labwin --use-celery     # Run via Celery worker
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Manually trigger LabWin Firebird database sync"

    def add_arguments(self, parser):
        parser.add_argument(
            "--full",
            action="store_true",
            help="Full sync (ignore last cursor, sync all records)",
        )
        parser.add_argument(
            "--lab-client-id",
            type=int,
            default=None,
            help="Lab client ID to assign to synced records",
        )
        parser.add_argument(
            "--use-celery",
            action="store_true",
            help="Run via Celery worker instead of synchronously",
        )

    def handle(self, *args, **options):
        from apps.labwin_sync.tasks import sync_labwin_results

        lab_client_id = options["lab_client_id"]
        full_sync = options["full"]

        if options["use_celery"]:
            result = sync_labwin_results.delay(
                lab_client_id=lab_client_id,
                full_sync=full_sync,
            )
            self.stdout.write(
                self.style.SUCCESS(f"Task submitted to Celery: {result.id}")
            )
            self.stdout.write(
                "Monitor progress in Django Admin -> Periodic Tasks or Flower."
            )
        else:
            self.stdout.write("Starting LabWin sync (synchronous mode)...")
            self.stdout.write(
                f"  Full sync: {full_sync}, Lab client ID: {lab_client_id}"
            )

            result = sync_labwin_results(
                lab_client_id=lab_client_id,
                full_sync=full_sync,
            )

            self.stdout.write(self.style.SUCCESS(f"\n{result['message']}"))
            self.stdout.write(f"  Total processed: {result['total_processed']}")
            self.stdout.write(f"  Studies created: {result['studies_created']}")
            self.stdout.write(f"  Studies updated: {result['studies_updated']}")
            self.stdout.write(f"  Patients created: {result['patients_created']}")
            self.stdout.write(f"  Doctors created: {result['doctors_created']}")
            self.stdout.write(f"  Practices created: {result['practices_created']}")
            if result["error_count"]:
                self.stdout.write(
                    self.style.WARNING(f"  Errors: {result['error_count']}")
                )
