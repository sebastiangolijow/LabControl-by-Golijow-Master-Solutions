# LabControl - Claude Context File

**Last Updated:** 2025-11-29 (Updated: Celery Beat fix)
**Project Status:** Production-grade foundation complete, Celery fully configured
**Current Phase:** Core infrastructure implemented with TDD approach

---

## Project Overview

**LabControl** is a production-grade multi-client medical laboratory management system. This is NOT a hobby project - every decision must be production-ready from day one.

### Business Context
- **Multi-tenant SaaS**: Multiple laboratory clients on a single platform
- **Medical Data**: Handles PII and sensitive medical information (HIPAA considerations)
- **Scalability**: Designed to be replicated across multiple laboratories
- **Security-First**: UUID primary keys, audit trails, role-based access control

### Core Domain
Medical laboratory operations including:
- **Studies**: Medical tests/examinations (blood tests, X-rays, MRIs, etc.)
- **Appointments**: Scheduling for sample collection and test procedures
- **Payments**: Billing and payment processing for lab services
- **Notifications**: Patient and staff communication system
- **User Management**: Multi-role system (admin, lab_manager, lab_staff, doctor, patient)

---

## Technology Stack

### Backend (Current Focus)
- **Python 3.11+** with **Django 4.2 LTS**
- **Django REST Framework** for API development
- **PostgreSQL 15** as primary database
- **Celery** for background tasks
- **Redis** for caching and Celery broker
- **django-simple-history** for audit trails
- **django-allauth** for authentication

### Infrastructure
- **Docker & Docker Compose** for containerization
- **Nginx** as reverse proxy
- **Gunicorn** as WSGI server
- **Google Cloud Platform (GCP)** for production deployment

### Frontend (Future)
- **Vue.js 3** with TypeScript
- **Pinia** for state management
- **Tailwind CSS** for styling

### Development Tools
- **Black** for code formatting
- **pytest** with pytest-django for testing
- **pytest-cov** for coverage reporting
- **flake8** for linting
- **pre-commit** hooks

---

## Architecture & Patterns

### Project Structure
```
labcontrol/
├── apps/                           # Django applications
│   ├── core/                       # Core utilities and base classes ✅
│   │   ├── models.py              # Base model mixins
│   │   ├── managers.py            # Custom managers
│   │   ├── querysets.py           # Query optimization utilities
│   │   └── events.py              # Event system
│   ├── users/                      # User management ✅
│   ├── studies/                    # Medical studies/tests ✅ (UPDATED)
│   ├── appointments/               # Scheduling ⚠️ (needs update)
│   ├── payments/                   # Billing ⚠️ (needs update)
│   └── notifications/              # Messaging ⚠️ (needs update)
├── config/                         # Django settings
│   ├── settings/
│   │   ├── base.py                # Common settings
│   │   ├── dev.py                 # Development settings
│   │   ├── prod.py                # Production settings
│   │   └── test.py                # Test settings ✅
│   ├── urls.py
│   └── wsgi.py
├── tests/                          # Test suite
│   ├── base.py                    # BaseTestCase with factories ✅
│   └── test_*.py                  # Test files
├── requirements/
│   ├── base.txt
│   ├── dev.txt
│   └── prod.txt
├── docker-compose.yml
├── Dockerfile
├── Dockerfile.dev
├── Makefile
├── pytest.ini
├── IMPROVEMENTS.md                # Production patterns documentation ✅
├── CELERY_SETUP.md                # Celery & Celery Beat guide ✅
└── claude.md                      # This file (AI context) ✅
```

### Design Patterns Implemented

#### 1. Base Model Mixins (DRY Principle)
Located in `apps/core/models.py`:

- **TimeStampedModel**: Auto-managed `created_at` and `updated_at` fields
- **UUIDModel**: UUID field (`uuid`) as unique identifier (security)
- **CreatedByModel**: Tracks who created each record (`created_by`)
- **SoftDeletableModel**: Soft delete with `is_deleted` and `deleted_at`
- **BaseModel**: Combines TimeStamped + UUID + CreatedBy
- **LabClientModel**: Multi-tenant support via `lab_client_id`
- **FullBaseModel**: All features combined

