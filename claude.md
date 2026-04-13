# LabControl Backend - AI Context

> **📖 For complete documentation, see [BACKEND.md](BACKEND.md)**
>
> This file provides a quick reference. For comprehensive backend architecture,
> API reference, development guide, and best practices, refer to BACKEND.md.

**Project**: Medical laboratory management system
**Framework**: Django 4.2 + Django REST Framework
**Database**: PostgreSQL (UUID primary keys)
**Tasks**: Celery + Redis
**Auth**: JWT (djangorestframework-simplejwt)
**Deployment**: Docker + docker-compose

## Project Structure

```
apps/
├── users/          # User management, authentication
│   ├── models.py   # User (UUID PK, roles: patient/doctor/lab_staff/admin)
│   ├── views.py    # User CRUD, doctor/patient search, create user
│   ├── serializers.py
│   ├── permissions.py
│   └── management/commands/
│       ├── verify_email.py       # Verify single user email
│       └── create_seed_users.py  # Create admin/doctor/patient seed users
├── studies/        # Lab studies, practices, determinations
│   ├── models.py   # Practice (with code field), Determination, Study, UserDetermination
│   ├── views.py    # Study CRUD, upload/download results
│   ├── serializers.py  # PracticeSerializer includes determinations_detail
│   ├── filters.py
│   ├── managers.py
│   └── management/commands/load_practices.py
├── labwin_sync/    # LabWin Firebird sync
│   ├── models.py   # SyncLog, SyncedRecord
│   ├── tasks.py    # sync_labwin_results Celery task
│   ├── mappers.py  # LabWin → Django field mapping
│   ├── connectors/ # base, firebird, mock
│   └── management/commands/sync_labwin.py
├── appointments/   # Appointment scheduling
├── payments/       # Payment processing
├── notifications/  # Notifications (email/in-app, Celery tasks)
├── analytics/      # Analytics and reporting
└── core/           # BaseModel, BaseManager, RBAC utilities

config/
├── settings/       # base, dev, test, prod
├── celery.py
└── urls.py

apps/labwin_sync/   # LabWin Firebird sync (connectors, mappers, models, tasks)

tests/              # 374 tests, 82% coverage
```

## Models

### User (apps/users/models.py)
```python
class User(AbstractBaseUser, PermissionsMixin):
    uuid = UUIDField(primary_key=True)
    email = EmailField(unique=True)
    role = CharField(choices=['admin','lab_staff','doctor','patient'])
    first_name, last_name, phone_number, dni, birthday
    gender, location, direction           # profile fields
    mutual_code, mutual_name, carnet      # insurance fields
    lab_client_id = IntegerField()        # multi-tenant (TODO: FK to Company)
    is_active, is_staff, is_verified
    verification_token, verification_token_created_at
    created_by = FK('self', null=True)
    history = HistoricalRecords()         # audit trail
```

### Practice (apps/studies/models.py)
```python
class Practice(BaseModel):
    name, technique, sample_type, sample_quantity
    code = CharField(max_length=20, blank=True, db_index=True)  # LabWin ABREV_FLD
    price = DecimalField()
    delay_days = IntegerField()
    is_active = BooleanField()
    determinations = ManyToManyField(Determination, blank=True)
```

### Determination (apps/studies/models.py)
```python
class Determination(BaseModel):
    # Individual lab measurement (e.g. Glucose, Hemoglobin, WBC)
    name = CharField(max_length=200)
    code = CharField(max_length=50, unique=True)
    unit = CharField()
    reference_range = CharField()
    description = TextField()
    is_active = BooleanField()
```

### Study (apps/studies/models.py)
```python
class Study(BaseModel, LabClientModel):
    patient = FK(User, related_name='studies')
    practice = FK(Practice)               # replaces old study_type FK
    protocol_number = CharField(unique=True)  # replaces old order_number
    ordered_by = FK(User, null=True, related_name='ordered_studies')  # doctor
    status = CharField(choices=['pending','in_progress','completed','cancelled'])
    results_file, results, completed_at
    lab_client_id = IntegerField()
    history = HistoricalRecords()

    # Custom managers
    Study.objects.pending()
    Study.objects.completed()
    Study.objects.for_patient(patient)
    Study.objects.for_lab(lab_client_id)

    def __str__(self): return f"{protocol_number} - {practice.name}"
    @property is_pending, is_completed
```

