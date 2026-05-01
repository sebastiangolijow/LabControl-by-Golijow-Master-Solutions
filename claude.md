# LabControl Backend — AI Context

> **Full reference**: [BACKEND.md](BACKEND.md) · **Deploy**: [DEPLOYMENT.md](DEPLOYMENT.md) · **LabWin backup**: [LABWIN_BACKUP_PIPELINE.md](LABWIN_BACKUP_PIPELINE.md) · **Env schema**: [.env.production.template](.env.production.template)
>
> This file is the index — pointers + non-obvious gotchas only. Don't add detail here that belongs in the linked docs.

**Stack**: Django 4.2 + DRF · PostgreSQL 15 (UUID PKs) · Celery + Redis · JWT · Docker Compose · 459 tests passing

---

## ⚠️ Non-negotiable conventions

### UUID primary keys
All models use UUID PKs. **Always `.pk`, never `.id`** (raises `AttributeError`).

```python
user.pk                       # ✓
Count("pk", filter=Q(...))    # ✓ in aggregations
str(obj.pk)                   # ✓ in test assertions
user.id                       # ✗
```

### Multi-tenant filtering
`User`, `Study`, `Appointment`, `Invoice` carry `lab_client_id: IntegerField`. Always scope queries:

```python
Study.objects.filter(lab_client_id=request.user.lab_client_id)
```

`Company` FK is planned but not implemented — `lab_client_id` is a plain int today.

### Permissions
Role check: `user.role in ['admin', 'lab_staff']`. Classes in `apps/core/permissions.py`: `IsAdminUser`, `IsAdminOrLabStaff`, `IsPatientOwner`.

### Test factories (`tests/base.BaseTestCase`)
High-frequency lookup — keeping the list here avoids re-grepping every time:

```python
self.create_admin() / create_lab_staff() / create_doctor() / create_patient()
self.create_practice(**kwargs)
self.create_study(patient, practice=p)              # auto protocol_number, creates StudyPractice
self.create_study(patient, practices=[p1, p2])      # multi-practice
self.create_appointment(patient, study)
self.create_invoice(patient, study) / create_payment(invoice)
self.authenticate_as_patient() → (client, user)     # also _admin / _lab_staff
```

### Adding a new Celery task
Worker doesn't hot-reload — **restart `celery_worker` AND `celery_beat`** after adding tasks (autodiscover only runs on startup). Easy to miss; symptom is "task not registered" in logs.

### Deploying Python code changes
**Always `docker compose build` before `up -d --force-recreate`.** The `web` / `celery_worker` / `celery_beat` images COPY `apps/` at build time, so an rsync to the host + recreate-only spins up the OLD code. Symptom: `docker exec <container> grep` shows the previous version. See DEPLOYMENT.md §Backend Updates.

### Changing a healthcheck (or any compose-level service config)
**`docker compose up -d --force-recreate <svc>`, NOT `restart`.** `restart` only restarts the running container — it doesn't re-read `docker-compose.yml`, so new healthcheck/env/volumes/network changes are silently ignored. Symptom: you change the healthcheck CMD in compose, run `restart`, and the container keeps reporting unhealthy with the OLD probe. Bit me on the nginx healthcheck fix (commit 877f51f).

---

## Migrations

All migrations were deleted and recreated from scratch on **2026-02-17**. Fresh `0001`/`0002` exist in every app. No legacy history — safe to assume clean slate when reading migration files.

---

## Status (2026-05-01)

**Production state**: real LabWin sync running against Firebird (`LABWIN_USE_MOCK=False`), patient emails disabled (`DISABLE_PATIENT_EMAILS=True`), nightly Beat at 04:00. Currently 3,040 patients / 3,749 studies / 1,720 doctors / 15 PDFs attached. All 7 containers healthy.

### TODO

**Gated on the LAB (out of our control until they fix):**

1. **Lab Task Scheduler not firing the nightly SFTP upload.** Last `backup_user` SFTP session on the VPS was 2026-04-29 15:14 (manual test). No 02:00 sessions on Apr 30 or May 1. Symptom: `/srv/labwin_backups/incoming/` is empty after 02:00. Lab to check Task Scheduler History "Last Run Result" + Event Viewer for the upload script.

2. **Lab PDF export landing in wrong folder.** New PDFs sometimes appear in the FTP chroot root (`/`) instead of `/results/`. The `cleanup_misplaced_uploads` Beat task at 03:50 moves them, but the source should be fixed. Lab to verify the LabWin PDF export config points to `/results/`.