**Usage Pattern:**
```python
from apps.core.models import BaseModel, LabClientModel

class MyModel(BaseModel, LabClientModel):
    """Inherits: uuid, created_at, updated_at, created_by, lab_client_id"""
    name = models.CharField(max_length=200)
    # ... your custom fields
```

#### 2. Custom Managers & QuerySets
Located in `apps/core/managers.py`:

- **SoftDeletableQuerySet**: Methods like `active()`, `deleted()`, `delete()` (soft), `hard_delete()`
- **SoftDeletableManager**: Manager for soft-deletable models
- **LabClientQuerySet**: Multi-tenant methods `for_lab()`, `for_user_lab()`
- **LabClientManager**: Manager for multi-tenant models

**Domain-Specific Managers** (e.g., `apps/studies/managers.py`):
```python
class StudyQuerySet(LabClientQuerySet):
    def pending(self):
        return self.filter(status="pending")

    def completed(self):
        return self.filter(status="completed")

    def for_patient(self, patient):
        return self.filter(patient=patient)

class StudyManager(LabClientManager):
    def get_queryset(self):
        return StudyQuerySet(self.model, using=self._db)

    def pending(self):
        return self.get_queryset().pending()
```

#### 3. Query Optimization (Avoiding N+1)
Located in `apps/core/querysets.py`:

- **SubqueryCount**: Efficient COUNT without GROUP BY
- **SubquerySum**: Efficient SUM aggregation
- **SubqueryMax/Min/Avg**: Additional aggregation helpers

**Usage Pattern:**
```python
from apps.core.querysets import SubqueryCount
from django.db.models import OuterRef

studies = Study.objects.annotate(
    appointment_count=SubqueryCount(
        Appointment.objects.filter(study=OuterRef('pk'))
    )
)
```

#### 4. Event-Driven Architecture
Located in `apps/core/events.py`:

- **EventRegistry**: Centralized event registration
- **BaseEvent**: Base class for async events (Celery-backed)

**Usage Pattern:**
```python
from apps.core.events import BaseEvent, EventRegistry

@EventRegistry.register("study.completed")
class StudyCompletedEvent(BaseEvent):
    @classmethod
    def handle(cls, payload):
        # Send notification
        # Update dashboard
        # Trigger billing
        pass

# Trigger event
StudyCompletedEvent(study_id=123, patient_id=456).trigger()
```

#### 5. Comprehensive Test Infrastructure
Located in `tests/base.py`:

**BaseTestCase** provides:
- **User Factories**: `create_user()`, `create_admin()`, `create_lab_manager()`, `create_lab_staff()`, `create_doctor()`, `create_patient()`
- **Model Factories**: `create_study_type()`, `create_study()`, `create_appointment()`, `create_payment()`, `create_notification()`
- **Authentication Helpers**: `authenticate_as_patient()`, `authenticate_as_admin()`, etc.
- **Custom Assertions**: `assertUUID()`, `assertTimestampRecent()`

**Usage Pattern:**
```python
from tests.base import BaseTestCase

class TestMyFeature(BaseTestCase):
    def test_something(self):
        # Use factories
        patient = self.create_patient()
        study = self.create_study(patient=patient)

        # Authenticate
        client, user = self.authenticate_as_patient()

        # Custom assertions
        self.assertUUID(study.uuid)
        self.assertTimestampRecent(study.created_at)
```

#### 6. Audit Trail with django-simple-history
Automatically tracks all changes to models:

```python
from simple_history.models import HistoricalRecords

class Study(BaseModel, LabClientModel):
    # ... fields
    history = HistoricalRecords()
```

Access history:
```python
study = Study.objects.get(id=123)
history = study.history.all()  # All changes
latest = study.history.first()  # Most recent change
```

---

## Current Implementation Status

### ✅ Completed Apps