### UserDetermination (apps/studies/models.py)
```python
class UserDetermination(BaseModel):
    # Stores result value of a determination for a specific study
    study = FK(Study, related_name='determination_results')
    determination = FK(Determination, related_name='user_results')
    value = CharField(max_length=200)
    is_abnormal = BooleanField(default=False)
    notes = TextField()
    class Meta:
        unique_together = [['study', 'determination']]
```

## API Endpoints

### Authentication
```
POST   /api/v1/auth/login/
POST   /api/v1/auth/logout/
POST   /api/v1/auth/token/refresh/
GET    /api/v1/auth/user/
PATCH  /api/v1/auth/user/
```

### Users
```
POST   /api/v1/users/register/          # Public registration
POST   /api/v1/users/create-user/       # Admin only
GET    /api/v1/users/search-doctors/    # Admin/lab_staff
GET    /api/v1/users/search-patients/   # Admin/lab_staff
GET    /api/v1/users/                   # Admin only
GET/PATCH/DELETE /api/v1/users/{id}/
POST   /api/v1/users/import-doctors/    # Import doctors from CSV (async)
GET    /api/v1/users/import-doctors/status/{task_id}/  # Check import status
```

### Studies
```
GET    /api/v1/studies/                          # Filtered by role
GET    /api/v1/studies/{id}/
POST   /api/v1/studies/{id}/upload_result/       # Admin/staff
GET    /api/v1/studies/{id}/download_result/
DELETE /api/v1/studies/{id}/delete-result/       # Admin/staff
GET    /api/v1/studies/with-results/             # Admin/staff
GET    /api/v1/studies/available-for-upload/     # Admin/staff

GET    /api/v1/studies/practices/                # List active practices
GET    /api/v1/studies/determinations/           # List determinations
GET/POST/PATCH /api/v1/studies/user-determinations/  # Study result values
```

### LabWin Sync
```
POST   /api/v1/labwin-sync/trigger/         # Trigger manual sync (admin only)
GET    /api/v1/labwin-sync/status/           # Get last sync status
GET    /api/v1/labwin-sync/logs/             # List sync logs
```

### Analytics
```
GET    /api/v1/analytics/dashboard/
GET    /api/v1/analytics/studies/
GET    /api/v1/analytics/studies/trends/
GET    /api/v1/analytics/revenue/
GET    /api/v1/analytics/revenue/trends/
GET    /api/v1/analytics/appointments/
GET    /api/v1/analytics/users/
GET    /api/v1/analytics/popular-practices/        # renamed from popular-study-types
GET    /api/v1/analytics/top-revenue-practices/    # renamed from top-revenue-study-types
```

## Key Patterns

### UUID Primary Keys — CRITICAL
```python
# ✓ ALWAYS use .pk
user.pk / study.pk
Count("pk", filter=Q(...))
str(obj.pk)   # in assertions

# ✗ NEVER use .id (fails with UUID PKs)
```

### Multi-Tenant Filtering
```python
# lab_client_id is an IntegerField on User and Study
Study.objects.filter(lab_client_id=request.user.lab_client_id)
User.objects.filter(lab_client_id=request.user.lab_client_id)
```

### Permissions
```python
# Role checks
user.role in ['admin', 'lab_staff']
# Permission classes: IsAdminUser, IsAdminOrLabStaff
```

### Tests
```python
from tests.base import BaseTestCase

# Factories available:
self.create_user(role=...)
self.create_admin() / create_lab_staff() / create_doctor() / create_patient()
self.create_practice(**kwargs)         # name, technique, sample_type, price, etc.
self.create_study(patient, practice)   # protocol_number auto-generated
self.create_appointment(patient, study)
self.create_invoice(patient, study)
self.create_payment(invoice)
self.create_notification(user)
self.authenticate(user) → APIClient
self.authenticate_as_patient() → (client, user)
self.authenticate_as_lab_staff(lab_client_id=1) → (client, user)
self.authenticate_as_admin() → (client, user)
```

## Migrations

**All migrations were deleted and recreated from scratch (2026-02-17).**
Fresh 0001/0002 migrations exist in all apps. No legacy migration history.

## Seed Users

```bash
make seed-users   # Creates admin/doctor/patient for dev
```
| role    | email                    | password |
|---------|--------------------------|----------|
| admin   | admin@labcontrol.com     | test1234 |
| doctor  | doctor@labcontrol.com    | test1234 |
| patient | patient@labcontrol.com   | test1234 |

All: `is_active=True`, `is_verified=True`, allauth EmailAddress created.

## Commands

