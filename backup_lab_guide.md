# LabControl — LabWin Backup Upload Guide (Lab Team)

This guide explains how to install and schedule the nightly LabWin backup uploader on the laboratory PC. Once configured, the PC will automatically create a Firebird backup of `BASEDAT.FDB`, compress it, and upload it via SFTP to the LabControl VPS every night at 02:00 AM.

---

## 1. The script — `upload_backup.py`

Save this file as `C:\labcontrol_backup\upload_backup.py` on the lab PC.

```python
"""
LabControl — LabWin nightly backup uploader.

Runs on the laboratory PC via Windows Task Scheduler (02:00 AM).
  1. Uses gbak to create a consistent Firebird backup of BASEDAT.FDB
  2. Compresses it with gzip
  3. Uploads via SFTP to the LabControl VPS (key-based auth)
  4. Rotates local backups (keeps the last N)

Exit codes:
  0  success
  1  config / validation error
  2  gbak failed
  3  gzip failed
  4  SFTP upload failed
  5  SSH host key mismatch

Usage:
  python upload_backup.py                  # normal run
  python upload_backup.py --dry-run        # test SSH + config without uploading
  python upload_backup.py --config PATH    # override config file path
  python upload_backup.py --keep-local     # skip local rotation
"""

import argparse
import configparser
import gzip
import logging
import logging.handlers
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import paramiko
except ImportError:
    sys.stderr.write("ERROR: paramiko is not installed. Run: pip install paramiko\n")
    sys.exit(1)


EXIT_OK = 0
EXIT_CONFIG = 1
EXIT_GBAK = 2
EXIT_GZIP = 3
EXIT_SFTP = 4
EXIT_HOSTKEY = 5


def load_config(path: Path) -> configparser.ConfigParser:
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")
    cfg = configparser.ConfigParser()
    cfg.read(path, encoding="utf-8")
    required = {
        "firebird": ["gbak_exe", "database", "user", "password"],
        "local": ["backup_dir", "log_file", "keep_last"],
        "sftp": ["host", "port", "username", "private_key", "known_hosts",
                 "remote_dir", "connect_timeout", "transfer_timeout"],
    }
    for section, keys in required.items():
        if section not in cfg:
            raise ValueError(f"Missing [{section}] section in config")
        for key in keys:
            if not cfg[section].get(key):
                raise ValueError(f"Missing {section}.{key} in config")
    return cfg


def setup_logging(log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    fh = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)

    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    root.addHandler(sh)


def run_gbak(cfg, fbk_path: Path) -> None:
    gbak = cfg["firebird"]["gbak_exe"]
    db = cfg["firebird"]["database"]
    user = cfg["firebird"]["user"]
    password = cfg["firebird"]["password"]

    if not Path(gbak).is_file():
        raise FileNotFoundError(f"gbak.exe not found at {gbak}")
    if not Path(db).is_file():
        raise FileNotFoundError(f"Firebird database not found at {db}")

    cmd = [gbak, "-b", "-g", "-user", user, "-password", password, db, str(fbk_path)]
    logging.info("Running gbak → %s", fbk_path.name)
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-10:]
        logging.error("gbak failed (rc=%s): %s", proc.returncode, " | ".join(tail))
        raise RuntimeError("gbak failed")
    logging.info("gbak OK in %.1fs (size=%.1f MB)",
                 time.time() - t0, fbk_path.stat().st_size / 1_048_576)


def gzip_file(src: Path, dst: Path) -> None:
    logging.info("Compressing → %s", dst.name)
    t0 = time.time()
    with open(src, "rb") as f_in, gzip.open(dst, "wb", compresslevel=6) as f_out:
        shutil.copyfileobj(f_in, f_out, length=1024 * 1024)
    src.unlink()
    logging.info("gzip OK in %.1fs (size=%.1f MB)",
                 time.time() - t0, dst.stat().st_size / 1_048_576)


def sftp_upload(cfg, local_path: Path) -> None:
    host = cfg["sftp"]["host"]
    port = int(cfg["sftp"]["port"])
    username = cfg["sftp"]["username"]
    key_path = cfg["sftp"]["private_key"]
    known_hosts = cfg["sftp"]["known_hosts"]
    remote_dir = cfg["sftp"]["remote_dir"].rstrip("/")
    connect_timeout = int(cfg["sftp"]["connect_timeout"])
    transfer_timeout = int(cfg["sftp"]["transfer_timeout"])

    if not Path(key_path).is_file():
        raise FileNotFoundError(f"SSH private key not found at {key_path}")
    if not Path(known_hosts).is_file():
        raise FileNotFoundError(f"known_hosts file not found at {known_hosts}")

    client = paramiko.SSHClient()
    client.load_host_keys(known_hosts)
    client.set_missing_host_key_policy(paramiko.RejectPolicy())

    logging.info("Connecting to %s@%s:%s", username, host, port)
    t0 = time.time()
    try:
        client.connect(
            hostname=host, port=port, username=username,
            key_filename=key_path,
            timeout=connect_timeout,
            banner_timeout=connect_timeout,
            auth_timeout=connect_timeout,
            allow_agent=False, look_for_keys=False,
        )
    except paramiko.BadHostKeyException as e:
        logging.error("Host key mismatch: %s", e)
        raise SystemExit(EXIT_HOSTKEY)

    try:
        sftp = client.open_sftp()
        sftp.get_channel().settimeout(transfer_timeout)

        remote_final = f"{remote_dir}/{local_path.name}"
        remote_partial = remote_final + ".part"

        logging.info("Uploading %s (%.1f MB) → %s",
                     local_path.name, local_path.stat().st_size / 1_048_576, remote_final)
        sftp.put(str(local_path), remote_partial)
        try:
            sftp.remove(remote_final)
        except IOError:
            pass
        sftp.rename(remote_partial, remote_final)

        local_size = local_path.stat().st_size
        remote_size = sftp.stat(remote_final).st_size
        if local_size != remote_size:
            logging.error("Size mismatch: local=%s remote=%s", local_size, remote_size)
            raise RuntimeError("size mismatch after upload")

        sftp.close()
        logging.info("SFTP upload OK in %.1fs", time.time() - t0)
    finally:
        client.close()


def rotate_local(backup_dir: Path, keep_last: int) -> None:
    files = sorted(
        backup_dir.glob("BASEDAT_*.fbk.gz"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in files[keep_last:]:
        logging.info("Rotating out old backup: %s", old.name)
        try:
            old.unlink()
        except OSError as e:
            logging.warning("Could not delete %s: %s", old, e)


def dry_run(cfg) -> int:
    logging.info("DRY RUN — validating config and SSH connectivity")
    for p in [cfg["firebird"]["gbak_exe"], cfg["firebird"]["database"],
              cfg["sftp"]["private_key"], cfg["sftp"]["known_hosts"]]:
        if not Path(p).is_file():
            logging.error("Path not found: %s", p)
            return EXIT_CONFIG
        logging.info("OK: %s", p)

    client = paramiko.SSHClient()
    client.load_host_keys(cfg["sftp"]["known_hosts"])
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        client.connect(
            hostname=cfg["sftp"]["host"],
            port=int(cfg["sftp"]["port"]),
            username=cfg["sftp"]["username"],
            key_filename=cfg["sftp"]["private_key"],
            timeout=int(cfg["sftp"]["connect_timeout"]),
            allow_agent=False, look_for_keys=False,
        )
        sftp = client.open_sftp()
        listing = sftp.listdir(cfg["sftp"]["remote_dir"])
        logging.info("SFTP listdir OK — %d file(s) currently in remote dir", len(listing))
        sftp.close()
    except paramiko.BadHostKeyException as e:
        logging.error("Host key mismatch: %s", e)
        return EXIT_HOSTKEY
    except (paramiko.SSHException, socket.error, OSError) as e:
        logging.error("SSH/SFTP error: %s", e)
        return EXIT_SFTP
    finally:
        client.close()

    logging.info("DRY RUN OK")
    return EXIT_OK


def main() -> int:
    parser = argparse.ArgumentParser(description="LabWin backup uploader")
    parser.add_argument("--config", default=None,
                        help="Path to config file (default: upload_backup.config.ini next to script)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate config + SSH without running gbak or uploading")
    parser.add_argument("--keep-local", action="store_true",
                        help="Skip local rotation (keep all backups)")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    config_path = Path(args.config) if args.config else script_dir / "upload_backup.config.ini"

    try:
        cfg = load_config(config_path)
    except (FileNotFoundError, ValueError) as e:
        sys.stderr.write(f"CONFIG ERROR: {e}\n")
        return EXIT_CONFIG

    setup_logging(Path(cfg["local"]["log_file"]))
    logging.info("=" * 60)
    logging.info("upload_backup.py start (config=%s)", config_path)

    if args.dry_run:
        return dry_run(cfg)

    backup_dir = Path(cfg["local"]["backup_dir"])
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    fbk = backup_dir / f"BASEDAT_{stamp}.fbk"
    gz = backup_dir / f"BASEDAT_{stamp}.fbk.gz"

    total_t0 = time.time()
    try:
        run_gbak(cfg, fbk)
    except Exception as e:
        logging.error("gbak stage failed: %s", e)
        return EXIT_GBAK

    try:
        gzip_file(fbk, gz)
    except Exception as e:
        logging.error("gzip stage failed: %s", e)
        return EXIT_GZIP

    try:
        sftp_upload(cfg, gz)
    except SystemExit as e:
        return int(e.code)
    except (paramiko.SSHException, socket.error, OSError, RuntimeError) as e:
        logging.error("SFTP stage failed: %s", e)
        return EXIT_SFTP

    if not args.keep_local:
        try:
            rotate_local(backup_dir, int(cfg["local"]["keep_last"]))
        except Exception as e:
            logging.warning("Rotation failed (non-fatal): %s", e)

    logging.info("DONE in %.1fs total", time.time() - total_t0)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
```

