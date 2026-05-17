# LabControl Backend — AI Context

> **Full reference**: [BACKEND.md](BACKEND.md) · **Deploy**: [DEPLOYMENT.md](DEPLOYMENT.md) · **LabWin backup**: [LABWIN_BACKUP_PIPELINE.md](LABWIN_BACKUP_PIPELINE.md) · **Env schema**: [.env.production.template](.env.production.template)
>
> This file is the index — pointers + non-obvious gotchas only. Don't add detail here that belongs in the linked docs.

**Stack**: Django 4.2 + DRF · PostgreSQL 15 (UUID PKs) · Celery + Redis · JWT · Docker Compose · 475+ tests passing (12 outcome-branch tests added 2026-05-12 for on-demand import; ~10 more across biological_sex split)

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

### biological_sex vs gender (added 2026-05-12)
Two distinct fields on `User`. **Sync writes `biological_sex` only — never `gender`.**

- `biological_sex` (`M`/`F`/blank): clinical reference field. Sourced from LabWin `SEXO_FLD` (`1`=Female, `2`=Male — note the encoding, the original mapper had it inverted from day one and corrupted ~2,180 records before the 2026-05-12 fix). Read-only on the patient-facing API; admin/lab_staff can edit via `AdminUserCreateSerializer` and the admin Editar Usuario modal.
- `gender` (`M`/`F`/`O`/`P`/blank): patient self-declared identity. Optional, patient-editable, **never overwritten by sync**. NOT used clinically.

If you're adding a sync code path that needs to write a sex/gender value, write `biological_sex`. If you touch `_get_or_create_patient` or `_refresh_existing_patient`, do NOT pass `gender=` to `User.objects.create_user` — that was the bug that landed empty `biological_sex` on every newly-synced patient between PR 2 deploy and the follow-up fix (2 commits, both same day).

