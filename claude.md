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
│   ├── models.py   # User (UUID PK, roles: patient/doctor/lab_staff/lab_manager/admin)
│   ├── views.py    # User CRUD, doctor/patient search, create user
│   ├── serializers.py # UserSerializer, UserDetailSerializer, UserCreateSerializer
│   └── permissions.py # IsAdminUser, IsLabManager, etc.
├── studies/        # Lab studies and results
│   ├── models.py   # Study, StudyType (ordered_by FK to User)
│   ├── views.py    # Study CRUD, upload/download results
│   ├── serializers.py # StudySerializer (ordered_by_name computed field)
│   └── managers.py # Active studies manager
├── appointments/   # Appointment scheduling
├── payments/       # Payment processing
├── notifications/  # Notifications (email/in-app)
│   └── tasks.py    # Celery tasks (send_password_setup_email)
├── analytics/      # Analytics and reporting
└── core/           # Base models, mixins, utilities
    ├── models.py   # BaseModel (UUID, soft delete, audit)
    ├── managers.py # ActiveManager
    └── permissions.py # RBAC utilities

config/
├── settings/       # Settings (base, dev, test, prod)
├── celery.py       # Celery configuration
└── urls.py         # URL routing

tests/              # Test suite (261 tests, 82.73% coverage)
└── test_doctor_features.py # 25 doctor-specific tests
```

## Models

### User (apps/users/models.py)
```python
class User(AbstractBaseUser, PermissionsMixin, BaseModel):
    # UUID primary key (from BaseModel)
    email = EmailField(unique=True)
    role = CharField(choices=ROLE_CHOICES)  # patient, doctor, lab_staff, lab_manager, admin
    first_name, last_name, phone_number, dni, birthday
    gender, location, direction  # New fields
    mutual_code, mutual_name, carnet  # Insurance fields
    is_active, is_staff, is_superuser
    email_verified, lab_client (FK)
```

### Study (apps/studies/models.py)
```python
class Study(BaseModel):
    # UUID primary key
    patient = FK(User, related_name='studies')
    study_type = FK(StudyType)
    ordered_by = FK(User, null=True, blank=True, related_name='ordered_studies')
    # ^^^ Must be doctor role (validated in clean())
    status = CharField(choices=STATUS_CHOICES)
    results_file, results_text
    created_at, completed_at
    lab_client (FK)

    def clean(self):
        if self.ordered_by and self.ordered_by.role != 'doctor':
            raise ValidationError("ordered_by must be doctor")
```

## API Endpoints

### Authentication
```
POST   /api/v1/auth/login/          # Login (returns access + refresh tokens)
POST   /api/v1/auth/logout/         # Logout
POST   /api/v1/auth/token/refresh/  # Refresh access token
GET    /api/v1/auth/user/           # Get current user
PATCH  /api/v1/auth/user/           # Update user profile
```

### Users
```
POST   /api/v1/users/create-user/       # Create user (admin only)
GET    /api/v1/users/search-doctors/    # Search doctors (admin/lab_manager)
GET    /api/v1/users/search-patients/   # Search patients (admin/lab_manager)
GET    /api/v1/users/                   # List users (admin only)
GET    /api/v1/users/{id}/              # Get user (admin only)
PATCH  /api/v1/users/{id}/              # Update user (admin only)
DELETE /api/v1/users/{id}/              # Delete user (admin only)
```

### Studies
```
GET    /api/v1/studies/                     # List studies (filtered by role)
GET    /api/v1/studies/{id}/                # Get study
POST   /api/v1/studies/{id}/upload_result/  # Upload result (admin/staff)
GET    /api/v1/studies/{id}/download_result/# Download PDF
DELETE /api/v1/studies/{id}/delete-result/  # Delete result (admin)
DELETE /api/v1/studies/{id}/                # Soft delete study
```

## Key Patterns

### UUID Primary Keys
```python
# ✓ ALWAYS use .pk (works with any PK type)
user.pk
study.pk
Count("pk", filter=Q(...))