#### `apps/core/` - Core Utilities
**Status:** Complete and production-ready
**Contains:**
- Base model mixins (TimeStampedModel, UUIDModel, etc.)
- Custom managers (SoftDeletableManager, LabClientManager)
- Query optimization utilities (SubqueryCount, SubquerySum, etc.)
- Event system (EventRegistry, BaseEvent)

#### `apps/users/` - User Management
**Status:** Basic implementation complete
**Models:**
- **User** (custom user model)
  - Roles: admin, lab_manager, lab_staff, doctor, patient
  - Multi-tenant support via `lab_client_id`
  - Email-based authentication

**TODO:**
- Apply BaseModel mixins
- Add custom managers
- Create comprehensive tests with BaseTestCase

#### `apps/studies/` - Medical Studies/Tests
**Status:** Updated with production-grade patterns ✅
**Models:**

1. **StudyType** (inherits BaseModel)
   - Fields: name, code, description, category, base_price
   - Requirements: requires_fasting, preparation_instructions
   - Processing: estimated_processing_hours
   - Status: is_active
   - Manager: StudyTypeManager with `active()`, `by_category()`

2. **Study** (inherits BaseModel + LabClientModel)
   - Relationships: patient, study_type, ordered_by
   - Details: order_number, status (pending/sample_collected/in_progress/completed/cancelled)
   - Sample: sample_id, sample_collected_at
   - Results: results, results_file, completed_at
   - Notes: notes, internal_notes
   - Manager: StudyManager with `pending()`, `completed()`, `for_patient()`
   - Audit: HistoricalRecords enabled

**Tests:** Comprehensive test coverage in `tests/test_studies.py`
- Model tests (UUID, timestamps, audit trail)
- Custom manager tests
- Multi-tenant isolation tests
- API endpoint tests
- Role-based access control tests

### ⚠️ Apps Needing Updates

#### `apps/appointments/` - Scheduling
**Status:** Initial structure exists, needs production-grade patterns
**TODO:**
- Apply BaseModel and LabClientModel
- Create custom managers (AppointmentManager)
- Add audit trail with HistoricalRecords
- Create comprehensive tests with BaseTestCase
- Add domain-specific query methods

#### `apps/payments/` - Billing
**Status:** Initial structure exists, needs production-grade patterns
**TODO:**
- Apply BaseModel and LabClientModel
- Create custom managers (PaymentManager, InvoiceManager)
- Add audit trail with HistoricalRecords
- Create comprehensive tests with BaseTestCase
- Add payment-specific query methods (pending_payments, overdue_invoices, etc.)

#### `apps/notifications/` - Messaging
**Status:** Initial structure exists, needs production-grade patterns
**TODO:**
- Apply BaseModel and LabClientModel
- Create custom managers (NotificationManager)
- Add audit trail with HistoricalRecords
- Create comprehensive tests with BaseTestCase
- Integrate with event system for automatic notifications

---

## Database Schema

### Key Fields Inherited from Base Models

All models inheriting from `BaseModel` get:
- `uuid` (UUIDField, unique, indexed)
- `created_at` (DateTimeField, auto_now_add)
- `updated_at` (DateTimeField, auto_now)
- `created_by` (ForeignKey to User, nullable)

All models inheriting from `LabClientModel` get:
- `lab_client_id` (IntegerField, indexed for multi-tenant queries)

### User Model
```python
User:
    - id (AutoField, primary key)
    - email (EmailField, unique)
    - first_name, last_name
    - phone_number
    - role (CharField: admin/lab_manager/lab_staff/doctor/patient)
    - lab_client_id (IntegerField, null for admins)
    - is_active, is_staff, is_superuser
    - date_joined
```

### Study Models
```python
StudyType (BaseModel):
    - uuid, created_at, updated_at, created_by (inherited)
    - name, code (unique), description, category
    - base_price
    - requires_fasting, preparation_instructions
    - estimated_processing_hours
    - is_active

Study (BaseModel + LabClientModel):
    - uuid, created_at, updated_at, created_by, lab_client_id (inherited)
    - patient (FK to User)
    - study_type (FK to StudyType)
    - ordered_by (FK to User)
    - order_number (unique)
    - status (pending/sample_collected/in_progress/completed/cancelled)
    - sample_id, sample_collected_at
    - results, results_file, completed_at
    - notes, internal_notes
    - history (HistoricalRecords)
```