3. **Lab pushing duplicate `.FDB` files via FTP** into `/home/labwin_ftp/results/` (~2.4 GB each, daily). 7 had accumulated as of 2026-05-01 (~16.5 GB) before we cleaned them up. **REMOVE-ONCE-LAB-FIXES-DUPLICATE-UPLOAD**: when lab confirms fix, delete:
   - `apps/labwin_sync/management/commands/cleanup_misplaced_fdb.py`
   - `cleanup_misplaced_uploads` task in `apps/labwin_sync/tasks.py`
   - "Cleanup Misplaced FTP Uploads" schedule entry in `apps/core/management/commands/setup_periodic_tasks.py`
   - `CleanupMisplacedFDBTests` in `tests/test_labwin_sync.py`
   - The PeriodicTask row in prod (`docker exec labcontrol_web python manage.py shell -c "from django_celery_beat.models import PeriodicTask; PeriodicTask.objects.filter(name='Cleanup Misplaced FTP Uploads').delete()"`)

4. **Patient signup workflow when source has no email** (~52% of PACIENTES rows lack `EMAIL_FLD`). Sebastián is talking with the lab. Options being discussed: hybrid auto-email-when-present + QR code on paper result for DNI self-claim, OR lab manually triggers an invite email. Decision shapes: when to flip `DISABLE_PATIENT_EMAILS=False`, the patient-Study visibility filter, an admin "send invite" button, the patient-side claim-by-DNI landing page. See "Workflow open question" below.

**Ready to implement on OUR side (no external blockers):**

- **Implement the chosen patient-onboarding flow** once the lab decides (4).
- **Find the LabWin source for `RESULTS_FLD`** (reference range templates). `SHOW TABLE NOMEN` on the restored DB confirmed `RESULTS_FLD` / `VALORMIN` / `VALORMAX` are NOT on NOMEN — only `CONDICIONES_FLD VARCHAR(32765)`. Probably lives on a different table (`RESULTSTEMPLATES`?). Currently the CSV path via `import_labwin_practices` populates `Practice.reference_range` via `extract_reference_range()`, but it's manual. Worth a Firebird-side discovery follow-up so ranges sync automatically.
- **PDF import for files outside the imported-study NUMERO range** — currently 41 of 56 real FTP PDFs get skipped because their parent Study isn't in the 90-day window. Either keep the PDFs in `_pending/` and re-attach when their Study lands, or extend the sync window for the specific NUMEROs that have PDFs waiting.
- **Address the 2 stale 2.3 GB `.FDB` files in `/home/labwin_ftp/results/`** (probably corrupt). The `cleanup_misplaced_uploads` task already deletes these — verify they're gone after the next 03:50 run.
- **Compress background images to WebP** (FRONTEND.md TODO).
- **Eventually flip `DISABLE_PATIENT_EMAILS=False`** once lab signup workflow is finalized.

**Operational hygiene:**

- Rotate `deploy@` SSH password and `labwin_ftp` password (still in git history pre-cleanup); replace 1Password entries.
- Migrate `deploy@` to SSH key auth, drop the sshpass workflow entirely.
- Decide retention policy for `/srv/labwin_backups/processed/` (currently 30 days).
- **No alerting yet**: if the 04:00 sync silently fails for 5 nights, nobody finds out unless someone tails logs. Phase F of LABWIN_BACKUP_PIPELINE.md mentions a "no-backup-in-36h" alert as future work.

### Done recently

