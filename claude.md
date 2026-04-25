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

## Status (2026-04-25)

### TODO

**Gated on lab decision (waiting on Sebastián's conversation with the lab):**
- **Patient signup workflow when source has no email** (~52% of PACIENTES rows lack `EMAIL_FLD`). Options being discussed: hybrid that always imports the patient (with `is_active=False` until signup) + QR code on the paper result for self-claim by DNI, OR lab manually triggers an invite email. See "Workflow open question" below for the full design tradeoff.

**Ready to implement (no external blockers):**
- Switch sync window from "all >= 2026-02-01" to **rolling yesterday + today** so re-imports update yesterday's late-validated rows without rescanning everything.
- Implement the chosen patient-onboarding flow once decided.
- **Schedule Celery Beat** for `import_uploaded_backup` (nightly 04:00) AND `fetch_ftp_pdfs`. Currently both are manual-only by deliberate choice — only flip after the workflow above is locked in.
- **Schedule Task Scheduler on lab PC** for nightly 02:00 upload (still manual).
- Populate `Practice.reference_range` from real LabWin data (the cleaner source we now have access to).
- Address the 2 stale 2.3 GB `.FDB` files in `/home/labwin_ftp/results/` (probably corrupt).
- PDF import workflow for files outside the imported-study NUMERO range — currently 32 of 56 real FTP PDFs get skipped because their study isn't imported yet.
- Compress background images to WebP (FRONTEND.md TODO).

**Operational hygiene:**
- Rotate `deploy@` SSH password and `labwin_ftp` password (still in git history pre-cleanup); replace 1Password entries.
- Migrate `deploy@` to SSH key auth, drop the sshpass workflow entirely.
- Decide retention policy for `/srv/labwin_backups/processed/` (currently 30 days).

### Done recently
- ✅ **2026-04-25 (this session)** — see "Today's session" below
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