---

## 2. Config file — `upload_backup.config.ini`

Save this as `C:\labcontrol_backup\upload_backup.config.ini` on the lab PC. **Fill in the real SYSDBA password before running** (see "Where to get the password" below) and confirm the paths match the lab's install.

```ini
[firebird]
gbak_exe = C:\Program Files\Firebird\Firebird_2_5\bin\gbak.exe
database = C:\sistema\LabWin4\BASEDAT.FDB
user = SYSDBA
password = REPLACE_WITH_REAL_SYSDBA_PASSWORD

[local]
backup_dir = C:\labcontrol_backup\out
log_file = C:\labcontrol_backup\upload.log
keep_last = 7

[sftp]
host = 72.60.137.226
port = 22
username = backup_user
private_key = C:\labcontrol_backup\keys\backup_user_ed25519
known_hosts = C:\labcontrol_backup\keys\known_hosts
remote_dir = /incoming
connect_timeout = 30
transfer_timeout = 3600
```

> **Note:** `remote_dir = /incoming` (no `/srv/labwin_backups/` prefix). The VPS-side `backup_user` is chroot'd to `/srv/labwin_backups/`, so from the SFTP session's perspective `/incoming` *is* `/srv/labwin_backups/incoming`.

### Where to get the password

The `[firebird] password` value is the **SYSDBA password for the lab's LabWin Firebird install**. It is **not committed to this repo or this guide** for security reasons. Get it from one of these sources, in order of preference:

