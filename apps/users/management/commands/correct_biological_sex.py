"""
One-shot data correction for the SEXO_FLD inversion bug (2026-05-12).

The original mappers.map_patient had SEXO_FLD encoded as 1=Male, 2=Female,
but the actual LabWin convention is 1=Female, 2=Male (verified against
real PACIENTES rows on 2026-05-12). Every patient ever imported by sync
had their biological sex inverted. PR 2's migration then copied the
wrong `gender` value into the new `biological_sex` field, so after the
migration both fields are wrong for every synced patient.

This command:
  1. Walks every user with biological_sex IN ('M', 'F').
  2. Swaps the value (M ↔ F).
  3. Clears `gender` for role='patient' — pre-PR-2 sync wrote gender
     from the same broken mapping, so it's wrong too. Clearing lets
     the patient self-declare correctly through the profile flow. Patients
     who already self-declared (very few; UAT started 2026-05-11) will
     need to re-set; a small price to pay for getting the data right.

Run with --dry-run first to see what would change. Re-run without
--dry-run AND with --confirm to apply.

REMOVE-ONCE-APPLIED: this command is single-use. Once executed in
prod, delete the file (and the entry in CLAUDE.md TODO).
"""

import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

logger = logging.getLogger(__name__)


SWAP_MAP = {"M": "F", "F": "M"}


class Command(BaseCommand):
    help = (
        "One-shot: swap User.biological_sex M<->F (correcting the SEXO_FLD "
        "inversion bug) and clear User.gender for patients."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without writing anything.",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Required to actually apply changes (paired with no --dry-run).",
        )
        parser.add_argument(
            "--clear-gender",
            action="store_true",
            default=True,
            help=(
                "Clear User.gender for role='patient' (default ON). "
                "Use --no-clear-gender to keep the existing gender values."
            ),
        )
        parser.add_argument(
            "--no-clear-gender",
            dest="clear_gender",
            action="store_false",
        )

    def handle(self, *args, **options):
        from apps.users.models import User

        dry_run = options["dry_run"]
        confirm = options["confirm"]
        clear_gender = options["clear_gender"]

        if not dry_run and not confirm:
            raise CommandError(
                "Refusing to run without --dry-run or --confirm. "
                "Run with --dry-run first to preview, then re-run with --confirm."
            )

        # Snapshot before
        before_dist = self._distribution()
        self.stdout.write(
            self.style.NOTICE(
                f"\nBefore: biological_sex distribution\n{self._format_dist(before_dist)}"
            )
        )

        # Build the worklist
        candidates = User.objects.filter(biological_sex__in=["M", "F"])
        total = candidates.count()
        self.stdout.write(f"\nCandidates to swap: {total}")

        if dry_run:
            patient_count = candidates.filter(role="patient").count()
            self.stdout.write(
                f"  (would clear gender on {patient_count} role='patient' users)"
                if clear_gender
                else "  (would NOT clear gender per --no-clear-gender)"
            )
            self.stdout.write(self.style.SUCCESS("\nDry run — no writes performed."))
            return

        with transaction.atomic():
            swapped = 0
            for user in candidates.iterator(chunk_size=500):
                old = user.biological_sex
                user.biological_sex = SWAP_MAP[old]
                update_fields = ["biological_sex", "updated_at"]
                if clear_gender and user.role == "patient" and user.gender:
                    user.gender = ""
                    update_fields.append("gender")
                user.save(update_fields=update_fields)
                swapped += 1
                if swapped % 500 == 0:
                    self.stdout.write(f"  ... {swapped}/{total}")

        after_dist = self._distribution()
        self.stdout.write(
            self.style.NOTICE(
                f"\nAfter: biological_sex distribution\n{self._format_dist(after_dist)}"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(f"\nDone. Swapped {swapped} users.")
        )

    def _distribution(self):
        from apps.users.models import User
        from django.db.models import Count

        rows = (
            User.objects.values("biological_sex")
            .annotate(n=Count("pk"))
            .order_by("biological_sex")
        )
        return {(r["biological_sex"] or ""): r["n"] for r in rows}

    def _format_dist(self, dist):
        lines = []
        for k in sorted(dist):
            label = repr(k) if k else "(empty)"
            lines.append(f"  {label}: {dist[k]}")
        return "\n".join(lines) if lines else "  (no rows)"
