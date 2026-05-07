"""
LabControl - PDF results uploader
=================================
Watches LabWin's PDF export folder and uploads new PDFs to the LabControl
VPS via passive FTP. Deletes each file locally only after a successful upload.

Designed to be run by Windows Task Scheduler every 5 minutes.

Why this exists: LabWin's built-in FTP plugin only supports active mode,
and active FTP through the lab's NAT is unreliable. This script uses
ftplib in passive mode, which works consistently.

Uso:
    python upload_pdfs.py              # Normal run
    python upload_pdfs.py --dry-run    # No upload, no delete - just list

Config:
    Edit the CONFIG block below if paths or credentials change.
"""

import argparse
import ftplib
import logging
import sys
from datetime import datetime
from pathlib import Path

# ============================================================================
# CONFIG - editar aqui si cambian rutas o credenciales
# ============================================================================

# LabWin's PDF export folder
PDF_DIR = Path(r"C:\sistema\PDFlabwin")

# VPS FTP
VPS_HOST = "72.60.137.226"
VPS_PORT = 21
VPS_USER = "labwin_ftp"
VPS_PASSWORD = "LabWinFTP2026!"
VPS_REMOTE_DIR = "/"  # Lab user is chrooted; "/" is /home/labwin_ftp/

# Connection timeouts (seconds)
CONNECT_TIMEOUT = 30
TRANSFER_TIMEOUT = 600  # 10 minutes per file should be plenty

# Skip files smaller than this (bytes) - LabWin sometimes leaves 0-byte
# placeholders mid-export, don't upload those
MIN_FILE_SIZE = 1

# Logging
LOG_FILE = Path(r"C:\labcontrol_backup\pdf_upload.log")

# ============================================================================
# Setup logging
# ============================================================================
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("pdf_upload")


def find_pdfs():
    """Return list of .pdf files in PDF_DIR, oldest first."""
    if not PDF_DIR.exists():
        log.warning("PDF directory does not exist: %s", PDF_DIR)
        return []
    pdfs = sorted(PDF_DIR.glob("*.pdf"), key=lambda p: p.stat().st_mtime)
    return pdfs


def upload_one(ftp, pdf_path):
    """Upload a single PDF. Returns True on success."""
    size = pdf_path.stat().st_size
    if size < MIN_FILE_SIZE:
        log.warning("skipping %s (size=%d, too small)", pdf_path.name, size)
        return False

    # Upload to a temp name first, rename on completion. This way if the
    # transfer is interrupted, the connector won't see a partial file.
    tmp_name = pdf_path.name + ".uploading"
    final_name = pdf_path.name

    log.info("uploading %s (%d bytes)", final_name, size)
    start = datetime.now()

    try:
        with open(pdf_path, "rb") as f:
            ftp.storbinary(f"STOR {tmp_name}", f)
        ftp.rename(tmp_name, final_name)
    except Exception as e:
        # Try to clean up the .uploading file so it doesn't accumulate
        try:
            ftp.delete(tmp_name)
        except Exception:
            pass
        log.error("upload FAILED for %s: %s", final_name, e)
        return False

    elapsed = (datetime.now() - start).total_seconds()
    speed_kb = (size / 1024 / elapsed) if elapsed > 0 else 0
    log.info("upload OK - %s (%.1f KB/s)", final_name, speed_kb)
    return True


def main(dry_run=False):
    start = datetime.now()
    log.info("=" * 60)
    log.info("PDF upload run started %s (dry_run=%s)", start.isoformat(), dry_run)

    pdfs = find_pdfs()
    if not pdfs:
        log.info("no PDFs to upload")
        return 0

    log.info("found %d PDF(s) in %s", len(pdfs), PDF_DIR)

    if dry_run:
        for p in pdfs:
            log.info("  would upload: %s (%d bytes)", p.name, p.stat().st_size)
        return 0

    # Connect once, upload all PDFs in one session
    log.info("connecting to %s:%d as %s", VPS_HOST, VPS_PORT, VPS_USER)
    try:
        ftp = ftplib.FTP()
        ftp.connect(VPS_HOST, VPS_PORT, timeout=CONNECT_TIMEOUT)
        ftp.login(VPS_USER, VPS_PASSWORD)
        ftp.set_pasv(True)  # CRITICAL: passive mode
        ftp.cwd(VPS_REMOTE_DIR)
        log.info("connected, pwd=%s", ftp.pwd())
    except Exception as e:
        log.exception("FTP connection FAILED: %s", e)
        return 1

    uploaded = 0
    failed = 0
    try:
        for pdf in pdfs:
            ok = upload_one(ftp, pdf)
            if ok:
                try:
                    pdf.unlink()
                    log.info("deleted local %s", pdf.name)
                    uploaded += 1
                except Exception as e:
                    log.error(
                        "upload OK but local delete FAILED for %s: %s", pdf.name, e
                    )
                    # Don't count as uploaded since we couldn't clean up;
                    # next run will try again (idempotent on server side via temp-rename).
                    failed += 1
            else:
                failed += 1
    finally:
        try:
            ftp.quit()
        except Exception:
            pass

    elapsed = (datetime.now() - start).total_seconds()
    log.info("done - uploaded=%d failed=%d duration=%.1fs", uploaded, failed, elapsed)
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LabControl PDF uploader")
    parser.add_argument(
        "--dry-run", action="store_true", help="List only, no upload, no delete"
    )
    args = parser.parse_args()
    sys.exit(main(dry_run=args.dry_run))