1. **Team 1Password vault** → entry name **"LabControl LabWin SYSDBA"** (mirror of what's deployed on the lab PC and the VPS)
2. **Repository env template** → `.env.production.template`, keys `LABWIN_FDB_PASSWORD` / `FIREBIRD_SYSDBA_PASSWORD` (these are the same secret as the lab PC's `[firebird] password` — the VPS uses it to read the restored backup, the lab PC uses it to create the backup)
3. **Lab admin** — if Firebird was installed long before this pipeline existed and the password was never rotated, ask the lab admin directly. **In that case, rotate it now** and update sources 1 and 2.

> ⚠️ **If the password is still the Firebird default (`masterkey`)**: rotate it before going to production. The default is publicly known and would let anyone with network access to Firebird read or modify the LabWin database. Procedure: stop the LabWin Firebird service → `gsec -user SYSDBA -password masterkey -mo SYSDBA -pw <new>` → restart service → update 1Password + the lab PC config + the VPS `.env.production`.

### Permissions on the config file

After filling in the password, restrict NTFS permissions so only the scheduled-task user can read it:

```
icacls C:\labcontrol_backup\upload_backup.config.ini /inheritance:r
icacls C:\labcontrol_backup\upload_backup.config.ini /grant:r "%USERNAME%:R"
icacls C:\labcontrol_backup\upload_backup.config.ini /remove "BUILTIN\Users"
icacls C:\labcontrol_backup\upload_backup.config.ini /remove "Everyone"
```

---

## 3. Setup guide for the lab team

### Prerequisites

- Windows 10 or 11 on the LabWin PC
- The LabWin Firebird 2.5 service already installed (so `gbak.exe` exists)
- Administrator access to the PC (needed once to install Python and create a scheduled task)
- The VPS team has already created the `backup_user` account — ask them for:
  - The **SSH private key file** for `backup_user`
  - A **known_hosts** file containing the VPS's SSH host key fingerprint

### Step 1 — Install Python

1. Download Python 3.11 (or newer) from https://www.python.org/downloads/windows/
2. During install, **check "Add Python to PATH"**
3. Open a Command Prompt (`cmd.exe`) and verify:
   ```
   python --version
   ```

### Step 2 — Install paramiko

In the same Command Prompt:

```
pip install paramiko
```

### Step 3 — Create the folder layout

```
C:\labcontrol_backup\
├── upload_backup.py                    ← the script from section 1
├── upload_backup.config.ini            ← the config from section 2 (edit it)
├── upload.log                          ← created automatically on first run
├── out\                                ← created automatically (local backups)
└── keys\
    ├── backup_user_ed25519             ← SSH private key (from the VPS team)
    └── known_hosts                     ← VPS host key (from the VPS team)
```

Set restrictive permissions on the `keys\` folder so only the account running the scheduled task can read it:

```
icacls C:\labcontrol_backup\keys /inheritance:r
icacls C:\labcontrol_backup\keys /grant:r "%USERNAME%:(OI)(CI)F"
```

### Step 4 — Edit the config file

Open `C:\labcontrol_backup\upload_backup.config.ini` in Notepad and update:

- `[firebird] password` — the real SYSDBA password (see "Where to get the password" in section 2; **do not** leave the placeholder `REPLACE_WITH_REAL_SYSDBA_PASSWORD`)
- `[firebird] gbak_exe` / `database` — confirm paths match the local install

After saving, run the `icacls` commands from section 2 ("Permissions on the config file") so the password isn't world-readable on the PC.

### Step 5 — Test from the terminal

Open a Command Prompt **as the same Windows user that will run the scheduled task**, then:

```
cd C:\labcontrol_backup
python upload_backup.py --dry-run
```

You should see:

```
... DRY RUN — validating config and SSH connectivity
... OK: C:\Program Files\Firebird\Firebird_2_5\bin\gbak.exe
... OK: C:\sistema\LabWin4\BASEDAT.FDB
... OK: C:\labcontrol_backup\keys\backup_user_ed25519
... OK: C:\labcontrol_backup\keys\known_hosts
... Connecting to backup_user@72.60.137.226:22
... SFTP listdir OK — 0 file(s) currently in remote dir
... DRY RUN OK
```

If that works, run a real upload once to confirm end-to-end:

```
python upload_backup.py
```

Check `C:\labcontrol_backup\upload.log` for the summary, and ask the VPS team to confirm `BASEDAT_YYYYMMDD.fbk.gz` shows up in `/srv/labwin_backups/incoming/`.

**If something fails**, the exit code tells you which stage:

| Exit code | Meaning | What to check |
|---|---|---|
| 1 | Config error | Paths / missing fields in the `.ini` |
| 2 | gbak failed | SYSDBA password, gbak path, DB path, disk space |
| 3 | gzip failed | Disk space in `backup_dir` |
| 4 | SFTP failed | VPS reachable? firewall? key permissions? |
| 5 | Host key mismatch | `known_hosts` file is wrong or VPS was rebuilt |

### Step 6 — Schedule it with Task Scheduler

1. Press **Win + R**, type `taskschd.msc`, press Enter
2. Right panel → **Create Task...** (not "Create Basic Task" — we need the advanced options)
3. **General** tab:
   - Name: `LabControl backup upload`
   - Select **"Run whether user is logged on or not"**
   - Select **"Run with highest privileges"**
   - Configure for: **Windows 10**
4. **Triggers** tab → **New...**:
   - Begin the task: **On a schedule**
   - Settings: **Daily**
   - Start: today's date, time `2:00:00 AM`
   - Recur every: `1` days
   - Check **"Enabled"**
5. **Actions** tab → **New...**:
   - Action: **Start a program**
   - Program/script: `python`
     *(or full path, e.g. `C:\Python311\python.exe`, if `python` isn't on PATH for the service account)*
   - Add arguments: `upload_backup.py`
   - Start in: `C:\labcontrol_backup`
6. **Conditions** tab:
   - Uncheck **"Start the task only if the computer is on AC power"** (so it runs even on a UPS)
   - Check **"Wake the computer to run this task"** if the PC is normally suspended at night
7. **Settings** tab:
   - Check **"Allow task to be run on demand"**
   - Check **"If the task fails, restart every: 15 minutes, up to 3 times"**
   - **"Stop the task if it runs longer than: 2 hours"**
8. Click **OK** — Windows will ask for the password of the user that owns the task.

### Step 7 — Test the scheduled task

In Task Scheduler, right-click **LabControl backup upload** → **Run**. Wait a couple of minutes, then:

- Check `C:\labcontrol_backup\upload.log` — should show a full successful run
- Check Task Scheduler's **History** tab — "Last Run Result" should be `0x0` (success)

If the manual test works, the 02:00 AM schedule will work too.

### Day-to-day monitoring

- **Log**: `C:\labcontrol_backup\upload.log` (rotates automatically, keeps 5 × 2 MB)
- **Task history**: Task Scheduler → LabControl backup upload → History tab. Any non-zero "Last Run Result" = something broke; check the log.
- **Local backups**: `C:\labcontrol_backup\out\` always holds the last 7 `.fbk.gz` files as a local fallback.
- **To pause** (e.g. while troubleshooting): Task Scheduler → right-click the task → **Disable**.
- **To run manually** any time: Task Scheduler → right-click → **Run**, or from cmd: `cd C:\labcontrol_backup && python upload_backup.py`.

That's it — once set up, it runs unattended every night at 02:00.