```bash
make up / down / restart / logs
make migrate / makemigrations / showmigrations
make seed-users          # Create dev seed users
make superuser           # Interactive superuser
make verify-email EMAIL=x@y.com
make test                # 374 tests (DJANGO_SETTINGS_MODULE=config.settings.test)
make test-coverage / test-verbose / test-fast
make throttle-reset      # Clear rate limit cache
make load_practices      # Load practice catalogue from JSON
make db-reset            # Drop + recreate DB (destroys data)
make format / lint / isort / quality
make sync-labwin         # Trigger LabWin sync manually
```

## Environment

```env
DJANGO_SECRET_KEY=...
DATABASE_URL=postgresql://labcontrol_user:password@db:5432/labcontrol_db
CELERY_BROKER_URL=redis://redis:6379/0
FRONTEND_URL=http://localhost:5173
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
```

## Doctor Import Feature

### Overview
Bulk import of doctors from CSV file using asynchronous Celery task (added 2026-04-12).

### CSV Format
```csv
NOMBRE_MEDICO,MATRICULA_O_ID
"Perez, Juan",12345
"Maria Rodriguez",MP67890
```

### Name Parsing Logic
The system handles multiple name formats:
- **"Last, First"** → first_name="First", last_name="Last"
- **"First Last"** → first_name="First", last_name="Last"
- **"Single"** → first_name="Single", last_name=""

### Import Flow
1. **Frontend**: User uploads CSV → POST `/api/v1/users/import-doctors/`
2. **Backend**:
   - Validates file is CSV
   - Reads CSV content into string
   - Starts Celery task `import_doctors_task.delay(csv_content, lab_client_id)`
   - Returns `{ task_id: "...", message: "..." }` with 202 status