### Indexes
Key indexes for performance:
- `Study.order_number`
- `Study.patient + Study.status` (composite)
- `Study.lab_client_id` (multi-tenant queries)
- All UUID fields (inherited from UUIDModel)

---

## Testing Strategy

### Test Configuration
- **Settings:** `config/settings/test.py`
- **Database:** In-memory SQLite for speed
- **Migrations:** Disabled with `--nomigrations`
- **Password Hashing:** MD5 (fast, test-only)
- **Celery:** Synchronous execution (`CELERY_TASK_ALWAYS_EAGER = True`)

### Running Tests
```bash
# Run all tests
pytest

# Run specific app
pytest tests/test_studies.py

# Run with coverage
pytest --cov=apps --cov-report=html

# Run in Docker
docker-compose exec web pytest
```

### Test Organization
```python
tests/
├── base.py                    # BaseTestCase with factories
├── test_studies.py            # Study app tests
├── test_appointments.py       # Appointment tests (TODO)
├── test_payments.py           # Payment tests (TODO)
└── test_notifications.py     # Notification tests (TODO)
```

### Test Coverage Goals
- **Unit Tests:** All models, managers, querysets
- **Integration Tests:** API endpoints with authentication
- **Multi-tenant Tests:** Data isolation between labs
- **RBAC Tests:** Role-based access control
- **Audit Trail Tests:** History tracking verification

---

## Development Workflow

### Setting Up Development Environment
```bash
# Clone repository
git clone <repo-url>
cd labcontrol

# Copy environment file
cp .env.example .env

# Start with Docker
docker-compose up -d

# Run migrations
docker-compose exec web python manage.py migrate

# Create superuser
docker-compose exec web python manage.py createsuperuser

# Run tests
docker-compose exec web pytest
```

### Common Commands (via Makefile)
```bash
make build          # Build Docker images
make up             # Start containers
make down           # Stop containers
make shell          # Django shell
make migrate        # Run migrations
make makemigrations # Create migrations
make test           # Run tests
make test-coverage  # Run tests with coverage
make lint           # Run flake8
make format         # Run black
```

### Code Style
- **Black** for Python formatting (line length: 88)
- **flake8** for linting
- **isort** for import sorting
- Follow Django naming conventions
- Docstrings for all classes and public methods

---

## Key Design Decisions & Rationale

### 1. UUID Primary Keys
**Decision:** Use UUID fields instead of auto-increment integers
**Rationale:**
- Prevents enumeration attacks (security)
- Safe for distributed systems
- No ID collisions when merging data
- Harder to guess/scrape data

### 2. Multi-Tenant via lab_client_id
**Decision:** Use `lab_client_id` column instead of separate databases
**Rationale:**
- Simpler infrastructure (one database)
- Easier migrations and updates
- Lower cost at scale
- Enforced via custom managers

**Trade-off:** Must be careful with queries to prevent data leakage

### 3. Soft Delete by Default
**Decision:** Use `is_deleted` flag instead of hard deletes
**Rationale:**
- Preserves audit trail
- Allows "undo" functionality
- Regulatory compliance (medical data)
- Can still hard delete if needed

### 4. Custom Managers for Domain Logic
**Decision:** Use custom managers instead of putting logic in views
**Rationale:**
- Reusable across views/serializers/tasks
- Testable in isolation
- Chainable query methods
- Cleaner views/viewsets

### 5. Event System for Decoupling
**Decision:** Use event-driven architecture for cross-app communication
**Rationale:**
- Loose coupling between apps
- Async execution via Celery
- Easy to add new event handlers
- Clearer business logic flow

