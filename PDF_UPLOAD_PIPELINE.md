# LabWin PDF Upload Pipeline

**Status:** ✅ In production since 2026-05-07. LabWin exports PDFs locally on the lab PC at 02:00; our `upload_pdfs.py` script (running on the lab PC via Task Scheduler at 02:15) pushes them to the VPS via passive FTP. The backend `fetch_ftp_pdfs` task then pulls them and attaches each to its matching `Study`.
**Owner:** Development Team
**Última actualización:** 2026-05-08

---

## 🎯 Why this exists

The lab generates one PDF per protocol from LabWin (`{NUMERO}-{DNI}-{NAME}.pdf`) and the LabControl portal needs to attach each PDF to its matching `Study`. The original design had LabWin's built-in FTP plugin push the files directly to vsftpd on the VPS. **It never worked reliably** — full debug session 2026-05-07 confirmed the failure mode and produced the current solution.

This doc is the bridge between:
- `BACKEND.md` §FTP PDF Fetch — describes the backend `fetch_ftp_pdfs` task that consumes the uploaded PDFs.
- `DEPLOYMENT.md` §FTP Server Configuration — describes the vsftpd server-side config.
- `deployment/lab_workstation/upload_pdfs.py` — the script that runs on the lab PC.

---

## 🧨 Why LabWin's FTP plugin was abandoned

**Symptom:** for weeks, PDFs would queue up in LabWin's outbox without arriving on the VPS, or arrive sporadically. Server-side fixes (CT helper rules, `port_enable=NO`, `allow_writeable_chroot`, chroot path tweaks) all failed.

**Root cause** (verified 2026-05-07):

1. LabWin's FTP plugin is **hardcoded to active mode**. The "passive" toggle in the UI is decorative — uninstalling and reinstalling the plugin did not change behavior.
2. The lab's NAT/router does not handle the FTP application-layer gateway correctly.
3. In active FTP, after the client sends `PORT 181,116,56,170,X,Y`, the server (vsftpd) opens a TCP connection back to `181.116.56.170:port`. That SYN went `[UNREPLIED]` in the VPS's conntrack — i.e. the lab's NAT silently dropped the return SYN.
4. There is **no fix for this on our side**. The lab would have to expose a proper FTP-ALG-aware router (or just open the data ports inbound), which they're not going to do.

**Decision:** stop fighting it. Replace the LabWin FTP plugin with an outbound-only push from the lab PC, using passive mode so the client opens both connections.

---

## 🏗️ Current architecture

```
┌─────────────── PC LAB (Windows, outbound-only) ──────────────────┐
│                                                                  │
│  LabWin                                                          │
│    └─ 02:00 — exports the day's PDFs to C:\sistema\PDFlabwin\    │
│                                                                  │
│  Task Scheduler — daily 02:15                                    │
│    └─ python upload_pdfs.py                                      │
│         1. List *.pdf in C:\sistema\PDFlabwin\                   │
│         2. ftp.set_pasv(True) → connect labwin_ftp@VPS           │
│         3. STOR each as {name}.pdf.uploading                     │
│         4. RNFR/RNTO → {name}.pdf  (atomic on the server)        │
│         5. Delete the local file on success                      │
│         6. Log to C:\labcontrol_backup\pdf_upload.log            │
└────────────────────────┬─────────────────────────────────────────┘
                         │
                         │ FTP :21 outbound, passive mode
                         │ labwin_ftp@vps (chrooted to /home/labwin_ftp)
                         ▼
┌──────────────────────── VPS Hostinger (72.60.137.226) ────────────┐
│                                                                   │
│  vsftpd                                                           │
│    └─ /home/labwin_ftp/  ← chroot, also LABWIN_FTP_DIRECTORY=/    │
│                                                                   │
│  docker stack: web + celery_worker reach vsftpd via               │
│                host.docker.internal:21                            │
│                                                                   │
│  Celery Beat — every 30 min                                       │
│    └─ apps.labwin_sync.tasks.fetch_ftp_pdfs                       │
│         1. ftp.list_pdf_files()  → ["220197-39592918-SIRI...pdf"] │
│         2. parse NUMERO from filename (first dash-separated seg)  │
│         3. find Study by sample_id=NUMERO                         │
│         4. download + save to study.results_file                  │
│         5. (PDF stays on FTP for audit; cleanup task removes      │
│             once the Study has results_file)                      │
└───────────────────────────────────────────────────────────────────┘
```

---

## 🔧 Components

### 1. Lab PC — `upload_pdfs.py`

