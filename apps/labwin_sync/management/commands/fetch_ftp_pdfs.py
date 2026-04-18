"""
Management command to fetch PDF result files from FTP server.

Usage:
    python manage.py fetch_ftp_pdfs                  # Fetch without deleting from FTP
    python manage.py fetch_ftp_pdfs --delete          # Fetch and delete from FTP
    python manage.py fetch_ftp_pdfs --cleanup          # Only delete already-processed PDFs
    python manage.py fetch_ftp_pdfs --use-celery       # Run via Celery worker
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Fetch PDF result files from FTP server and attach to studies"

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Delete PDFs from FTP after successful download",
        )
        parser.add_argument(
            "--cleanup",
            action="store_true",
            help="Only clean up FTP files for studies that already have PDFs",
        )
        parser.add_argument(
            "--use-celery",
            action="store_true",
            help="Run via Celery worker instead of synchronously",
        )
        parser.add_argument(
            "--lab-client-id",
            type=int,
            default=None,
            help="Lab client ID (default: LABWIN_DEFAULT_LAB_CLIENT_ID)",
        )

    def handle(self, *args, **options):
        from apps.labwin_sync.tasks import cleanup_ftp_pdfs, fetch_ftp_pdfs

        lab_client_id = options["lab_client_id"]

        if options["cleanup"]:
            if options["use_celery"]:
                task = cleanup_ftp_pdfs.delay(lab_client_id=lab_client_id)
                self.stdout.write(f"Cleanup task queued: {task.id}")
            else:
                result = cleanup_ftp_pdfs(lab_client_id=lab_client_id)
                self.stdout.write(self.style.SUCCESS(result["message"]))
        else:
            if options["use_celery"]:
                task = fetch_ftp_pdfs.delay(
                    lab_client_id=lab_client_id,
                    delete_after_download=options["delete"],
                )
                self.stdout.write(f"Fetch task queued: {task.id}")
            else:
                result = fetch_ftp_pdfs(
                    lab_client_id=lab_client_id,
                    delete_after_download=options["delete"],
                )
                self.stdout.write(self.style.SUCCESS(result["message"]))