### 6. django-simple-history for Audit
**Decision:** Use simple-history instead of custom audit solution
**Rationale:**
- Battle-tested library
- Automatic tracking
- Easy to query history
- Minimal performance impact
- Required for medical data compliance

---

## Security Considerations

### Authentication & Authorization
- Email-based authentication (django-allauth)
- Role-based access control (RBAC) via User.role
- JWT tokens for API authentication (planned)
- Multi-tenant data isolation enforced at manager level

### Data Protection
- UUID primary keys (no enumeration)
- Soft delete preserves audit trail
- Historical records for all changes
- Encrypted database connections in production
- Environment variables for secrets

### API Security
- DRF permission classes for all endpoints
- Throttling on sensitive endpoints
- CORS configuration for frontend
- HTTPS only in production

---

## Production Deployment Checklist

### Pre-Deployment
- [ ] All tests passing
- [ ] Coverage > 80%
- [ ] Migrations applied and tested
- [ ] Environment variables configured
- [ ] Static files collected
- [ ] Media files storage configured (GCP bucket)
- [ ] Database backups configured
- [ ] Celery workers running
- [ ] Redis configured and secured

### Monitoring
- [ ] Error tracking (Sentry)
- [ ] Performance monitoring (APM)
- [ ] Database query monitoring
- [ ] Celery task monitoring
- [ ] Log aggregation
- [ ] Uptime monitoring

### Security
- [ ] SECRET_KEY rotated
- [ ] DEBUG = False
- [ ] ALLOWED_HOSTS configured
- [ ] SSL/TLS certificates
- [ ] Database credentials secured
- [ ] API rate limiting enabled
- [ ] Security headers configured

---

## Next Steps & Roadmap

### Immediate (Current Sprint)
1. **Verify Current Implementation**
   - Run all tests to ensure production patterns work
   - Check migrations are created correctly
   - Verify Docker setup is working

2. **Apply Patterns to Remaining Apps**
   - Update `apps/appointments/` with BaseModel, managers, tests
   - Update `apps/payments/` with BaseModel, managers, tests
   - Update `apps/notifications/` with BaseModel, managers, tests
   - Update `apps/users/` with enhanced patterns

### Short-term (Next 2-4 Weeks)
1. **API Development**
   - Complete DRF viewsets for all models
   - Add pagination, filtering, search
   - Implement JWT authentication
   - Add API documentation (drf-spectacular)

2. **Business Logic**
   - Study workflow automation
   - Appointment scheduling logic
   - Payment processing integration
   - Notification triggers via events

3. **Admin Interface**
   - Customize Django Admin for all models
   - Add inline editing
   - Custom actions (bulk operations)
   - Historical records in admin

### Medium-term (1-2 Months)
1. **Frontend Development**
   - Vue.js 3 + TypeScript setup
   - Authentication flow
   - Dashboard for each role
   - Study management interface
   - Appointment calendar
   - Payment processing UI

2. **Integrations**
   - Payment gateway (Stripe/PayPal)
   - Email service (SendGrid/AWS SES)
   - SMS notifications (Twilio)
   - File storage (GCP Cloud Storage)
   - Lab equipment integrations

### Long-term (3-6 Months)
1. **Advanced Features**
   - Reporting and analytics
   - Multi-language support (i18n)
   - Mobile app (React Native)
   - Telemedicine integration
   - AI-powered result analysis

2. **Scale & Performance**
   - Database query optimization
   - Caching strategy (Redis)
   - CDN for static assets
   - Load balancing
   - Horizontal scaling

---

## Important Context from Development

### Learning from Production Backends
This project was built by analyzing two real production backends:
1. **core-backend** (Investment platform): Provided patterns for KYC, audit trails, simple-history usage
2. **market** (B2B marketplace): Provided patterns for base mixins, query optimization, event system, test infrastructure

Key takeaway: **All patterns implemented are battle-tested in production environments handling millions of requests.**

### Development Approach
- **TDD (Test-Driven Development)**: Write tests first, then implement
- **Production-First**: Every decision considers production requirements
- **DRY Principle**: Reusable base classes, managers, factories
- **Clean Architecture**: Clear separation of concerns
- **Documentation**: Code is self-documenting + comprehensive docs