**Source of truth in repo:** [`deployment/lab_workstation/upload_pdfs.py`](./deployment/lab_workstation/upload_pdfs.py). The copy on the lab PC has the real `LABWIN_FTP_PASSWORD` filled in; the repo copy uses a placeholder. We do not redeploy this script unless behavior needs to change — the lab is running it autonomously.

**Behavior:**
- Watches `C:\sistema\PDFlabwin\` for `*.pdf` files (LabWin's export folder).
- One FTP session per run, uploads all PDFs in order of mtime (oldest first).
- Atomic `name.pdf.uploading` → `RNTO name.pdf` so the connector never sees half-written files.
- Deletes locally only after server-side rename succeeds.
- Logs to `C:\labcontrol_backup\pdf_upload.log` (shared with `upload_backup.py`).
- Skips zero-byte files (LabWin sometimes leaves placeholders during export).

**Task Scheduler config:**
- Trigger: daily at 02:15 (gives LabWin's 02:00 export 15 minutes to finish writing).
- Action: `C:\Python312\python.exe C:\labcontrol_backup\upload_pdfs.py`
- Run whether user is logged on or not, with highest privileges.

**Why 02:15 specifically:** LabWin runs its own export at 02:00 that drops the day's PDFs into `C:\sistema\PDFlabwin\`. Our script needs to fire after that finishes, but well before the VPS Beat job at 04:00 ART that runs `sync_labwin_results` + `fetch_ftp_pdfs`. 15 minutes is plenty of headroom for the export and the upload (typical: a few dozen PDFs in ~2s).

**`--dry-run`** lists the PDFs that would be uploaded without uploading or deleting anything.

### 2. VPS — vsftpd

The vsftpd server-side config is documented in [`DEPLOYMENT.md`](./DEPLOYMENT.md) §FTP Server Configuration. Key facts:

| Setting | Value |
|---|---|
| Host | `72.60.137.226` |
| Port | `21` (control), `30000-30100` (passive data) |
| User | `labwin_ftp` (chrooted to `/home/labwin_ftp/`) |
| Password | 1Password → "LabControl LabWin FTP user" |
| Mode | **Passive only** — the lab PC's NAT cannot do active FTP (see §Why LabWin's FTP plugin was abandoned) |

### 3. Backend — `fetch_ftp_pdfs`

Already documented in [`BACKEND.md`](./BACKEND.md) §FTP PDF Fetch. Highlights:

- Filename format: `{NUMERO}-{DNI}-{NAME}.pdf`. Parser takes the first dash-separated segment as `NUMERO` (matches `Study.sample_id`).
- Files whose NUMERO is **not** in the imported-study window (90 days) stay on FTP and re-attach automatically once their Study lands. Currently ~46 of 59 PDFs sit unprocessed in this state — known and accepted (see §Open follow-ups).
- `cleanup_ftp_pdfs` removes PDFs from FTP once their Study has `results_file`.
- `LABWIN_FTP_DIRECTORY=/` because the chroot root *is* the directory where `upload_pdfs.py` writes (no `/results` subdir anymore — old `LABWIN_FTP_DIRECTORY=/results` is decommissioned).

---

## 📜 End-to-end validation (2026-05-07)

First production run of the new pipeline:

```
[lab PC] 2026-05-07 21:14:02 [INFO] PDF upload run started
[lab PC] 2026-05-07 21:14:02 [INFO] found 59 PDF(s) in C:\sistema\PDFlabwin
[lab PC] 2026-05-07 21:14:02 [INFO] connecting to 72.60.137.226:21 as labwin_ftp
[lab PC] 2026-05-07 21:14:03 [INFO] connected, pwd=/
[lab PC] 2026-05-07 21:14:03 [INFO] uploading 220197-39592918-SIRI,FRANCO.pdf (XXXXX bytes)
   ... (59 uploads in ~2 s) ...