# ✗ NEVER use .id (fails with UUID)
user.id          # AttributeError
Count("id")      # FieldError
```

### Permissions
```python
# views.py
class UserViewSet(viewsets.ModelViewSet):
    @action(detail=False, methods=['get'], permission_classes=[IsAdminOrLabManager])
    def search_doctors(self, request):
        # Multi-tenant filtering
        qs = User.objects.filter(role='doctor', lab_client=request.user.lab_client)
        return Response(...)
```

### Multi-Tenant Filtering
```python
# All queries filtered by lab_client
User.objects.filter(lab_client=request.user.lab_client)
Study.objects.filter(patient__lab_client=request.user.lab_client)
```

### Serializers
```python
class StudySerializer(ModelSerializer):
    ordered_by_name = SerializerMethodField()

    def get_ordered_by_name(self, obj):
        if obj.ordered_by:
            return f"{obj.ordered_by.first_name} {obj.ordered_by.last_name}"
        return None
```

### Celery Tasks
```python
# apps/notifications/tasks.py
@shared_task(bind=True, max_retries=3)
def send_password_setup_email(self, user_id, reset_token):
    try:
        user = User.objects.get(pk=user_id)  # Note: .pk not .id
        send_mail(...)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)
```

## Tests

```bash
make test                # Run all tests (261 tests)
make test-coverage       # With coverage report (82.73%)
make test-verbose        # Verbose output
make test-fast           # No coverage (quick)
make throttle-reset      # Clear rate limit cache
```

### Test Structure
```python
from tests.base import BaseTestCase

class TestDoctorFeatures(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.doctor = self.create_user(role='doctor')
        self.study = self.create_study(ordered_by=self.doctor)

    def test_ordered_by_validation(self):
        # Doctor validation
        patient = self.create_user(role='patient')
        with self.assertRaises(ValidationError):
            study = Study(ordered_by=patient)
            study.clean()
```

## Environment

```env
# .env
DJANGO_SECRET_KEY=...
DATABASE_URL=postgresql://labcontrol_user:password@db:5432/labcontrol_db
CELERY_BROKER_URL=redis://redis:6379/0
FRONTEND_URL=http://localhost:5173
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
```

## Commands

```bash
# Docker
make up down restart logs shell

# Django
make migrate makemigrations superuser
make collectstatic setup-periodic-tasks

# Testing
make test test-coverage test-verbose test-fast

# Utilities
make throttle-reset      # Clear API rate limits
make clean db-reset

# Code Quality
make format lint isort quality

# Setup
make setup rebuild      # Initial setup / rebuild
```

## Migrations

### Recent Migrations
```
apps/users/migrations/
├── 0002_auto_*.py    # Doctor role + ordered_by field
└── 0003_auto_*.py    # New profile fields (gender, location, etc.)

apps/studies/migrations/
└── 0002_auto_*.py    # ordered_by FK to User
```

## Recent Changes (2026-01-31)

### Doctor Role Implementation
1. **User Model**:
   - Added `doctor` to ROLE_CHOICES
   - New fields: gender, location, direction, mutual_code, mutual_name, carnet

2. **Study Model**:
   - Added `ordered_by` FK (nullable, validated for doctor role)
   - `clean()` method validates doctor role

3. **Study Serializer**:
   - `ordered_by_name` computed field

4. **User Views**:
   - `create_user()` action: Creates user + sends password email
   - `search_doctors()` action: Returns doctors (multi-tenant filtered)
   - `search_patients()` action: Returns patients (multi-tenant filtered)

5. **Notifications**:
   - `send_password_setup_email` Celery task

6. **UUID Fixes** (50+ occurrences):
   - All `.id` → `.pk`
   - All `Count("id")` → `Count("pk")`
   - Test assertions: `str(obj.pk)` comparisons

7. **Tests**:
   - `tests/test_doctor_features.py`: 25 tests
   - All tests passing: 261 tests, 82.73% coverage

### Throttle Reset Command
```bash
make throttle-reset  # Clears Django cache to reset rate limits
```

## Known Issues

**None** - All features working as expected

---
*AI Context File - Keep concise, update after major changes*
