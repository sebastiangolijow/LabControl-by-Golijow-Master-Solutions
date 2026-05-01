"""
Cleanup misplaced uploads on the LabWin FTP server.

The FTP user `labwin_ftp` is meant to upload only PDF results into
`/results/`. In practice we've seen two failure modes from the lab side:

1. Raw Firebird DB snapshots (`*.FDB`, `*.fbk`, `*.fbk.gz`) being uploaded
   into `/results/` — these belong in the SFTP backup pipeline and clutter
   the PDF folder with multi-GB files that slow down `fetch_ftp_pdfs`.
2. PDFs landing in the FTP chroot root (`/home/labwin_ftp/`) instead of
   in `/results/` — usually because the lab forgot to `cd` first.

This command scans both locations and:

- Deletes any `*.FDB` / `*.fbk` / `*.fbk.gz` it finds (in either location).
- Moves any orphan `.pdf` from the FTP root into `/results/` (does NOT
  delete — preserves the upload).

# REMOVE-ONCE-LAB-FIXES-DUPLICATE-UPLOAD: see CLAUDE.md TODO. Once the lab
# stops pushing nightly .FDB files via FTP, this command and its companion
# Celery task `cleanup_misplaced_uploads` can be deleted.

Usage:
    python manage.py cleanup_misplaced_fdb              # delete + move
    python manage.py cleanup_misplaced_fdb --dry-run    # report only
"""

import logging

from django.core.management.base import BaseCommand

from apps.labwin_sync.ftp import get_ftp_connector

logger = logging.getLogger(__name__)


# Extensions we delete outright — never legitimate uploads on this FTP
DELETABLE_EXTENSIONS = (".fdb", ".fbk", ".fbk.gz")


def cleanup_misplaced_uploads(dry_run=False):
    """Connect to the LabWin FTP and scrub misplaced uploads.

    Returns:
        dict with keys: deleted (list of filenames), moved (list of
        (src, dst) tuples), bytes_freed (int), errors (list of strings).
    """
    deleted = []
    moved = []
    bytes_freed = 0
    errors = []

    connector = get_ftp_connector()
    connector.connect()
    try:
        ftp = connector._ftp  # underlying ftplib.FTP from FTPConnector

        # Step 1: in /results/ (where connector.connect() left us) — delete
        # any *.FDB / *.fbk / *.fbk.gz files.
        try:
            entries = ftp.mlsd()
            entries = list(entries)
        except Exception:
            # Server doesn't support MLSD — fall back to a plain LIST + size lookup.
            entries = []
            for name in ftp.nlst():
                try:
                    size = ftp.size(name)
                except Exception:
                    size = 0
                entries.append((name, {"size": str(size or 0), "type": "file"}))

        for name, facts in entries:
            if name in (".", ".."):
                continue
            if facts.get("type") not in ("file", None):
                continue
            if not _is_deletable(name):
                continue
            size = int(facts.get("size") or 0)
            logger.warning(
                "cleanup_misplaced: found stray %s in /results/ (size=%d bytes)",
                name,
                size,
            )
            if dry_run:
                deleted.append(name)
                bytes_freed += size
                continue
            try:
                ftp.delete(name)
                deleted.append(name)
                bytes_freed += size
                logger.info("cleanup_misplaced: deleted /results/%s", name)
            except Exception as e:
                msg = f"failed to delete /results/{name}: {e}"
                errors.append(msg)
                logger.exception(msg)

        # Step 2: in the FTP chroot root — delete .FDB-likes and move stray PDFs.
        try:
            ftp.cwd("/")
        except Exception as e:
            errors.append(f"failed to cwd to /: {e}")
            logger.exception("cleanup_misplaced: failed to cwd to /")
            return _result(deleted, moved, bytes_freed, errors)

        try:
            root_entries = list(ftp.mlsd())
        except Exception:
            root_entries = []
            for name in ftp.nlst():
                try:
                    size = ftp.size(name)
                except Exception:
                    size = 0
                root_entries.append((name, {"size": str(size or 0), "type": "file"}))

        for name, facts in root_entries:
            if name in (".", ".."):
                continue
            if facts.get("type") not in ("file", None):
                continue
            lower = name.lower()
            size = int(facts.get("size") or 0)

            if _is_deletable(name):
                logger.warning(
                    "cleanup_misplaced: found stray %s in /  (size=%d bytes)",
                    name,
                    size,
                )
                if dry_run:
                    deleted.append(f"/{name}")
                    bytes_freed += size
                    continue
                try:
                    ftp.delete(name)
                    deleted.append(f"/{name}")
                    bytes_freed += size
                    logger.info("cleanup_misplaced: deleted /%s", name)
                except Exception as e:
                    msg = f"failed to delete /{name}: {e}"
                    errors.append(msg)
                    logger.exception(msg)

            elif lower.endswith(".pdf"):
                # Orphan PDF in chroot root — move to /results/. We use FTP
                # RNFR/RNTO (rename) which on vsftpd works across the chroot
                # without re-uploading the bytes.
                logger.warning(
                    "cleanup_misplaced: orphan PDF in / — moving to /results/: %s",
                    name,
                )
                if dry_run:
                    moved.append((f"/{name}", f"/results/{name}"))
                    continue
                try:
                    ftp.rename(name, f"/results/{name}")
                    moved.append((f"/{name}", f"/results/{name}"))
                    logger.info(
                        "cleanup_misplaced: moved /%s -> /results/%s", name, name
                    )
                except Exception as e:
                    msg = f"failed to move /{name} to /results/: {e}"
                    errors.append(msg)
                    logger.exception(msg)
    finally:
        connector.disconnect()

    return _result(deleted, moved, bytes_freed, errors)


def _is_deletable(name):
    lower = name.lower()
    return lower.endswith(DELETABLE_EXTENSIONS)


def _result(deleted, moved, bytes_freed, errors):
    return {
        "deleted": deleted,
        "moved": moved,
        "bytes_freed": bytes_freed,
        "errors": errors,
    }


class Command(BaseCommand):
    help = (
        "Delete misplaced .FDB/.fbk uploads from the LabWin FTP and move "
        "orphan PDFs from the chroot root into /results/."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without modifying anything",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no changes"))

        result = cleanup_misplaced_uploads(dry_run=dry_run)

        mb = result["bytes_freed"] / 1024 / 1024
        self.stdout.write(
            f"\nDeleted: {len(result['deleted'])} files " f"({mb:.1f} MB freed)"
        )
        for name in result["deleted"]:
            self.stdout.write(f"  - {name}")

        self.stdout.write(f"\nMoved: {len(result['moved'])} files")
        for src, dst in result["moved"]:
            self.stdout.write(f"  - {src} -> {dst}")

        if result["errors"]:
            self.stdout.write(self.style.ERROR(f"\nErrors: {len(result['errors'])}"))
            for err in result["errors"]:
                self.stdout.write(self.style.ERROR(f"  - {err}"))