[lab PC] 2026-05-07 21:14:05 [INFO] done - uploaded=59 failed=0 duration=2.0s
```

Backend `fetch_ftp_pdfs` run shortly after:
- `files_found=59`, `files_matched=13`, `files_attached=13`, `files_skipped=46`, `error_count=0`.
- 46 skipped because their NUMERO is outside the imported-study 90-day window (parent Study not yet in Postgres). Those PDFs stay on FTP.

---

## 🚨 Failure modes & debugging

| Symptom | First check | Fix |
|---|---|---|
| "PDFs stopped showing up in the portal" | `C:\labcontrol_backup\pdf_upload.log` on the lab PC — is the script running and succeeding? | If the log shows successful uploads but the portal doesn't see them, the issue is on the backend (see next row). |
| Script logs successful uploads, portal doesn't show them | `docker exec labcontrol_celery_worker python manage.py fetch_ftp_pdfs` — check `files_skipped` count | High skipped = NUMEROs outside the 90-day window, expected. Otherwise check `apps/labwin_sync/ftp/ftp.py` connector logs. |
| Script logs "FTP connection FAILED" | VPS reachable from lab PC? `Test-NetConnection 72.60.137.226 -Port 21` | If unreachable, network/firewall on the lab side. If reachable but auth fails, password drift between lab PC and VPS — re-fetch from 1Password. |
| Script logs "upload FAILED for {file}" repeatedly | The `.uploading` rename probably broke; check `/home/labwin_ftp/` on VPS for stale `*.uploading` files | The script tries to delete its own `.uploading` on retry, but a leftover from a hard kill needs `docker exec labcontrol_celery_worker python -c "..."` or a manual FTP session to delete. |
| Stale `.FDB` files in `/home/labwin_ftp/results/` | Not from this pipeline — the lab also has a separate (broken) Task Scheduler entry that pushes raw `.FDB` files via FTP | The `cleanup_misplaced_uploads` Beat task (03:50 daily) deletes these. **Eventually the lab will turn off that other task; until then this hack stays.** |
| Task Scheduler not firing on the lab PC | Event Viewer → Task Scheduler History → "Last Run Result" code on the "LabControl PDF Upload" task | Same class of issue we have for the backup uploader — Task Scheduler reliability on the lab PC is its own ongoing problem. |

**DO NOT** "fix" any of this by trying to make active FTP work. Active+NAT is the original problem, the script-based passive-only flow is what permanently sidesteps it.

---

## 🔐 Security

- **FTP, not FTPS** — plain credentials over port 21. Acceptable today because the only data on the wire is PDFs of lab results that are also delivered to the patient on paper, and the credentials only allow writes to a single chroot. **Long-term** we should switch to SFTP (reuse `backup_user`'s pattern) or FTPS, but it's not on the immediate roadmap.
- The `labwin_ftp` password lives in:
  - `.env.production` on the VPS (consumed by the backend `fetch_ftp_pdfs` connector).
  - The local copy of `upload_pdfs.py` on the lab PC (`VPS_PASSWORD` constant).
  - 1Password → "LabControl LabWin FTP user" (source of truth).
  - Older versions of `upload_pdfs.py` had the password committed to git — rotate before sharing the repo more widely. Tracked in CLAUDE.md operational hygiene.
- The `labwin_ftp` user has `/usr/sbin/nologin` as shell. No SSH access, no shell — FTP only.

---

## 🔗 Related docs

- `BACKEND.md` §FTP PDF Fetch — the backend side of this pipeline (`fetch_ftp_pdfs`, `cleanup_ftp_pdfs`, mock connector).
- `DEPLOYMENT.md` §FTP Server Configuration — vsftpd server-side setup, port allocation, firewall.
- `LABWIN_BACKUP_PIPELINE.md` — the *other* pipeline (DB backup push, SFTP, port 22). Don't confuse the two.
- `deployment/lab_workstation/upload_pdfs.py` — the script.
- CLAUDE.md "Status" entry from 2026-05-07 — short version of this rebuild story.

---

## 📋 Open follow-ups

1. **PDFs outside the 90-day Study window** (~46 of 59 in the first prod run). They sit on FTP and re-attach automatically when the parent Study lands. Three options for if/when this becomes a problem:
   - Keep current behavior (PDFs accumulate indefinitely on FTP). Cheapest.
   - Move unmatched PDFs to a `_pending/` subdir on FTP with explicit retry/expiry logic.
   - Extend the sync window for specific NUMEROs that have PDFs waiting.
2. **Rotate the `labwin_ftp` password** — historical commits of `upload_pdfs.py` and `DEPLOYMENT.md` have the value in plaintext. Rotation needs a coordinated update of 1Password, `.env.production` on the VPS, and the lab PC's copy of the script.
3. **Migrate to SFTP/FTPS.** Not urgent (see §Security) but the long-term right thing.
4. **Alerting on no-PDF-in-N-hours.** Currently if Task Scheduler stops firing on the lab PC, nobody finds out until someone notices results aren't appearing in the portal. Mirror the "no-backup-in-36h" alert from Phase F of `LABWIN_BACKUP_PIPELINE.md`.
