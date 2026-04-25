# LabControl Backend — AI Context

> **Full reference**: [BACKEND.md](BACKEND.md) · **Deploy**: [DEPLOYMENT.md](DEPLOYMENT.md) · **LabWin backup**: [LABWIN_BACKUP_PIPELINE.md](LABWIN_BACKUP_PIPELINE.md) · **Env schema**: [.env.production.template](.env.production.template)
>
> This file is the index — pointers + non-obvious gotchas only. Don't add detail here that belongs in the linked docs.

**Stack**: Django 4.2 + DRF · PostgreSQL 15 (UUID PKs) · Celery + Redis · JWT · Docker Compose · 374 tests passing

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
- **LabWin backup pipeline — Fase B** (gating item to flip `LABWIN_USE_MOCK=False` in prod):
  - Add `firebird` service to `docker-compose.prod.yml`
  - Implement `apps/labwin_sync/services/backup_import.py` + `tasks.import_uploaded_backup`
  - Management command `python manage.py import_backup`
  - Wire Celery Beat schedule
  - Plan: [LABWIN_BACKUP_PIPELINE.md §Plan de implementación](LABWIN_BACKUP_PIPELINE.md#-plan-de-implementación-fases)
- Schedule Task Scheduler on lab PC for nightly 02:00 upload (currently runs manually)
- Populate `Practice.reference_range` once clean LabWin reference data is available
- Compress background images to WebP (FRONTEND.md TODO)

### Done recently
- ✅ **2026-04-24** — LabWin backup pipeline Fase A complete: SFTP `backup_user` chroot on VPS, ed25519 keypair deployed, first real upload succeeded (69.9 MB, 22 s)
- ✅ **2026-04-18** — 2,174 LabWin practices imported
- ✅ **2026-04-12** — Doctor CSV import + LabWin sync feature shipped

### Known issues
None — all 374 tests passing.

---
*Index file. Edit BACKEND.md / DEPLOYMENT.md / LABWIN_BACKUP_PIPELINE.md for detail; only update here on architectural changes or new gotchas.*
