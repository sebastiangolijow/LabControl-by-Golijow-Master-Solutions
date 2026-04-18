"""
Import practices from LabWin CSV exports.

Loads two files:
1. practicas CSV (CODIGO, DETERMINACION) → Practice.code + Practice.name
2. Abrev y valores de referencia CSV (ABREV_FLD, RESULTS_FLD) →
   Practice.result_template + Practice.reference_range

Usage:
    python manage.py import_labwin_practices \
        --practices /path/to/practicas.csv \
        --references /path/to/referencias.csv
"""

import csv
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.studies.models import Practice


def extract_reference_range(results_fld):
    """
    Extract human-readable reference range text from LabWin RESULTS_FLD template.

    Strips LabWin formatting tags ({L=2}, {CrLf}, {FB=1}, etc.) and
    result slot placeholders (R00000000001, T001, V001, F factors).
    Returns cleaned text if meaningful content remains.
    """
    if not results_fld:
        return ""

    text = results_fld

    # Replace {CrLf} with newlines
    text = re.sub(r"\{CrLf\}", "\n", text, flags=re.IGNORECASE)

    # Remove all other LabWin formatting tags
    text = re.sub(r"\{[^}]*\}", "", text)

    # Remove result slot placeholders (R00000000001, R        001, etc.)
    text = re.sub(r"[RTVF]\s*0+\d+", "", text)

    # Remove formula operators
    text = re.sub(r"[=*]", " ", text)

    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    text = text.strip()

    # Only return if there's meaningful content (not just whitespace)
    if len(text) < 5:
        return ""

    # Truncate to fit field max_length
    if len(text) > 500:
        text = text[:497] + "..."

    return text


class Command(BaseCommand):
    help = "Import practices from LabWin CSV exports (practicas + reference values)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--practices",
            type=str,
            required=True,
            help="Path to practicas CSV (CODIGO, DETERMINACION)",
        )
        parser.add_argument(
            "--references",
            type=str,
            help="Path to reference values CSV (ABREV_FLD, RESULTS_FLD)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all existing practices before importing (DANGEROUS)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be imported without making changes",
        )

    def handle(self, *args, **options):
        practices_file = options["practices"]
        references_file = options.get("references")
        clear = options["clear"]
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no changes will be made"))

        # Step 1: Read practices CSV
        self.stdout.write(f"\nReading practices from: {practices_file}")
        practices_data = self._read_practices_csv(practices_file)
        if not practices_data:
            return
        self.stdout.write(f"  Found {len(practices_data)} practices")

        # Step 2: Read references CSV (optional)
        references_data = {}
        if references_file:
            self.stdout.write(f"\nReading references from: {references_file}")
            references_data = self._read_references_csv(references_file)
            self.stdout.write(f"  Found {len(references_data)} reference entries")

            # Count how many have meaningful reference text
            with_ref = sum(
                1 for v in references_data.values() if v.get("reference_range")
            )
            self.stdout.write(f"  {with_ref} entries have extractable reference ranges")

        # Step 3: Merge data
        merged = self._merge_data(practices_data, references_data)

        # Step 4: Import
        if dry_run:
            self._dry_run_report(merged)
        else:
            self._import_practices(merged, clear)

    def _read_practices_csv(self, file_path):
        """Read practicas CSV → dict of {code: name}."""
        try:
            # Try UTF-8 first, fall back to latin-1
            for encoding in ["utf-8", "latin-1"]:
                try:
                    with open(file_path, "r", encoding=encoding) as f:
                        reader = csv.reader(f)
                        header = next(reader)

                        # Validate header
                        if len(header) < 2:
                            self.stdout.write(
                                self.style.ERROR(
                                    f"Expected at least 2 columns, got {len(header)}"
                                )
                            )
                            return None

                        practices = {}
                        for row in reader:
                            if len(row) < 2:
                                continue
                            code = row[0].strip()
                            name = row[1].strip()
                            if code and name:
                                practices[code] = name

                        return practices
                except UnicodeDecodeError:
                    continue

            self.stdout.write(self.style.ERROR("Could not decode file"))
            return None
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"File not found: {file_path}"))
            return None

    def _read_references_csv(self, file_path):
        """Read reference values CSV → dict of {code: {template, reference_range}}."""
        try:
            with open(file_path, "r", encoding="latin-1") as f:
                reader = csv.reader(f)
                header = next(reader)

                references = {}
                for row in reader:
                    if len(row) < 2:
                        continue
                    code = row[0].strip()
                    results_fld = row[1] if len(row) > 1 else ""
                    if not code:
                        continue

                    references[code] = {
                        "result_template": results_fld.strip()[:2000],
                    }

                return references
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"File not found: {file_path}"))
            return {}

    def _merge_data(self, practices_data, references_data):
        """Merge practices and references into a single list."""
        merged = []
        for code, name in practices_data.items():
            ref = references_data.get(code, {})
            merged.append(
                {
                    "code": code,
                    "name": name,
                    "result_template": ref.get("result_template", ""),
                }
            )
        return merged

    def _dry_run_report(self, merged):
        """Show what would be imported."""
        existing_codes = set(
            Practice.objects.values_list("code", flat=True).exclude(code="")
        )

        new = [p for p in merged if p["code"] not in existing_codes]
        update = [p for p in merged if p["code"] in existing_codes]
        with_ref = [p for p in merged if p["reference_range"]]

        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(self.style.SUCCESS("DRY RUN REPORT"))
        self.stdout.write(f"{'='*60}")
        self.stdout.write(f"Total practices in CSV: {len(merged)}")
        self.stdout.write(f"Already in DB (will update): {len(update)}")
        self.stdout.write(f"New (will create): {len(new)}")
        self.stdout.write(f"With reference ranges: {len(with_ref)}")
        self.stdout.write(f"Current DB count: {Practice.objects.count()}")

        if with_ref:
            self.stdout.write(f"\nSample reference ranges:")
            for p in with_ref[:5]:
                self.stdout.write(f"  {p['code']}: {p['reference_range'][:100]}")

    def _import_practices(self, merged, clear):
        """Import practices into the database."""
        if clear:
            count = Practice.objects.count()
            Practice.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(f"\nDeleted {count} existing practices")
            )

        created = 0
        updated = 0
        errors = 0

        with transaction.atomic():
            for item in merged:
                try:
                    defaults = {"name": item["name"], "is_active": True}

                    if item["result_template"]:
                        defaults["result_template"] = item["result_template"]
                    if item["reference_range"]:
                        defaults["reference_range"] = item["reference_range"]

                    practice, was_created = Practice.objects.update_or_create(
                        code=item["code"],
                        defaults=defaults,
                    )

                    if was_created:
                        created += 1
                    else:
                        updated += 1

                except Exception as e:
                    errors += 1
                    self.stdout.write(self.style.ERROR(f"  Error {item['code']}: {e}"))

        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(self.style.SUCCESS("IMPORT COMPLETE"))
        self.stdout.write(f"{'='*60}")
        self.stdout.write(f"Created: {created}")
        self.stdout.write(f"Updated: {updated}")
        if errors:
            self.stdout.write(self.style.ERROR(f"Errors: {errors}"))
        self.stdout.write(f"Total in DB: {Practice.objects.count()}")