3. **Frontend**: Polls GET `/api/v1/users/import-doctors/status/{task_id}/` every 2 seconds
4. **Task**:
   - Parses CSV row by row
   - Updates progress every 100 rows
   - Creates doctors with:
     - `role='doctor'`
     - `is_active=True`
     - `is_verified=True` (no email verification required)
     - `email=None` (doctors don't need email)
     - `matricula` from CSV
   - Skips duplicates (checks existing matricula)
5. **Completion**: Returns `{ created: N, skipped: M, errors: [...] }`

### Key Design Decisions

1. **Doctors Don't Require Email**
   - Matricula is the unique identifier for doctors
   - Email is optional (`blank=True, null=True` in User model)
   - Doctors are auto-verified (`is_verified=True`)
   - No password setup email sent

2. **Async Processing with Celery**
   - Large CSV files (1000+ rows) need async processing
   - Celery task runs in background
   - Frontend polls for status every 2 seconds
   - Task updates progress every 100 rows

3. **Error Handling**
   - Skip rows with missing NOMBRE_MEDICO or MATRICULA_O_ID
   - Skip duplicate matriculas (idempotent)
   - Collect errors with row number for user feedback
   - Task completes even with errors

4. **Celery Worker Restart Required**
   - When adding new Celery tasks, worker must be restarted
   - `docker-compose restart celery_worker`
   - Worker loads tasks on startup, doesn't hot-reload

### Files Modified
- **Backend**:
  - `apps/users/views.py` - ImportDoctorsView, ImportDoctorsStatusView
  - `apps/users/tasks.py` - import_doctors_task, _parse_name helper
  - `apps/users/urls.py` - Added import endpoints
- **Frontend**:
  - `src/api/users.js` - importDoctors(), getImportStatus()
  - `src/views/admin/PatientsView.vue` - Import button, modal, polling
  - `src/i18n/es.yaml` - Import translations

### Testing Locally
```bash
# 1. Ensure Celery worker is running
docker-compose ps | grep celery_worker

# 2. If worker was started before task was added, restart it
docker-compose restart celery_worker

# 3. Verify task is registered
docker logs labcontrol_celery_worker | grep "import_doctors_task"

# 4. Test import via UI or API
curl -X POST http://localhost:8000/api/v1/users/import-doctors/ \
  -H "Authorization: Bearer <token>" \
  -F "file=@doctors.csv"
```

## LabWin Sync Feature

### Overview
Nightly automated sync of lab results from LabWin Firebird database to LabControl (added 2026-04-12).

### Architecture
New Django app: `apps/labwin_sync/`
- **Connector abstraction**: Swappable mock/real Firebird connector
- **Mock connector**: In-memory sample data for dev/tests (no Firebird dependency)
- **Real connector**: Uses `firebirdsql` (pure Python) to connect to LabWin Firebird 2.x
- **Data mappers**: Transform LabWin rows to LabControl model fields
- **SyncLog/SyncedRecord models**: Track sync runs and map records for deduplication

### LabWin Database (Firebird 2.x)
Key tables: `PACIENTES` (patient orders), `DETERS` (practices/results per order),
`MEDICOS` (doctors), `NOMEN` (practice definitions).

Results stored as pipe-delimited strings in `DETERS.RESULT_FLD`:
- Simple: `"92"` (glucose)
- Multi-value: `"79|4790|137|39|242000"` (hemogram)

### Data Mapping
| LabWin | LabControl | Matching Key |
|--------|-----------|--------------|
| PACIENTES | User (role=patient) | `dni` = `HCLIN_FLD` |
| MEDICOS | User (role=doctor) | `matricula` = `MATNAC_FLD` |
| NOMEN | Practice | `code` = `ABREV_FLD` |
| DETERS | Study | `protocol_number` = `"LW-{NUMERO}-{ABREV}"` |

### Sync Flow
1. Celery Beat triggers `sync_labwin_results` task nightly at 2 AM
2. Task reads cursor from last successful SyncLog
3. Connects to LabWin via connector factory (mock or real)
4. Fetches validated DETERS in batches of 500
5. Creates/updates patients, doctors, practices, studies (idempotent)
6. Stores raw RESULT_FLD in Study.results
7. Updates SyncLog with counts and cursor

### Configuration
```env
LABWIN_USE_MOCK=True          # Set False for production
LABWIN_FDB_HOST=localhost     # LabWin Firebird host
LABWIN_FDB_PORT=3050
LABWIN_FDB_DATABASE=          # Path to .fdb file on Firebird server
LABWIN_FDB_USER=SYSDBA
LABWIN_FDB_PASSWORD=masterkey
LABWIN_SYNC_BATCH_SIZE=500
LABWIN_DEFAULT_LAB_CLIENT_ID=1
```

### Management Command
```bash
python manage.py sync_labwin              # Incremental sync
python manage.py sync_labwin --full       # Full sync (ignore cursor)
python manage.py sync_labwin --use-celery # Run via Celery worker
```

### Key Files
- `apps/labwin_sync/tasks.py` - sync_labwin_results Celery task
- `apps/labwin_sync/connectors/` - Connector abstraction (base, firebird, mock)
- `apps/labwin_sync/mappers.py` - Data mapping logic
- `apps/labwin_sync/models.py` - SyncLog, SyncedRecord
- `apps/studies/models.py` - Practice.code field added for LabWin ABREV_FLD

### Future Phases
- **Phase 2**: Replace mock with real Firebird credentials from lab
- **Phase 3**: Parse pipe-delimited RESULT_FLD into UserDetermination records
  (requires RESULTS template table from LabWin)

## Deployment (Staging)

**Server**: Hostinger VPS `72.60.137.226`, port `8443` (HTTPS)
**Domain**: `labmolecuar-portal-clientes-staging.com`
**App Location**: `/opt/labcontrol/`
**User**: `deploy@72.60.137.226`
**Containers**: web, nginx, db, redis, celery_worker, celery_beat

### Deploy Backend
```bash
# Rsync code (EXCLUDE .env.production to avoid overwriting server secrets)
rsync -avz --exclude='.env.production' --exclude='__pycache__' . deploy@72.60.137.226:/opt/labcontrol/

# Build & restart on server
ssh deploy@72.60.137.226 "cd /opt/labcontrol && \
  docker compose -f docker-compose.prod.yml build web celery_worker celery_beat && \
  docker compose -f docker-compose.prod.yml up -d --force-recreate web celery_worker celery_beat && \
  docker compose -f docker-compose.prod.yml exec web python manage.py migrate"
```

### Deploy Frontend
```bash
cd ../labcontrol-frontend && npm run build
scp -r dist/* deploy@72.60.137.226:/opt/labcontrol/frontend/dist/
ssh deploy@72.60.137.226 "docker restart labcontrol_nginx"
```

### Important Deployment Notes
- **NEVER rsync `.env.production`** — it overwrites server credentials with local template
- **Rebuild ALL celery images** when adding new tasks — celery_worker and celery_beat use separate Docker images
- Backup exists at `/opt/labcontrol/backups/2026-03-22-working-config/`

## Known Issues

**None** - All features working, 374/374 tests passing.

---
*AI Context File — update after major changes*
