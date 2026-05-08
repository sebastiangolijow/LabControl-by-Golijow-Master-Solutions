"""
Sync Practice.result_layout from LabWin's RESULTS + VALNOR tables.

This command pulls the per-position practice metadata that LabWin keeps
separately from NOMEN, builds the structured `result_layout` JSON, and
writes it to every matching Practice in our DB.

Run after a fresh `import_backup` so the Firebird container has the
restored DB. Idempotent — re-running just refreshes the layouts.

Usage:
    python manage.py sync_practice_layouts
    python manage.py sync_practice_layouts --dry-run
    python manage.py sync_practice_layouts --code HEMC
    python manage.py sync_practice_layouts --code HEMC --code COA
"""

import logging

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.labwin_sync.connectors import get_connector
from apps.labwin_sync.services.practice_layout import build_layout
from apps.studies.models import Practice

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Build Practice.result_layout from LabWin RESULTS + VALNOR tables"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without writing to the DB",
        )
        parser.add_argument(
            "--code",
            action="append",
            default=[],
            help="Limit to specific practice codes (ABREV_FLD). Can repeat. "
            "Default: all practices in our DB.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        code_filter = options["code"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no changes will be made"))

        # Decide which practice codes we're processing
        practices_qs = Practice.objects.filter(code__isnull=False).exclude(code="")
        if code_filter:
            practices_qs = practices_qs.filter(code__in=code_filter)

        practice_codes = list(practices_qs.values_list("code", flat=True))
        if not practice_codes:
            self.stdout.write(self.style.WARNING("No practices to sync"))
            return

        self.stdout.write(f"Syncing layouts for {len(practice_codes)} practice(s)")

        # Pull the metadata from Firebird in one shot per table
        with get_connector() as connector:
            self.stdout.write("Fetching RESULTS metadata...")
            results_by_abbrev = connector.fetch_results_metadata(practice_codes)
            results_count = sum(len(v) for v in results_by_abbrev.values())
            self.stdout.write(
                f"  → {results_count} RESULTS rows for {len(results_by_abbrev)} "
                f"practices"
            )

            self.stdout.write("Fetching VALNOR metadata...")
            valnor_by_abbrev = connector.fetch_valnor(practice_codes)
            valnor_count = sum(len(v) for v in valnor_by_abbrev.values())
            self.stdout.write(
                f"  → {valnor_count} VALNOR rows for {len(valnor_by_abbrev)} "
                f"practices"
            )

        # Build & write
        stats = {"updated": 0, "cleared": 0, "skipped": 0, "errors": 0}
        with transaction.atomic():
            for practice in practices_qs.iterator():
                code = practice.code
                results_rows = results_by_abbrev.get(code, [])
                valnor_rows = valnor_by_abbrev.get(code, [])

                try:
                    layout = build_layout(code, results_rows, valnor_rows)
                except Exception:  # noqa: BLE001 — log + continue per practice
                    logger.exception("build_layout failed for practice code=%r", code)
                    stats["errors"] += 1
                    continue

                if layout is None:
                    if practice.result_layout is not None:
                        if not dry_run:
                            practice.result_layout = None
                            practice.save(update_fields=["result_layout"])
                        stats["cleared"] += 1
                    else:
                        stats["skipped"] += 1
                    continue

                if practice.result_layout != layout:
                    if not dry_run:
                        practice.result_layout = layout
                        practice.save(update_fields=["result_layout"])
                    stats["updated"] += 1
                else:
                    stats["skipped"] += 1

            if dry_run:
                # Roll back any accidental writes
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS("\n=== Summary ==="))
        for key, val in stats.items():
            self.stdout.write(f"  {key}: {val}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY RUN — no changes written"))
