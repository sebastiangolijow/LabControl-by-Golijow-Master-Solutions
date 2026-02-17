# LabControl Backend - AI Context

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
│   ├── models.py   # Practice, Determination, Study, UserDetermination
│   ├── views.py    # Study CRUD, upload/download results
│   ├── serializers.py
│   ├── filters.py
│   ├── managers.py
│   └── management/commands/load_practices.py
├── appointments/   # Appointment scheduling
├── payments/       # Payment processing
├── notifications/  # Notifications (email/in-app, Celery tasks)
├── analytics/      # Analytics and reporting
└── core/           # BaseModel, BaseManager, RBAC utilities

config/
├── settings/       # base, dev, test, prod
├── celery.py
└── urls.py

tests/              # 277 tests, 82% coverage
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
make test                # 277 tests (DJANGO_SETTINGS_MODULE=config.settings.test)
make test-coverage / test-verbose / test-fast
make throttle-reset      # Clear rate limit cache
make load_practices      # Load practice catalogue from JSON
make db-reset            # Drop + recreate DB (destroys data)
make format / lint / isort / quality
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

## Known Issues

**None** - All features working, 277/277 tests passing.

---
*AI Context File — update after major changes*
