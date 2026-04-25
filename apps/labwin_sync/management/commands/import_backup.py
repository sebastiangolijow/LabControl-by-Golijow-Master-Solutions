"""
Manually trigger Phase B of the LabWin backup pipeline.

Restores the most recent (or a specified) `.fbk.gz` from
`/srv/labwin_backups/incoming/` into the firebird container, then runs
sync_labwin_results.

Usage:
    python manage.py import_backup                  # latest backup, full pipeline
    python manage.py import_backup --file PATH      # specific file
    python manage.py import_backup --restore-only   # restore, skip sync
    python manage.py import_backup --sync-only      # sync, skip restore (DB already loaded)
    python manage.py import_backup --use-celery     # dispatch via Celery worker
    python manage.py import_backup --lab-client-id 1
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Restore the latest LabWin .fbk.gz backup into the firebird container "
        "and trigger sync_labwin_results."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default=None,
            help="Path to a specific .fbk.gz to restore (default: latest in incoming/)",
        )
        parser.add_argument(
            "--restore-only",
            action="store_true",
            help="Restore the backup but skip the sync_labwin_results step",
        )
        parser.add_argument(
            "--sync-only",
            action="store_true",
            help=(
                "Skip the restore step (assume firebird already has the data) "
                "and just run sync_labwin_results"
            ),
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
            help="Dispatch via Celery worker instead of running synchronously",
        )

    def handle(self, *args, **options):
        if options["restore_only"] and options["sync_only"]:
            raise CommandError("--restore-only and --sync-only are mutually exclusive")

        explicit_file = options["file"]
        lab_client_id = options["lab_client_id"]

        if options["use_celery"]:
            from apps.labwin_sync.tasks import import_uploaded_backup

            if options["restore_only"] or options["sync_only"]:
                raise CommandError(
                    "--restore-only / --sync-only are not supported with --use-celery "
                    "(the task always runs the full pipeline)"
                )
            result = import_uploaded_backup.delay(
                lab_client_id=lab_client_id,
                explicit_file=explicit_file,
            )
            self.stdout.write(
                self.style.SUCCESS(f"Task submitted to Celery: {result.id}")
            )
            self.stdout.write(
                "Monitor in Django Admin → SyncLog or with: "
                "celery -A config inspect active"
            )
            return

        # Synchronous path — uses BackupImporter directly so we get fine-grained
        # control over restore_only / sync_only flags.
        from apps.labwin_sync.services.backup_import import BackupImporter

        self.stdout.write("Starting backup import (synchronous mode)...")
        self.stdout.write(
            f"  File: {explicit_file or '(latest in incoming/)'}, "
            f"lab_client_id: {lab_client_id}, "
            f"restore_only: {options['restore_only']}, "
            f"sync_only: {options['sync_only']}"
        )

        importer = BackupImporter(lab_client_id=lab_client_id)
        result = importer.run(
            explicit_file=Path(explicit_file) if explicit_file else None,
            skip_restore=options["sync_only"],
            skip_sync=options["restore_only"],
        )

        # Pretty-print the result
        self.stdout.write("")
        self.stdout.write("=" * 60)
        if result.status == "completed":
            self.stdout.write(self.style.SUCCESS(f"Status: {result.status}"))
        elif result.status == "skipped":
            self.stdout.write(self.style.WARNING(f"Status: {result.status}"))
        else:
            self.stdout.write(self.style.ERROR(f"Status: {result.status}"))
        if result.backup_filename:
            self.stdout.write(f"Backup:  {result.backup_filename}")
            self.stdout.write(f"Size:    {result.backup_size_bytes / 1_048_576:.1f} MB")
        if result.restore_duration_s:
            self.stdout.write(f"Restore: {result.restore_duration_s:.1f}s")
        if result.sync_result:
            sync_msg = result.sync_result.get("message", "")
            self.stdout.write(f"Sync:    {sync_msg}")
        if result.error:
            self.stdout.write(self.style.ERROR(f"Error:   {result.error}"))
        if result.sync_log_uuid:
            self.stdout.write(f"SyncLog: {result.sync_log_uuid}")
        self.stdout.write("=" * 60)

        if result.status == "failed":
            raise CommandError(result.error or "import_backup failed")