### Known Limitations
1. **Docker Required:** Current setup assumes Docker for development
2. **Migrations:** Core app migrations need to be created (`makemigrations`) and run
3. **Periodic Tasks:** Need to run `setup_periodic_tasks` command after migrations
4. **API Not Complete:** ViewSets exist but need enhancement
5. **Frontend Not Started:** Backend-focused for now

### Recent Fixes (2025-11-29)
1. **Celery Beat Configuration**: Fixed conflict between hardcoded `beat_schedule` and `DatabaseScheduler`
   - Removed hardcoded periodic tasks from `config/celery.py`
   - Created `setup_periodic_tasks` management command for easy setup
   - Created comprehensive `CELERY_SETUP.md` documentation
   - Now properly uses django-celery-beat for database-backed scheduling

---

## How to Use This File

### For Claude in Future Sessions
1. **Read this file first** to understand project context
2. **Check "Current Implementation Status"** to see what's done
3. **Review "Next Steps"** to understand priorities
4. **Follow established patterns** when implementing new features
5. **Update this file** whenever making significant changes

### Update Triggers
Update this file when:
- ✅ Completing a major feature
- ✅ Adding new apps or models
- ✅ Changing architecture decisions
- ✅ Updating dependencies
- ✅ Implementing new patterns
- ✅ Discovering important context

### Sections to Keep Current
- **Last Updated** date at top
- **Current Implementation Status** (✅, ⚠️ status markers)
- **Next Steps & Roadmap**
- **Database Schema** (as models evolve)
- **Known Limitations**

---

## Quick Reference Commands

### Development
```bash
# Start project
docker-compose up -d

# View logs
docker-compose logs -f web

# Django shell
docker-compose exec web python manage.py shell

# Database shell
docker-compose exec web python manage.py dbshell

# Create migrations
docker-compose exec web python manage.py makemigrations

# Apply migrations
docker-compose exec web python manage.py migrate

# Create superuser
docker-compose exec web python manage.py createsuperuser

# Setup periodic tasks for Celery Beat
docker-compose exec web python manage.py setup_periodic_tasks
```

### Celery & Background Tasks
```bash
# View Celery worker logs
docker-compose logs -f celery_worker

# View Celery beat logs
docker-compose logs -f celery_beat

# Restart Celery services
docker-compose restart celery_worker celery_beat

# Access Flower monitoring dashboard
open http://localhost:5555

# Check active tasks
docker-compose exec celery_worker celery -A config inspect active

# Check registered tasks
docker-compose exec celery_worker celery -A config inspect registered
```

### Testing
```bash
# All tests
docker-compose exec web pytest

# Specific app
docker-compose exec web pytest tests/test_studies.py

# With coverage
docker-compose exec web pytest --cov=apps --cov-report=html

# Verbose
docker-compose exec web pytest -v

# Stop on first failure
docker-compose exec web pytest -x
```

### Code Quality
```bash
# Format code
docker-compose exec web black apps/ tests/

# Lint code
docker-compose exec web flake8 apps/ tests/

# Sort imports
docker-compose exec web isort apps/ tests/
```

---

## Contact & Resources

### Project Resources
- **Repository:** (To be added)
- **Documentation:**
  - `IMPROVEMENTS.md` - Production patterns and migration guide
  - `CELERY_SETUP.md` - Celery & Celery Beat complete guide
  - `README.md` - Project overview and quick start
- **Issue Tracker:** (To be added)

### Key Documentation Links
- [Django 4.2 Documentation](https://docs.djangoproject.com/en/4.2/)
- [Django REST Framework](https://www.django-rest-framework.org/)
- [django-simple-history](https://django-simple-history.readthedocs.io/)
- [Celery Documentation](https://docs.celeryq.dev/)

---

**Note:** This file is maintained for AI assistants (Claude) to maintain context across sessions. Keep it updated and comprehensive.
