"""
Restore the latest LabWin backup uploaded by the lab PC and trigger a sync.

The lab PC ships a nightly `BASEDAT_YYYYMMDD_HHMMSS.fbk.gz` over SFTP into
`/srv/labwin_backups/incoming/`. This module:

  1. Picks the most-recent backup from incoming/.
  2. Validates it (size > 0, valid gzip magic).
  3. Decompresses to a temp `.fbk` next to it (visible to the firebird
     container via the read-only `/backups` bind-mount).
  4. Calls Firebird's Services API (`restore_database`) to replace the
     contents of `/firebird/data/BASEDAT.FDB` inside the firebird container.
  5. Invokes `sync_labwin_results` synchronously to ingest the new data.
  6. Moves the original `.fbk.gz` to `processed/` (success) or `failed/`
     (any stage error).

All paths are configurable via Django settings (defaults match the production
docker-compose layout). The class is intentionally test-friendly: each stage
is a separate method so tests can mock the firebird/sync calls without
touching real I/O.
"""

import gzip
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from django.conf import settings
from django.utils import timezone

from apps.labwin_sync.models import SyncLog

logger = logging.getLogger(__name__)


GZIP_MAGIC = b"\x1f\x8b"


class BackupImportError(Exception):
    """Base for any error that should send the backup to failed/."""


class NoBackupFound(BackupImportError):
    """incoming/ has no `.fbk.gz` files to process."""


class CorruptBackup(BackupImportError):
    """File exists but isn't a valid gzip / is empty."""


class FirebirdRestoreError(BackupImportError):
    """gbak/Services API restore call failed."""


@dataclass
class BackupImportResult:
    """Returned by `BackupImporter.run()`. Mirrors the sync-task return shape."""

    status: str  # 'completed' | 'failed' | 'skipped'
    backup_filename: Optional[str] = None
    backup_size_bytes: int = 0
    restore_duration_s: float = 0.0
    sync_result: dict = field(default_factory=dict)
    error: Optional[str] = None
    sync_log_uuid: Optional[str] = None

    def as_dict(self):
        return {
            "status": self.status,
            "backup_filename": self.backup_filename,
            "backup_size_bytes": self.backup_size_bytes,
            "restore_duration_s": round(self.restore_duration_s, 1),
            "sync_result": self.sync_result,
            "error": self.error,
            "sync_log_uuid": self.sync_log_uuid,
        }