### LabWin SEXO_FLD encoding
`SEXO_FLD = 1` is **female**, `SEXO_FLD = 2` is **male**. Verified 2026-05-12 via raw PACIENTES rows — population is 85% =1 / 15% =2 (matches the lab's mostly-female demographic). The mapper had it inverted from the connector's first commit; one-shot `correct_biological_sex` management command fixed the 2,181 affected rows in prod. **Never re-flip the mapping.** See `apps/labwin_sync/mappers.py:106-118` for the canonical encoding + the comment explaining the incident.

---

## Migrations

All migrations were deleted and recreated from scratch on **2026-02-17**. Fresh `0001`/`0002` exist in every app. No legacy history — safe to assume clean slate when reading migration files.

---

## Status (2026-05-12)

**Production state**: real LabWin sync running against Firebird (`LABWIN_USE_MOCK=False`), patient emails paused (`DISABLE_PATIENT_EMAILS=True`) but **bypassed for `@labmolecular.com.ar`** via the new `PATIENT_EMAIL_ALLOWLIST_DOMAINS` env var (lab UAT in progress). Nightly Beat at 04:00 UTC. Currently ~2,180 patients with `biological_sex` populated (split from `gender` 2026-05-12; 1,700 F / 481 M / rest empty), 3,749+ studies, 1,720 doctors. All 7 containers healthy. On-demand protocol import endpoint live (admin types a NUMERO into the modal → study lands from Firebird).

### PDF upload pipeline (rebuilt 2026-05-07)
LabWin's built-in FTP plugin is **hardcoded to active mode** (UI passive toggle is decorative even after reinstall). Active FTP through the lab's NAT is unreliable — our return SYN to the client's announced data port goes unanswered. End-to-end debug session 2026-05-07 confirmed every server-side fix (CT helper rules, allow_writeable_chroot, port_enable=NO, chroot path tweaks) is irrelevant to the underlying NAT problem.

**Solution**: replaced LabWin's FTP plugin with a Python script (`deployment/lab_workstation/upload_pdfs.py`) that runs on the lab PC via Task Scheduler — **starts 03:30, repeats hourly for 12 h** (changed 2026-05-16 from a single 02:15 run, which fired mid-export and missed PDFs LabWin's slow 02:00 export hadn't written yet). Watches `C:\sistema\PDFlabwin\`, uploads via passive FTP using `ftplib.set_pasv(True)`, deletes locally on success. Atomic `.uploading` → rename pattern, idempotent per run. End-to-end validated 2026-05-07: 59 PDFs uploaded in ~2s, 13 attached to in-window studies, 0 errors. See [`PDF_UPLOAD_PIPELINE.md`](PDF_UPLOAD_PIPELINE.md) for the full rebuild story (or commit `<hash>` for the diff).

### TODO

**Gated on the LAB (out of our control until they fix):**

1. **LabWin's own scheduled PDF export CRASHES — root cause found 2026-05-17.** First seen 2026-05-09 as "incomplete export" (validated+paid studies with no PDF). On 2026-05-17 the lab PC's screen showed the actual failure: a cascade of LabWin error dialogs — window title "Monitor de Tareas Programadas" (LabWin's *own* internal task monitor, NOT Windows Task Scheduler) — each reading `Access violation at address 00DE7046 in module 'LWFile4.bpl'. Read of address 00000004.` `LWFile4.bpl` is a LabWin Delphi runtime package; this is a null-pointer crash *inside LabWin*. Every scheduled-export run access-violates → no PDFs written → `PACIENTES.EXPORTADOPDF_FLD` stays empty. Verified via Firebird query: paid+validated 257476 and 256513 have empty `EXPORTADOPDF_FLD`; protocols that owe the bono (`DEBEBONO_FLD='1'`) being unexported is correct/expected. Our `upload_pdfs.py` and the SFTP backup task are both fine — a `*.bpl` access violation can only come from LabWin (our scripts are Python; they'd show a `Traceback`). **This needs LabWin support to repair/reinstall `LWFile4.bpl` — not fixable on our side.** Until fixed, manual export from the LabWin UI is the workaround.

2. ~~**Lab PDF export landing in wrong folder.**~~ **OBSOLETE 2026-05-07** — LabWin's FTP plugin is no longer used. PDFs go via `upload_pdfs.py` script on the lab PC, which uploads to the chroot root (`/` = `/home/labwin_ftp/`) directly. No more "wrong folder" possibility.

3. **Lab pushing duplicate `.FDB` files via FTP** into `/home/labwin_ftp/results/` (~2.4 GB each, daily). 7 had accumulated as of 2026-05-01 (~16.5 GB) before we cleaned them up. **REMOVE-ONCE-LAB-FIXES-DUPLICATE-UPLOAD**: when lab confirms fix, delete:
   - `apps/labwin_sync/management/commands/cleanup_misplaced_fdb.py`
   - `cleanup_misplaced_uploads` task in `apps/labwin_sync/tasks.py`
   - "Cleanup Misplaced FTP Uploads" schedule entry in `apps/core/management/commands/setup_periodic_tasks.py`
   - `CleanupMisplacedFDBTests` in `tests/test_labwin_sync.py`
   - The PeriodicTask row in prod (`docker exec labcontrol_web python manage.py shell -c "from django_celery_beat.models import PeriodicTask; PeriodicTask.objects.filter(name='Cleanup Misplaced FTP Uploads').delete()"`)

3b. **REMOVE-ONCE-APPLIED**: `apps/users/management/commands/correct_biological_sex.py` was a one-shot script run in prod 2026-05-12 to swap M↔F + clear `gender` for the 2,181 users affected by the SEXO_FLD inversion. Already applied. Delete the file in a few days once we're confident no edge cases need re-running. Same pattern as the cleanup_misplaced_fdb removal above.

4. **Patient signup workflow when source has no email** (~52% of PACIENTES rows lack `EMAIL_FLD`). Sebastián is talking with the lab. Options being discussed: hybrid auto-email-when-present + QR code on paper result for DNI self-claim, OR lab manually triggers an invite email. Decision shapes: when to flip `DISABLE_PATIENT_EMAILS=False`, the patient-Study visibility filter, an admin "send invite" button, the patient-side claim-by-DNI landing page. See "Workflow open question" below.

**Ready to implement on OUR side (no external blockers):**

- **Implement the chosen patient-onboarding flow** once the lab decides (4).
- **Find the LabWin source for `RESULTS_FLD`** (reference range templates). `SHOW TABLE NOMEN` on the restored DB confirmed `RESULTS_FLD` / `VALORMIN` / `VALORMAX` are NOT on NOMEN — only `CONDICIONES_FLD VARCHAR(32765)`. Probably lives on a different table (`RESULTSTEMPLATES`?). Currently the CSV path via `import_labwin_practices` populates `Practice.reference_range` via `extract_reference_range()`, but it's manual. Worth a Firebird-side discovery follow-up so ranges sync automatically.
- **PDF import for files outside the imported-study NUMERO range** — currently 46 of 59 real FTP PDFs get skipped because their parent Study isn't in the 90-day window (numbers updated after 2026-05-07 rebuild). They sit on the FTP server and re-attach correctly once their Study comes into window. Either keep them indefinitely (current behavior, fine) or move to `_pending/` with explicit retry/expiry, or extend the sync window for the specific NUMEROs that have PDFs waiting.
- **Address the 2 stale 2.3 GB `.FDB` files in `/home/labwin_ftp/results/`** (probably corrupt). The `cleanup_misplaced_uploads` task already deletes these — verify they're gone after the next 03:50 run.
- **Eventually flip `DISABLE_PATIENT_EMAILS=False`** once lab signup workflow is finalized.

**Operational hygiene:**

- Rotate `deploy@` SSH password and `labwin_ftp` password (still in git history pre-cleanup); replace 1Password entries.
- Migrate `deploy@` to SSH key auth, drop the sshpass workflow entirely.
- Decide retention policy for `/srv/labwin_backups/processed/` (currently 30 days).
- **No alerting yet**: if the 04:00 sync silently fails for 5 nights, nobody finds out unless someone tails logs. Phase F of LABWIN_BACKUP_PIPELINE.md mentions a "no-backup-in-36h" alert as future work.

### Done recently

- ✅ **2026-05-12 (long session)** — **biological_sex split, SEXO_FLD inversion fix, on-demand protocol import (the big one), several UAT fixes.**

  **Schema + sync semantics — `biological_sex` split from `gender`:**
  - New `User.biological_sex` (M/F, blank). Sourced from LabWin SEXO_FLD, read-only on the patient API. `User.gender` (M/F/O/P, blank) is now patient-self-declared and **never written by sync**.
  - Migration `0003_user_biological_sex` adds the column + backfills `biological_sex` from existing `gender` for M/F users (1,700 + 481).
  - `mappers.map_patient` returns `biological_sex` (not `gender`). `_get_or_create_patient` and `_refresh_existing_patient` write `biological_sex`. Deliberate: don't pass `gender=` to `create_user` — that was the bug that landed empty `biological_sex` on every freshly-synced patient between PR 2 deploy and the follow-up fix.
  - Serializers: `UserSerializer` exposes `biological_sex` as read_only. `PatientRegistrationSerializer` requires it. `UserUpdateSerializer` deliberately omits it.
  - Frontend: ProfileView shows both fields (biological_sex read-only above gender). RegisterView has a required M/F select. Admin Editar Usuario modal has the field as editable.

  **SEXO_FLD inversion fix — corruption since the connector's first commit:**
  - Verified against real PACIENTES rows: `SEXO_FLD=1` is **female**, `=2` is **male** (population is 85% =1 / 15% =2 — matches the lab's mostly-female demographic).
  - Mapper had `1→M, 2→F` for months. Every synced patient had inverted biological sex. PR 2's migration then copied the wrong `gender` into `biological_sex`, doubling the corruption.
  - `apps/labwin_sync/mappers.py` flipped to `1→F, 2→M`. Mock data fixed too.
  - One-shot `correct_biological_sex` management command swapped 2,181 users (M↔F) + cleared `gender` for role='patient'. Distribution went from 1700 M / 481 F → 1700 F / 481 M (correct). Yamila Garcia + the 4 "Juan Pablo *" patients spot-checked.
  - **REMOVE-ONCE-APPLIED**: see TODO 3b above.

  **On-demand protocol import (`import_protocol_by_numero`):**
  - New full-stack feature for importing studies older than the 90-day nightly window. Admin types a NUMERO into the modal → Celery task pulls one protocol from the local Firebird container → runs through the same mappers + skip-filters as nightly sync. PDF is uploaded later via the existing FTP path.
  - Components: `connectors/base.py` + `firebird.py` + `mock.py` `fetch_one_protocol(numero)`; `tasks.py` `import_protocol_by_numero` (max_retries=0, decision tree: `not_found` / `partial_validation` / `unpaid_skipped` / `derivacion_skipped` / `pet_skipped` / `already_imported` / `imported`); cache-based concurrency lock; `TriggerImportProtocolView` at `POST /api/v1/labwin-sync/import-protocol/`; management command `import_protocol`; SyncLog tagged `backup_filename="on-demand:LW-{numero}"` for audit (no migration).
  - Admin/lab_staff only. Same notification path as nightly sync (`_dispatch_patient_notifications`) — `DISABLE_PATIENT_EMAILS` + `PATIENT_EMAIL_ALLOWLIST_DOMAINS` apply unchanged.
  - `force=True` kwarg added later same day: bypasses ONLY the `derivacion_skipped` filter (walk-in patients with NUMMEDICO_FLD=175). Other filters intact (data-quality reasons). Frontend "Importar de todas formas" button on the derivacion result card.
  - **On-demand-only fix to `completed_at`**: the mapper deliberately leaves `completed_at = NULL` (frontend reads `created_at` as "Completado"). For an on-demand import of an old study, that produced "Completado: today" on a year-old study. Backfill `completed_at = service_date` after the study lands. Nightly sync stays untouched — the historical "completed before solicited" visual bug the mapper comment warns about can't reappear there.
  - 12 outcome-branch tests + 8 API permission/validation tests + 3 force tests + 1 completed_at test.

  **Patient-email allowlist (`PATIENT_EMAIL_ALLOWLIST_DOMAINS`):**
  - New env var (comma-separated, case-insensitive). When `DISABLE_PATIENT_EMAILS=True`, patients whose email domain matches the list still receive emails. Used to let lab staff test the patient flow with `@labmolecular.com.ar` accounts while real patients stay paused.
  - Set `PATIENT_EMAIL_ALLOWLIST_DOMAINS=labmolecular.com.ar` in `.env.production` on the VPS.

  **Multi-token search fix in `unaccent_icontains_q`:**
  - UAT bug: searching `"estefania s"` returned 0 results because `__icontains` matched the literal substring against each field.
  - Fix: split on whitespace, AND tokens, OR fields-per-token. `"estefania schm"` now narrows to just the Schmidts. Backward compatible (single-token search unchanged).
  - Bonus side effect: same helper is used by StudyFilter, PracticeFilter, search-doctors, search-patients — all benefit.

  **UAT polish** (separate small commits):
  - Email templates rewritten to LDM voice (Spanish, no Security Notice, no LabControl branding): `email_verification.html` + `result_ready.html` + `send_result_notification_email` subject line.
  - Registration: replaced inline success strip + 2s auto-redirect with a centered modal that requires manual click. Spam-folder hint included.
  - ResultsView patient name is now a clickable button (admin/lab_staff only) → opens a tight detail popup with email/DNI/phone/birthday. Sanity-check for the "wrong patient attached" UAT bug.
  - CreateStudyModal got a yellow deprecation banner pointing to the new "Importar protocolo antiguo" button.
  - Profile birthday rendered in `es-AR` locale ("17 de diciembre de 1966" instead of "December 17, 1966").
  - "N° de Carnet" label renamed to "N° de Afiliado" across all 3 forms (label + placeholder).

- ✅ **2026-05-10 (frontend session)** — **PDF backlog drained + UI polish.**
  - **PDF gap resolved (for now).** Diagnosed two new studies missing PDFs (LW-257278 and LW-256891). Confirmed via Firebird query that LabWin's export uses `EXPORTADOPDF_FLD` as a cursor *and* filters by `solicitado date` (FECHA_FLD). Manual exports against the lab's UI for the full window finished today; portal currently has 0 studies missing PDFs. Tomorrow's nightly run is the experiment: now that the backlog is drained, does the LabWin scheduled task succeed on a near-empty workload? If yes, backlog was the cause; if drops still happen, it's a logic/timeout bug and the next move is the date-window plan (export by FECHA_FLD, ignore EXPORTADOPDF_FLD).
  - **Pagination component** (`labcontrol-frontend/src/components/Pagination.vue`). Numbered pages + first/last/prev/next icon buttons + clickable ellipsis (jumps ±5 pages). Replaces the prev/next-only pagination in `ResultsView.vue` and `admin/PatientsView.vue` (the latter wasn't usable beyond page 1 for 572-page lists). Frontend commit `207d115`, deployed.
  - **Background images: PNG → WebP, 5.6 MB → 140 KB (~40×)** — fixes the white-flash on first paint that was visible on every page load. Per-file: `background_desktop` 2.32 MB → 31 KB (also downscaled 4000×2250 → 1920×1080), `ipad` 1.59 MB → 62 KB, `phone` 1.69 MB → 46 KB. Touched 12 views. cwebp q=82. Frontend commit `bb7a8b5`, deployed. Removes the "Compress background images to WebP" item from FRONTEND.md TODO.
  - **`Cleanup FTP PDFs` Beat task** confirmed already running (`apps.labwin_sync.tasks.cleanup_ftp_pdfs`, cron `0 3 * * 0` UTC = midnight Sunday lab time). Docs that say it's not scheduled are stale. Ran today (2026-05-10 is Sunday) at 03:00 UTC.
  - **Timezone reality check**: confirmed all containers + Django settings + Celery are UTC. Lab is UTC-3 (no DST). So Beat schedules in `setup_periodic_tasks.py` need to be read with `lab_time = utc - 3h`.

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
