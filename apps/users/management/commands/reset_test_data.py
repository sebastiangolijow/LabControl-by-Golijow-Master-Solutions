"""
Reset test-mode data: delete all patients and studies, leaving practices,
doctors, lab_staff and admin users intact.

Used to validate the LabWin ingestion pipeline against real data without
carrying state from previous runs. The next `import_backup` / `sync_labwin`
will re-create the patients and studies from scratch.

Safety:
- Refuses to run without --confirm.
- Refuses to run if DEBUG=False AND DISABLE_PATIENT_EMAILS=False — that
  combination means "we're in production and emails are live", and we
  should not silently nuke patient data in that posture.

Usage:
    python manage.py reset_test_data --dry-run    # report only
    python manage.py reset_test_data --confirm    # actually delete
"""

import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.labwin_sync.models import SyncedRecord
from apps.studies.models import Study
from apps.users.models import User

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Delete all patients and studies (test-mode reset). Practices, "
        "doctors, lab_staff and admins are preserved."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Required to actually run the deletion. Without this flag "
            "the command refuses to do anything destructive.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without making changes",
        )

    def handle(self, *args, **options):
        confirm = options["confirm"]
        dry_run = options["dry_run"]

        if not confirm and not dry_run:
            raise CommandError(
                "Refusing to run without --confirm. Pass --dry-run to "
                "see what would be deleted, or --confirm to actually delete."
            )

        # Production safety gate: if we're not in DEBUG mode and the
        # patient-email kill switch is off, we're effectively in live prod.
        # Don't allow accidental data wipes there.
        disable_emails = getattr(settings, "DISABLE_PATIENT_EMAILS", False)
        if not settings.DEBUG and not disable_emails and confirm:
            raise CommandError(
                "Refusing to run in live production posture "
                "(DEBUG=False AND DISABLE_PATIENT_EMAILS=False). Set "
                "DISABLE_PATIENT_EMAILS=True in .env.production first if "
                "this is intentional."
            )

        # Snapshot counts before
        before = self._snapshot()
        self._report("BEFORE", before)

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY RUN — no changes"))
            return

        with transaction.atomic():
            # Order matters: studies first (so SyncedRecord(target_model=Study)
            # rows can be cleaned up while we still have their pks); then
            # patients; then orphan SyncedRecord rows.
            study_pks = list(Study.objects.values_list("pk", flat=True))
            patient_pks = list(
                User.objects.filter(role="patient").values_list("pk", flat=True)
            )

            # Delete SyncedRecord rows pointing to studies/patients we're
            # about to delete. Without this the next sync would think those
            # rows were already imported and skip them, leaving a phantom
            # state where PACIENTES rows can't be re-imported.
            sr_studies = SyncedRecord.objects.filter(
                target_model="Study", target_uuid__in=study_pks
            )
            sr_users = SyncedRecord.objects.filter(
                target_model="User", target_uuid__in=patient_pks
            )
            n_sr_studies, _ = sr_studies.delete()
            n_sr_users, _ = sr_users.delete()
            logger.info(
                "reset_test_data: deleted SyncedRecords — studies=%d users=%d",
                n_sr_studies,
                n_sr_users,
            )

            # Studies cascade to StudyPractice and UserDetermination.
            n_studies, _ = Study.objects.all().delete()
            logger.info("reset_test_data: deleted studies (cascade) — count=%d", n_studies)

            # Patients cascade to Appointments, Invoices, Notifications.
            n_patients, _ = User.objects.filter(role="patient").delete()
            logger.info(
                "reset_test_data: deleted patients (cascade) — count=%d", n_patients
            )

        after = self._snapshot()
        self._report("AFTER", after)

        self.stdout.write(self.style.SUCCESS("\n✓ Reset complete."))

    def _snapshot(self):
        return {
            "patients": User.objects.filter(role="patient").count(),
            "doctors": User.objects.filter(role="doctor").count(),
            "lab_staff": User.objects.filter(role="lab_staff").count(),
            "admins": User.objects.filter(role="admin").count(),
            "studies": Study.objects.count(),
            "synced_records_user": SyncedRecord.objects.filter(
                target_model="User"
            ).count(),
            "synced_records_study": SyncedRecord.objects.filter(
                target_model="Study"
            ).count(),
        }

    def _report(self, label, snap):
        self.stdout.write(f"\n{label}:")
        for key, val in snap.items():
            self.stdout.write(f"  {key}: {val}")