class BackupImporter:
    """Restore the latest LabWin `.fbk.gz` and trigger a sync.

    Args:
        lab_client_id: which lab to assign synced records to (default: settings).
        incoming_dir, processed_dir, failed_dir: backup pipeline directories
            (defaults from settings).
        firebird_host, firebird_port, firebird_user, firebird_password:
            connection params for the Services API (defaults from settings).
        firebird_target_path: where the restored DB should live inside the
            firebird container (default: settings.LABWIN_FDB_DATABASE).
        firebird_backup_mount: prefix the firebird container sees for the
            host's /srv/labwin_backups (default: '/backups').
        retention_days: how long to keep files in processed/ (default: 30).

    All overrides exist for testing; production calls use no kwargs.
    """

    def __init__(
        self,
        lab_client_id: Optional[int] = None,
        incoming_dir: Optional[str] = None,
        processed_dir: Optional[str] = None,
        failed_dir: Optional[str] = None,
        firebird_host: Optional[str] = None,
        firebird_port: Optional[int] = None,
        firebird_user: Optional[str] = None,
        firebird_password: Optional[str] = None,
        firebird_target_path: Optional[str] = None,
        firebird_backup_mount: str = "/backups",
        retention_days: int = 30,
    ):
        self.lab_client_id = lab_client_id or getattr(
            settings, "LABWIN_DEFAULT_LAB_CLIENT_ID", 1
        )
        self.incoming_dir = Path(
            incoming_dir
            or getattr(
                settings,
                "LABWIN_BACKUP_INCOMING_DIR",
                "/srv/labwin_backups/incoming",
            )
        )
        self.processed_dir = Path(
            processed_dir
            or getattr(
                settings,
                "LABWIN_BACKUP_PROCESSED_DIR",
                "/srv/labwin_backups/processed",
            )
        )
        self.failed_dir = Path(
            failed_dir
            or getattr(
                settings,
                "LABWIN_BACKUP_FAILED_DIR",
                "/srv/labwin_backups/failed",
            )
        )
        self.firebird_host = firebird_host or getattr(
            settings, "LABWIN_FDB_HOST", "firebird"
        )
        self.firebird_port = int(
            firebird_port or getattr(settings, "LABWIN_FDB_PORT", 3050)
        )
        self.firebird_user = firebird_user or getattr(
            settings, "LABWIN_FDB_USER", "SYSDBA"
        )
        self.firebird_password = firebird_password or getattr(
            settings, "LABWIN_FDB_PASSWORD", ""
        )
        self.firebird_target_path = firebird_target_path or getattr(
            settings, "LABWIN_FDB_DATABASE", "/firebird/data/BASEDAT.FDB"
        )
        self.firebird_backup_mount = firebird_backup_mount.rstrip("/")
        self.retention_days = retention_days

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def run(
        self,
        explicit_file: Optional[Path] = None,
        skip_restore: bool = False,
        skip_sync: bool = False,
    ) -> BackupImportResult:
        """Execute the full pipeline.

        Args:
            explicit_file: skip discovery, restore this file instead.
            skip_restore: skip Firebird restore (assume DB already loaded).
            skip_sync: skip the sync_labwin_results call (restore only).
        """
        sync_log = SyncLog.objects.create(
            status="started",
            lab_client_id=self.lab_client_id,
            celery_task_id="",
        )
        result = BackupImportResult(status="started", sync_log_uuid=str(sync_log.pk))
        backup_path: Optional[Path] = None

        try:
            # 1. Locate
            backup_path = explicit_file or self.find_latest_backup()
            result.backup_filename = backup_path.name
            result.backup_size_bytes = backup_path.stat().st_size
            logger.info(
                "BackupImporter: selected %s (%.1f MB)",
                backup_path.name,
                result.backup_size_bytes / 1_048_576,
            )

            # 2. Validate
            self.validate_backup(backup_path)

            # 3. Restore
            if not skip_restore:
                fbk_path = self.decompress(backup_path)
                t0 = timezone.now()
                try:
                    self.restore_to_firebird(fbk_path)
                finally:
                    # Always remove the temp .fbk, even on failure
                    try:
                        fbk_path.unlink()
                    except OSError as e:
                        logger.warning("Could not delete temp .fbk %s: %s", fbk_path, e)
                result.restore_duration_s = (timezone.now() - t0).total_seconds()
                logger.info("Restore OK in %.1fs", result.restore_duration_s)

            # 4. Sync
            if not skip_sync:
                result.sync_result = self.trigger_sync()

            # 5. Move to processed/
            self.move_to_processed(backup_path)
            result.status = "completed"

        except NoBackupFound as e:
            result.status = "skipped"
            result.error = str(e)
            logger.info("BackupImporter: %s", e)

        except BackupImportError as e:
            result.status = "failed"
            result.error = f"{type(e).__name__}: {e}"
            logger.error("BackupImporter failed: %s", result.error)
            if backup_path and backup_path.exists():
                self.move_to_failed(backup_path)

        except Exception as e:
            result.status = "failed"
            result.error = f"unexpected: {type(e).__name__}: {e}"
            logger.exception("BackupImporter unexpected error")
            if backup_path and backup_path.exists():
                self.move_to_failed(backup_path)

        finally:
            sync_log.status = "completed" if result.status == "completed" else "failed"
            sync_log.completed_at = timezone.now()
            if result.error:
                sync_log.errors = [{"stage": "backup_import", "error": result.error}]
                sync_log.error_count = 1
            sync_log.save()

        return result

    # ------------------------------------------------------------------
    # Stages (each is independently testable)
    # ------------------------------------------------------------------
    def find_latest_backup(self) -> Path:
        """Return the most-recently-modified `.fbk.gz` in incoming/."""
        if not self.incoming_dir.is_dir():
            raise NoBackupFound(f"incoming dir does not exist: {self.incoming_dir}")
        candidates = sorted(
            self.incoming_dir.glob("*.fbk.gz"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        # Skip in-progress uploads (the lab script renames .uploading→final on
        # completion, so anything ending .uploading is partial)
        candidates = [p for p in candidates if not p.name.endswith(".uploading")]
        if not candidates:
            raise NoBackupFound(f"No .fbk.gz files in {self.incoming_dir}")
        return candidates[0]

    def validate_backup(self, path: Path) -> None:
        """Sanity-check the .fbk.gz before passing it to gbak."""
        size = path.stat().st_size
        if size == 0:
            raise CorruptBackup(f"{path.name} is empty")
        if size < 1024:
            raise CorruptBackup(f"{path.name} is suspiciously small ({size} bytes)")
        with open(path, "rb") as f:
            magic = f.read(2)
        if magic != GZIP_MAGIC:
            raise CorruptBackup(f"{path.name} is not gzip (magic: {magic!r})")

    def decompress(self, gz_path: Path) -> Path:
        """Decompress a `.fbk.gz` to a sibling `.fbk` (for firebird to read).

        We write next to the source so the firebird container's /backups
        bind-mount can see the .fbk file at the same relative path.
        """
        fbk_path = gz_path.with_suffix("")  # strip .gz → leaves .fbk
        # Use a temp suffix so a partial decompression doesn't get picked up
        # by find_latest_backup or the firebird restore
        tmp_path = fbk_path.with_name(fbk_path.name + ".tmp")
        logger.info("Decompressing %s → %s", gz_path.name, fbk_path.name)
        with gzip.open(gz_path, "rb") as src, open(tmp_path, "wb") as dst:
            shutil.copyfileobj(src, dst, length=16 * 1024 * 1024)
        tmp_path.rename(fbk_path)
        return fbk_path

    def restore_to_firebird(self, fbk_path: Path) -> None:
        """Restore a `.fbk` to the firebird container via Services API.

        The firebird container sees `fbk_path` (which is on the host under
        `/srv/labwin_backups/...`) as `/backups/...` because of the bind
        mount in docker-compose.prod.yml.
        """
        # Translate host path → container path
        try:
            relative = fbk_path.relative_to(
                self.incoming_dir.parent
            )  # e.g. Path('incoming/foo.fbk')
        except ValueError as e:
            raise FirebirdRestoreError(
                f"fbk path {fbk_path} not under {self.incoming_dir.parent}"
            ) from e
        backup_path_in_container = f"{self.firebird_backup_mount}/{relative}"

        try:
            from firebirdsql import services
        except ImportError as e:
            raise FirebirdRestoreError(
                "firebirdsql.services not importable — check passlib install"
            ) from e

        logger.info(
            "Restore: gbak -r %s → %s (Services API on %s:%s)",
            backup_path_in_container,
            self.firebird_target_path,
            self.firebird_host,
            self.firebird_port,
        )
        try:
            svc = services.connect(
                host=self.firebird_host,
                port=self.firebird_port,
                user=self.firebird_user,
                password=self.firebird_password,
            )
        except Exception as e:
            raise FirebirdRestoreError(
                f"could not connect to firebird Services API: {e}"
            ) from e

        try:
            # Positional args per firebirdsql 1.4.5 signature:
            #   restore_database(restore_filename, database_name, replace=False, ...)
            # 'replace=True' overwrites the existing /firebird/data/BASEDAT.FDB.
            svc.restore_database(
                backup_path_in_container,
                self.firebird_target_path,
                replace=True,
            )
        except Exception as e:
            raise FirebirdRestoreError(f"restore_database failed: {e}") from e
        finally:
            try:
                svc.close()
            except Exception:
                pass

    def trigger_sync(self) -> dict:
        """Run sync_labwin_results synchronously and return its result dict."""
        # Imported here to avoid circular import at module load
        from apps.labwin_sync.tasks import sync_labwin_results

        logger.info("Triggering sync_labwin_results (synchronous)")
        # Calling .run() / direct invocation runs synchronously in this process.
        # Pass full_sync=False so it uses the cursor.
        return sync_labwin_results(lab_client_id=self.lab_client_id, full_sync=False)

    def move_to_processed(self, path: Path) -> None:
        """Atomic move into processed/ with a timestamp suffix."""
        self._move_with_timestamp(path, self.processed_dir)
        # Opportunistically rotate old files
        try:
            self._rotate_processed()
        except Exception as e:
            logger.warning("Rotation of processed/ failed (non-fatal): %s", e)

    def move_to_failed(self, path: Path) -> None:
        """Move a problematic backup to failed/ for forensics."""
        try:
            self._move_with_timestamp(path, self.failed_dir)
        except Exception as e:
            logger.error("Could not move %s to failed/: %s", path.name, e)

    def _move_with_timestamp(self, path: Path, target_dir: Path) -> None:
        target_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%dT%H%M%S")
        # Insert timestamp before the FULL extension chain (.fbk.gz, not just .gz)
        # so the result still globs as *.fbk.gz
        suffixes = "".join(path.suffixes)  # e.g. ".fbk.gz"
        base = path.name[: -len(suffixes)] if suffixes else path.name
        target = target_dir / f"{base}__{ts}{suffixes}"
        # Use shutil.move so it works across filesystems if needed (it's all
        # one filesystem in production but tests may use tmpdirs)
        shutil.move(str(path), str(target))
        logger.info("Moved %s → %s", path.name, target)

    def _rotate_processed(self) -> int:
        """Delete files in processed/ older than retention_days. Returns count."""
        if not self.processed_dir.is_dir():
            return 0
        cutoff = datetime.now() - timedelta(days=self.retention_days)
        cutoff_ts = cutoff.timestamp()
        deleted = 0
        for path in self.processed_dir.glob("*"):
            if path.is_file() and path.stat().st_mtime < cutoff_ts:
                try:
                    path.unlink()
                    deleted += 1
                except OSError as e:
                    logger.warning("Could not delete %s: %s", path, e)
        if deleted:
            logger.info(
                "Rotated %d files older than %d days from processed/",
                deleted,
                self.retention_days,
            )
        return deleted