- ✅ **2026-05-01 (full session)** — **Test-mode reset, real-data sync, + 3 follow-ups.** Now in production: live Firebird sync (mock flag flipped to `False`) ingesting against real lab data, with patient emails disabled via kill switch. Final state: 3,040 patients / 3,749 studies / 25,439 StudyPractices / 15 PDFs attached, all within a 90-day window (2026-01-31 → 2026-04-29).

  **Code changes shipped today:**
  - **`DISABLE_PATIENT_EMAILS` env flag** (`config/settings/base.py`). When `True`, `_dispatch_patient_notifications` short-circuits both `.delay()` calls but still sets `Study.notification_sent_at` so re-syncs don't re-queue. Admin/system emails unaffected. Verified in prod: `emails_skipped=3,040, notifications_queued=0` and zero actual `.delay()` calls in worker logs.
  - **SyncLog counters extended** (migration `0002_synclog_counters_extension`): `study_practices_created`, `notifications_queued`, `emails_skipped`.
  - **Backup file dedup** (migration `0003_synclog_backup_filename`). New `SyncLog.backup_filename` field; `BackupImporter.run()` checks for prior completed SyncLog with the same filename and returns `status=skipped` if found, without restoring. Defends against the lab uploading the same `.fbk.gz` twice.
  - **Loggers added** to `_get_or_create_patient` and `_get_or_create_study_with_practices`: WARNING when patient created without email, WARNING on email collision (was INFO), INFO for new patient + study creation. New `sync_labwin_results SUMMARY` log line at end of every sync run with all 9 counters greppable in one line.
  - **`cleanup_misplaced_fdb` management command + `cleanup_misplaced_uploads` Celery task** (Beat: daily 03:50). Connects via FTP, deletes `*.FDB` / `*.fbk` / `*.fbk.gz` from `/` and `/results/`, moves orphan PDFs from `/` into `/results/`. **REMOVE-ONCE-LAB-FIXES-DUPLICATE-UPLOAD** — see TODO. One-shot run on 2026-05-01 freed 16.5 GB.
  - **`reset_test_data` management command** (`apps/users/management/commands/`). Deletes patients + studies (cascade includes StudyPractice, Appointments, Invoices, Notifications, plus orphan SyncedRecord cleanup). Keeps practices, doctors, lab_staff, admins, SyncLog history. Requires `--confirm`; refuses if `DEBUG=False AND DISABLE_PATIENT_EMAILS=False`.
  - **`Practice.reference_range` populated** from `extract_reference_range()` in `import_labwin_practices` — was previously only writing the raw `result_template`, leaving `reference_range` empty. Frontend `getRefRangeFromSp()` (`labcontrol-frontend/src/views/ResultsView.vue:890`) was already wired but had no data.
  - **`has_pdf` filter on `StudyFilter`** + frontend `<select>` toggle ("-" / "Con PDF" / "Sin PDF"). Wired through `buildFetchParams()` in ResultsView.vue. Smoke test on prod data: 15 with PDF / 3,734 without / 3,749 total ✓.
  - **Beat schedule changes**: `Sync LabWin Results` moved from 02:00 → 04:00 (gives 2h headroom after lab's 02:00 SFTP upload). `setup_periodic_tasks` made idempotent — re-running now updates existing rows when the schedule has drifted, instead of silently skipping. New schedule: `Cleanup Misplaced FTP Uploads` daily 03:50 (defends against duplicate `.FDB` uploads).

  **Operational changes on the VPS:**
  - Applied `studies.0006_historicalstudy_notification_sent_at_and_more` migration (committed 2026-04-28 but never deployed — surfaced via a `ProgrammingError` mid-`reset_test_data`).
  - Flipped `LABWIN_USE_MOCK=True` → `False` in `.env.production`.
  - Set `DISABLE_PATIENT_EMAILS=True` in `.env.production`.
  - Cleaned 16.5 GB of stray `.FDB` files from FTP. Moved 1 orphan PDF.
  - Rebuilt + force-recreated `web` / `celery_worker` / `celery_beat` images twice (once for the deploy, once for the 3 follow-ups).
  - Restarted `nginx` to serve the new frontend dist.
  - Ran `reset_test_data --confirm` twice (the runaway `--full` sync surfaced the missing migration; second run cleaned up after the `--full` flag was caught and the windowed sync was used).
  - Sync verification: ran `sync_labwin --use-celery` (NO `--full`, since `--full` bypasses the 90-day window per the inline comment at `apps/labwin_sync/tasks.py:87`). Real-data sync took ~1 min. PDF fetch attached 15/56 (rest skipped because their NUMEROs are outside the window — known issue).

  **Tests**: 14 new tests across `DisablePatientEmailsTests`, `SyncLoggerTests`, `ReferenceRangePopulationTests`, `CleanupMisplacedFDBTests`, `ResetTestDataCommandTests`, plus `BackupImporterRunTests` (4 dedup tests) and `TestStudyFilterUnit` (3 has_pdf tests). All passing locally; pre-existing 24 redis-related failures unchanged baseline (need Redis running for HTTP API integration tests).

  **Plan file**: `/Users/cevichesmac/.claude/plans/spicy-swimming-bengio.md` has the full deployment summary table.
- ✅ **2026-04-28 (latest)** — **Window simplification + activation flow**. Two earlier-same-day designs replaced by a cleaner final shape:
  - **Single window**: dropped `LABWIN_SYNC_INITIAL_DAYS` / `LABWIN_SYNC_ROLLING_DAYS`, replaced with one `LABWIN_SYNC_WINDOW_DAYS=90`. Every sync re-imports DETERS where `FECHA_FLD >= today - 90 days`. The connector filters on sample/order date (FECHA_FLD), not validation date — so a study sampled 60 days ago but validated yesterday gets picked up by today's sync. Re-imports are idempotent; old data (~14 years of history) is skipped per business decision.
  - **Patients imported INACTIVE**: `_get_or_create_patient` now creates new users with `is_active=False, is_verified=False` (regardless of email). They activate themselves by clicking the password-setup link. `SetPasswordView` flips both flags, sets the password, and creates the `allauth.EmailAddress` row (without which login silently fails because allauth authenticates against EmailAddress, not User.email).
  - **DNI revival**: when sync finds a User by DNI who has no email but PACIENTES now brings one, the sync writes the email and routes them through password-setup (so they get an activation email instead of a "your study is available" one).
- ✅ **2026-04-28 (earlier)** — Patient notification dispatch from `sync_labwin_results`. New `Study.notification_sent_at` field + new `apps.notifications.tasks.send_studies_available_email` (batched). Sync ends with one email per patient: already-active users → "your N new studies are available" (reuses `result_ready.html`), users needing setup → password-setup (reuses existing `send_password_setup_email`). Emailless patients skipped silently — `notification_sent_at` stays NULL so a later sync (DNI revival) can retry. 475 tests passing (6 new `PatientActivationTests` + 5 `SyncNotificationTests`).
- ✅ **2026-04-25 (previous session)** — see "Today's session" below
- ✅ **2026-04-24** — LabWin backup pipeline Fase A complete (SFTP chroot, first real upload 69.9 MB)
- ✅ **2026-04-18** — 2,174 LabWin practices imported
- ✅ **2026-04-12** — Doctor CSV import + LabWin sync feature shipped

### Today's session — 2026-04-25

**Phase A→B rollout for LabWin backup ingestion (the big one):**
- Added `firebird` (jacobalberty/firebird:2.5-ss) container to `docker-compose.prod.yml`. Restored real `BASEDAT_20260424_180940.fbk.gz` (70 MB → 2.2 GB DB) in 155s via `firebirdsql.services.restore_database`. PACIENTES 218k rows / DETERS 940k / MEDICOS 7k / NOMEN 2k all queryable.
- `apps/labwin_sync/services/backup_import.BackupImporter` + Celery task `import_uploaded_backup` + management command `import_backup`.
- Smoke test surfaced 3 real-data quirks (email collisions, varchar(20) overflow, duplicate `(study, practice)`) — all fixed.
- Added `Study.is_paid` (from `DEBEBONO_FLD`) and `Study.is_validated` flags. Re-sync updates flags on existing studies.
- Pet/veterinary patient skip rule (combined: `dni='' AND (last_name starts with '167' OR has vet practice)`); deleted 583 pet users + cascade.
- Fixed `fetch_ftp_pdfs` filename parser for `{NUMERO}-{DNI}-{NAME}.pdf` format. 24 real PDFs attached end-to-end.

**Search bug fix (user-reported):**
- Patient list search returning wrong results due to client-side filtering on paginated data.
- Backend: enabled Postgres `unaccent` extension; new `apps/core/search.unaccent_icontains_q()` helper; `UserFilter`/`StudyFilter` now match across `first_name, last_name, email, dni, phone_number, matricula, protocol_number` accent + case insensitively. `'si'` now matches 164 patients (was 1).
- Frontend (`labcontrol-frontend`): `ResultsView.vue` and `PatientsView.vue` rewired from client-side filter to server-side `?search=&ordering=&page=`.

**Operational fixes:**
- All 3 broken healthchecks fixed (`web` uses `/health/` endpoint via `http.client`; `nginx` uses `nc -z localhost 443`; `celery_beat` reads PID 1 cmdline). All 7 containers now report `(healthy)`.
- Comprehensive logging across Celery tasks, ingestion, auth, and state mutations. Memory snapshots at start/end of long-running tasks.
- Log-tail commands: `make logs-prod*` from laptop + `labcontrol-logs` shell wrapper on the VPS.

**Security/hygiene:**
- Scrubbed plaintext secrets from docs (`39872327Seba.`, `LabWinFTP2026!`, `masterkey`, embedded SSH private key); replaced with `$DEPLOY_SSH_PASSWORD` + 1Password references.
- `.env.production` was committed to git; removed from index, added to gitignore. **Existing values still in git history** — rotation pending.

**Tests**: 374 → **459 passing**, 0 regressions. ~85 new tests across the work above.

### Workflow open question (waiting on lab)

Roughly 52% of PACIENTES rows have empty `EMAIL_FLD`. Current import creates them anyway (with `email=None`), but they have no portal access. Sebastián is talking with the lab to decide:
- Always import patient + lab manually triggers invite email when ready?
- QR code on paper results for self-claim by DNI?
- Hybrid — auto-email when source has email, QR-claim when not?

Decision will shape: nightly sync window, patient-Study visibility filter, new admin "send invite" button, and patient-side claim-by-DNI landing page. Backend work ~half day, frontend ~half day, once decided.

### Known issues
None blocking. All 459 tests passing. All 7 containers healthy.

---
*Index file. Edit BACKEND.md / DEPLOYMENT.md / LABWIN_BACKUP_PIPELINE.md for detail; only update here on architectural changes or new gotchas.*
