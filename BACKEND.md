# LabControl Backend - Agent Context

**Last Updated**: April 25, 2026
**Python**: 3.11
**Django**: 4.2
**Database**: PostgreSQL 15 with UUID primary keys
**Task Queue**: Celery + Redis
**API Framework**: Django REST Framework 3.x
**Test suite**: 464 passing

---

## 📋 Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture & Design Patterns](#architecture--design-patterns)
3. [Project Structure](#project-structure)
4. [Core Models & Relationships](#core-models--relationships)
5. [API Endpoints](#api-endpoints)
6. [Authentication & Permissions](#authentication--permissions)
7. [Key Patterns & Conventions](#key-patterns--conventions)
8. [Testing](#testing)
9. [Database](#database)
10. [Celery Tasks](#celery-tasks)
11. [LabWin Sync](#labwin-sync)
12. [Development Workflow](#development-workflow)
13. [Common Tasks](#common-tasks)

---

## 🎯 Project Overview

LabControl is a **multi-tenant medical laboratory management platform** that handles:

- **Patient Management**: Registration, profiles, medical history
- **Study Management**: Lab tests, practices, determinations, results
- **Appointments**: Scheduling, reminders, check-in/out
- **Payments**: Invoices, payment tracking, multiple payment methods
- **Notifications**: Email, in-app, SMS notifications
- **Analytics**: Revenue tracking, study trends, performance metrics

### Multi-Tenancy

The system supports **multiple laboratory clients** using a simple `lab_client_id` field on relevant models. Each laboratory client's data is isolated using query filters.

```python
# Example: Filter studies by lab client
Study.objects.filter(lab_client_id=request.user.lab_client_id)
```

**Note**: Full multi-tenancy with a `Company` model is planned but not yet implemented.

---

## 🏗️ Architecture & Design Patterns

### Django Apps Structure

The backend follows Django's **app-based architecture**:

- **`apps/core/`**: Base models, mixins, utilities (BaseModel, permissions, etc.)
- **`apps/users/`**: User model, authentication, registration
- **`apps/studies/`**: Lab studies, practices, determinations, results
- **`apps/appointments/`**: Appointment scheduling and management
- **`apps/payments/`**: Invoices, payments, billing
- **`apps/notifications/`**: Notification system (email, in-app, SMS)
- **`apps/analytics/`**: Dashboard, reports, metrics

### Key Design Patterns

1. **Base Model Pattern**: All models inherit from `BaseModel` or `LabClientModel` for common fields
2. **Custom Managers**: Each model has a custom manager for reusable queries
3. **UUID Primary Keys**: All models use UUIDs instead of auto-increment IDs
4. **Audit Trail**: All critical models use `django-simple-history` for change tracking
5. **Permissions**: Role-based access control (RBAC) with custom permission classes
6. **Serializers**: DRF serializers handle validation and representation
7. **ViewSets**: DRF ViewSets for RESTful CRUD operations

---

## 📁 Project Structure

```
labcontrol/
├── apps/
│   ├── core/                    # Core utilities and base classes
│   │   ├── models.py            # BaseModel, UUIDModel, LabClientModel
│   │   ├── managers.py          # Base managers
│   │   ├── permissions.py       # Custom permissions (IsAdminUser, etc.)
│   │   └── utils.py             # Helper functions
│   │
│   ├── users/                   # User management & auth
│   │   ├── models.py            # User (UUID PK, roles, profile)
│   │   ├── views.py             # Registration, login, profile
│   │   ├── serializers.py       # UserSerializer, RegisterSerializer
│   │   ├── permissions.py       # Role-based permissions
│   │   ├── managers.py          # UserManager
│   │   ├── auth_urls.py         # Auth endpoints (/auth/login, /auth/user, etc.)
│   │   ├── urls.py              # User endpoints (/users/, etc.)
│   │   └── management/commands/
│   │       ├── create_seed_users.py    # Create dev users
│   │       └── verify_email.py         # Manually verify email
│   │
│   ├── studies/                 # Lab studies & practices
│   │   ├── models.py            # Practice, Determination, Study, StudyPractice, UserDetermination
│   │   ├── views.py             # Study CRUD, upload/download results
│   │   ├── serializers.py       # Study, Practice, Determination serializers
│   │   ├── filters.py           # StudyFilter, PracticeFilter
│   │   ├── managers.py          # StudyManager, PracticeManager
│   │   ├── urls.py              # Study endpoints
│   │   └── management/commands/
│   │       └── load_practices.py       # Load practice catalog from JSON
│   │
│   ├── appointments/            # Appointment management
│   │   ├── models.py            # Appointment (status, scheduling)
│   │   ├── views.py             # Appointment CRUD
│   │   ├── serializers.py       # AppointmentSerializer
│   │   ├── managers.py          # AppointmentManager
│   │   └── urls.py
│   │
│   ├── payments/                # Billing & payments
│   │   ├── models.py            # Invoice, Payment
│   │   ├── views.py             # Invoice/Payment CRUD
│   │   ├── serializers.py       # InvoiceSerializer, PaymentSerializer
│   │   ├── managers.py          # InvoiceManager, PaymentManager
│   │   └── urls.py
│   │
│   ├── notifications/           # Notification system
│   │   ├── models.py            # Notification (in-app, email, SMS)
│   │   ├── views.py             # Notification CRUD
│   │   ├── serializers.py       # NotificationSerializer
│   │   ├── tasks.py             # Celery tasks for sending notifications
│   │   ├── managers.py          # NotificationManager
│   │   └── urls.py
│   │
│   ├── labwin_sync/             # LabWin Firebird sync + FTP PDF fetch
│   │   ├── models.py            # SyncLog, SyncedRecord
│   │   ├── tasks.py             # sync_labwin_results, fetch_ftp_pdfs, cleanup_ftp_pdfs
│   │   ├── mappers.py           # LabWin row → Django model mapping
│   │   ├── admin.py             # SyncLog/SyncedRecord admin views
│   │   ├── connectors/
│   │   │   ├── __init__.py      # get_connector() factory
│   │   │   ├── base.py          # Abstract connector interface
│   │   │   ├── firebird.py      # Real Firebird connector (firebirdsql)
│   │   │   └── mock.py          # Mock connector with sample data
│   │   ├── ftp/
│   │   │   ├── __init__.py      # get_ftp_connector() factory
│   │   │   ├── base.py          # Abstract FTP connector interface
│   │   │   ├── ftp.py           # Real FTP/FTPS connector (ftplib)
│   │   │   └── mock.py          # Mock FTP connector with sample PDFs
│   │   └── management/commands/
│   │       ├── sync_labwin.py   # Manual sync trigger
│   │       └── fetch_ftp_pdfs.py  # Manual FTP PDF fetch
│   │
│   └── analytics/               # Analytics & reporting
│       ├── views.py             # Dashboard, trends, revenue
│       ├── serializers.py       # Analytics serializers
│       └── urls.py
│
├── config/                      # Project configuration
│   ├── settings/
│   │   ├── base.py              # Common settings
│   │   ├── dev.py               # Development settings
│   │   ├── test.py              # Test settings
│   │   ├── prod.py              # Production settings
│   │   └── __init__.py
│   ├── urls.py                  # Root URL configuration
│   ├── wsgi.py                  # WSGI config for deployment
│   ├── asgi.py                  # ASGI config (future WebSocket support)
│   └── celery.py                # Celery configuration
│
├── tests/                       # Test suite (459 tests passing as of 2026-04-25)
│   ├── base.py                  # BaseTestCase with factories
│   ├── test_users.py
│   ├── test_studies.py
│   ├── test_appointments.py
│   ├── test_payments.py
│   ├── test_notifications.py
│   ├── test_analytics.py
│   └── test_labwin_sync.py
│
├── templates/                   # Email templates
│   └── emails/
│       ├── email_verification.html
│       ├── password_reset.html
│       └── password_setup.html
│
├── manage.py                    # Django management script
├── Makefile                     # Common commands
├── requirements.txt             # Python dependencies
├── Dockerfile                   # Docker image
├── docker-compose.yml           # Local development
├── docker-compose.prod.yml      # Production deployment
└── .env.example                 # Environment variables template
```

---

## 🗃️ Core Models & Relationships

### Base Models (apps/core/models.py)

All models inherit from base classes that provide common functionality:

```python
class TimeStampedModel(models.Model):
    """Provides created_at and updated_at fields"""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class UUIDModel(models.Model):
    """Provides uuid field (unique identifier)"""
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

class CreatedByModel(models.Model):
    """Tracks who created the record"""
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

class LabClientModel(models.Model):
    """Multi-tenant support"""
    uuid = models.UUIDField(default=uuid.uuid4, primary_key=True)
    lab_client_id = models.IntegerField(null=True, blank=True, db_index=True)

class BaseModel(TimeStampedModel, UUIDModel, CreatedByModel):
    """Combines all common mixins - most models inherit this"""
    pass
```

### User Model (apps/users/models.py)

**Primary Key**: `uuid` (UUIDField)

```python
class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model with role-based access control.

    Roles:
    - admin: Full system access
    - lab_staff: Lab operations (upload results, manage studies)
    - doctor: View patient studies, order tests
    - patient: View own studies and results
    """
    # Primary key (UUID)
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Authentication
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128)

    # Role & permissions
    role = models.CharField(
        max_length=20,
        choices=[
            ('admin', 'Administrator'),
            ('lab_staff', 'Laboratory Staff'),
            ('doctor', 'Doctor'),
            ('patient', 'Patient'),
        ],
        default='patient'
    )

    # Profile information
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    phone_number = models.CharField(max_length=20, blank=True)
    dni = models.CharField(max_length=20, blank=True)  # National ID
    birthday = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, blank=True)
    location = models.CharField(max_length=100, blank=True)
    direction = models.TextField(blank=True)  # Address
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True)

    # Insurance information
    mutual_code = models.CharField(max_length=50, blank=True)
    mutual_name = models.CharField(max_length=100, blank=True)
    carnet = models.CharField(max_length=50, blank=True)

    # Multi-tenant support
    lab_client_id = models.IntegerField(null=True, blank=True, db_index=True)

    # Account status
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)  # Django admin access
    is_verified = models.BooleanField(default=False)  # Email verified

    # Email verification
    verification_token = models.CharField(max_length=100, blank=True)
    verification_token_created_at = models.DateTimeField(null=True, blank=True)

    # User preferences
    language = models.CharField(
        max_length=2,
        choices=[('EN', 'English'), ('ES', 'Spanish')],
        default='ES'
    )

    # Audit trail
    created_by = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']
```

**Related Models**:
- `studies.Study` (patient → studies, ordered_by → ordered_studies)
- `appointments.Appointment` (patient → appointments)
- `payments.Invoice` (patient → invoices)
- `notifications.Notification` (user → notifications)

### Practice Model (apps/studies/models.py)

A **Practice** is a type of lab test (e.g., "Complete Blood Count", "Glucose Test").

```python
class Practice(BaseModel):
    """
    Laboratory practice/test definition.

    Defines what tests are available, their cost, turnaround time, etc.
    """
    name = models.CharField(max_length=200)  # e.g., "Complete Blood Count"
    code = models.CharField(max_length=20, blank=True, db_index=True)  # LabWin ABREV_FLD (e.g., "HEMC")
    technique = models.CharField(max_length=200, blank=True)  # e.g., "Flow Cytometry"
    sample_type = models.CharField(max_length=100, blank=True)  # e.g., "Blood"
    sample_quantity = models.CharField(max_length=100, blank=True)  # e.g., "5ml"
    price = models.DecimalField(max_digits=10, decimal_places=2)
    delay_days = models.IntegerField(default=0)  # Turnaround time
    is_active = models.BooleanField(default=True)

    # Many-to-many with Determination (individual measurements)
    determinations = models.ManyToManyField('Determination', blank=True, related_name='practices')
```

### Determination Model (apps/studies/models.py)

A **Determination** is an individual measurement within a practice (e.g., "Hemoglobin", "WBC Count").

```python
class Determination(BaseModel):
    """
    Individual lab measurement/test component.

    A Practice can have multiple Determinations.
    Example: "Complete Blood Count" practice includes determinations like:
    - Hemoglobin
    - White Blood Cell Count
    - Platelet Count
    """
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)  # e.g., "HGB"
    unit = models.CharField(max_length=50, blank=True)  # e.g., "g/dL"
    reference_range = models.CharField(max_length=100, blank=True)  # e.g., "12-16 g/dL"
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
```

### Study Model (apps/studies/models.py)

A **Study** represents a lab protocol/order for a specific patient. One study contains one or more practices via `StudyPractice`.

**Key design**: 1 Study = 1 protocol = N practices. This matches the LabWin domain where a patient visit (NUMERO_FLD) has multiple practices (DETERS rows).

**Primary Key**: `uuid` (UUIDField)

```python
class Study(BaseModel, LabClientModel):
    """
    Laboratory study/protocol order for a patient.

    Lifecycle:
    1. Created (pending)
    2. Sample collected (in_progress)
    3. Results uploaded (completed)
    4. Patient notified
    """
    # Relationships
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='studies')
    ordered_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ordered_studies',
        limit_choices_to={'role': 'doctor'}
    )

    # Study details
    protocol_number = models.CharField(max_length=50, unique=True)  # e.g., "LW-12345" or "2026-001234"
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('in_progress', 'In Progress'),
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled'),
        ],
        default='pending'
    )

    # Results (PDF file per protocol)
    results_file = models.FileField(upload_to='study_results/', blank=True)

    # LabWin fields
    sample_id = models.CharField(max_length=50, blank=True, db_index=True)  # NUMERO_FLD
    service_date = models.DateField(null=True, blank=True)

    # Dates
    solicited_date = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Notes
    notes = models.TextField(blank=True)

    # Multi-tenant
    lab_client_id = models.IntegerField(null=True, blank=True, db_index=True)

    # Audit trail
    history = HistoricalRecords()

    # Custom manager (see managers.py)
    objects = StudyManager()

    def __str__(self):
        return self.protocol_number

    @property
    def is_pending(self):
        return self.status == 'pending'

    @property
    def is_completed(self):
        return self.status == 'completed'
```

**Custom Manager** (apps/studies/managers.py):
```python
class StudyManager(models.Manager):
    def pending(self):
        return self.filter(status='pending')

    def completed(self):
        return self.filter(status='completed')

    def for_patient(self, patient):
        return self.filter(patient=patient)

    def for_lab(self, lab_client_id):
        return self.filter(lab_client_id=lab_client_id)

    def for_practice(self, practice):
        return self.filter(study_practices__practice=practice)
```

**LabWin-derived flags** (added 2026-04-25):
- `is_paid: BooleanField(default=True)` — `False` only when the source
  `PACIENTES.DEBEBONO_FLD == '1'` (patient owes a bono). Most patients are
  insurance-covered so the default is True. Re-imported on every sync; flips
  if the patient pays between backups.
- `is_validated: BooleanField(default=False)` — `True` for sync-imported
  studies (the connector pre-filters to `VALIDADO_FLD='1'` DETERS rows).
  Manually-created studies start False until lab staff validates.

Patient-facing visibility filters (e.g. `Study.objects.visible_to_patient()`)
should AND on both flags. Today no manager method enforces this; add one
when the lab confirms the patient signup workflow (see CLAUDE.md "Workflow
open question").

### StudyPractice Model (apps/studies/models.py)

A **StudyPractice** links a practice to a study. Each practice within a protocol gets its own result.

```python
class StudyPractice(BaseModel):
    """
    A practice within a study/protocol.
    Stores the raw result for this specific practice.

    Example:
    Study "LW-12345" (protocol) has:
    - StudyPractice 1: Glucemia Basal → result="105"
    - StudyPractice 2: Uremia → result="35"
    - StudyPractice 3: Creatinina → result="0.9"
    """
    study = models.ForeignKey(Study, on_delete=models.CASCADE, related_name='study_practices')
    practice = models.ForeignKey(Practice, on_delete=models.PROTECT, related_name='study_practices')
    result = models.TextField(blank=True)  # Raw result value (e.g., "105" or "79|4790|137")
    code = models.CharField(max_length=20, blank=True, db_index=True)  # LabWin ABREV_FLD
    order = models.IntegerField(default=0)  # Display order

    class Meta:
        ordering = ['order', 'code']
        unique_together = [['study', 'practice']]
```

### UserDetermination Model (apps/studies/models.py)

Stores **individual result values** for a specific practice within a study.

```python
class UserDetermination(BaseModel):
    """
    Individual result value for a determination within a study practice.

    Example:
    StudyPractice: "Complete Blood Count" in Study "LW-12345"
    - UserDetermination 1: Hemoglobin = "14.5 g/dL"
    - UserDetermination 2: WBC Count = "7200 /uL"
    """
    study_practice = models.ForeignKey(StudyPractice, on_delete=models.CASCADE, related_name='determination_results')
    determination = models.ForeignKey(Determination, on_delete=models.PROTECT, related_name='user_results')
    value = models.CharField(max_length=200)  # Actual result value
    is_abnormal = models.BooleanField(default=False)  # Flag if outside reference range
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = [['study_practice', 'determination']]
```

### Appointment Model (apps/appointments/models.py)

```python
class Appointment(BaseModel, LabClientModel):
    """Patient appointment for sample collection or consultation"""
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='appointments')
    study = models.ForeignKey(Study, on_delete=models.SET_NULL, null=True, blank=True)

    appointment_number = models.CharField(max_length=50, unique=True)
    scheduled_date = models.DateField()
    scheduled_time = models.TimeField()
    duration_minutes = models.IntegerField(default=30)

    status = models.CharField(
        max_length=20,
        choices=[
            ('scheduled', 'Scheduled'),
            ('confirmed', 'Confirmed'),
            ('in_progress', 'In Progress'),
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled'),
            ('no_show', 'No Show'),
        ],
        default='scheduled'
    )

    confirmed_at = models.DateTimeField(null=True, blank=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)

    reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    cancellation_reason = models.TextField(blank=True)

    reminder_sent = models.BooleanField(default=False)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()
```

### Invoice & Payment Models (apps/payments/models.py)

```python
class Invoice(BaseModel, LabClientModel):
    """Invoice for medical services"""
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='invoices')
    study = models.ForeignKey(Study, on_delete=models.SET_NULL, null=True, blank=True)

    invoice_number = models.CharField(max_length=50, unique=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('draft', 'Draft'),
            ('pending', 'Pending Payment'),
            ('paid', 'Paid'),
            ('partially_paid', 'Partially Paid'),
            ('cancelled', 'Cancelled'),
            ('refunded', 'Refunded'),
        ],
        default='draft'
    )

    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    issue_date = models.DateField()
    due_date = models.DateField()
    paid_date = models.DateField(null=True, blank=True)

    notes = models.TextField(blank=True)
    history = HistoricalRecords()

    @property
    def balance_due(self):
        return self.total_amount - self.paid_amount

class Payment(BaseModel):
    """Payment transaction for an invoice"""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')

    transaction_id = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(
        max_length=20,
        choices=[
            ('cash', 'Cash'),
            ('credit_card', 'Credit Card'),
            ('debit_card', 'Debit Card'),
            ('bank_transfer', 'Bank Transfer'),
            ('online', 'Online Payment'),
        ],
        default='cash'
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('processing', 'Processing'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
            ('refunded', 'Refunded'),
        ],
        default='pending'
    )

    # Payment gateway integration (e.g., Stripe)
    gateway = models.CharField(max_length=50, blank=True)
    gateway_transaction_id = models.CharField(max_length=200, blank=True)
    gateway_response = models.JSONField(blank=True, null=True)

    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    history = HistoricalRecords()
```

### Notification Model (apps/notifications/models.py)

```python
class Notification(BaseModel):
    """System notification for users"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')

    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(
        max_length=30,
        choices=[
            ('info', 'Information'),
            ('warning', 'Warning'),
            ('error', 'Error'),
            ('success', 'Success'),
            ('appointment_reminder', 'Appointment Reminder'),
            ('result_ready', 'Result Ready'),
            ('payment_due', 'Payment Due'),
        ],
        default='info'
    )
    channel = models.CharField(
        max_length=20,
        choices=[
            ('in_app', 'In-App'),
            ('email', 'Email'),
            ('sms', 'SMS'),
            ('push', 'Push Notification'),
        ],
        default='in_app'
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('sent', 'Sent'),
            ('delivered', 'Delivered'),
            ('failed', 'Failed'),
            ('read', 'Read'),
        ],
        default='pending'
    )

    # Related objects (stored as IDs, not FKs to avoid circular dependencies)
    related_study_id = models.IntegerField(null=True, blank=True)
    related_appointment_id = models.IntegerField(null=True, blank=True)
    related_invoice_id = models.IntegerField(null=True, blank=True)

    metadata = models.JSONField(blank=True, null=True)

    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    @property
    def is_read(self):
        return self.read_at is not None
```

---

## 🔌 API Endpoints

All API endpoints are prefixed with `/api/v1/`.

### Authentication (`/api/v1/auth/`)

Defined in `apps/users/auth_urls.py`:

```python
POST   /api/v1/auth/register/           # Patient registration (public)
POST   /api/v1/auth/login/              # Login (returns JWT access + refresh tokens)
POST   /api/v1/auth/logout/             # Logout (blacklists refresh token)
POST   /api/v1/auth/token/refresh/      # Refresh access token
GET    /api/v1/auth/user/               # Get current user profile
PATCH  /api/v1/auth/user/               # Update current user profile
POST   /api/v1/auth/password/change/    # Change password (authenticated)
POST   /api/v1/auth/password/reset/     # Request password reset (public)
POST   /api/v1/auth/password/reset/confirm/  # Confirm password reset
POST   /api/v1/auth/verify-email/       # Verify email with token
```

**Rate Limits**:
- Login: 5 attempts per 15 minutes per IP
- Password reset: 3 requests per hour per IP
- Registration: 5 requests per hour per IP

### Users (`/api/v1/users/`)

Defined in `apps/users/urls.py`:

```python
GET    /api/v1/users/                    # List all users (admin only)
POST   /api/v1/users/create-user/        # Create user (admin/staff only)
GET    /api/v1/users/{uuid}/             # Get user details
PATCH  /api/v1/users/{uuid}/             # Update user
DELETE /api/v1/users/{uuid}/             # Delete user (admin only)

# Search endpoints
GET    /api/v1/users/search-doctors/     # Search doctors (admin/staff)
GET    /api/v1/users/search-patients/    # Search patients (admin/staff)

# Bulk import (asynchronous via Celery)
POST   /api/v1/users/import-doctors/     # Upload CSV to import doctors (admin/staff)
GET    /api/v1/users/import-doctors/status/{task_id}/  # Check import status
```

#### Doctor CSV Import Feature (Added 2026-04-12)

Bulk import doctors from CSV file using Celery for async processing.

**CSV Format**:
```csv
NOMBRE_MEDICO,MATRICULA_O_ID
"Perez, Juan",12345
"Maria Rodriguez",MP67890
"Single Name",ABC123
```

**Import Workflow**:

1. **Upload CSV** (`POST /api/v1/users/import-doctors/`):
   - Permission: Admin or Lab Staff only
   - File validation: Must be `.csv` file
   - Request: `multipart/form-data` with `file` field
   - Response: `{ "task_id": "uuid", "message": "..." }` (202 Accepted)

2. **Check Status** (`GET /api/v1/users/import-doctors/status/{task_id}/`):
   - Poll every 2 seconds from frontend
   - Returns task state and progress:
     - `PENDING`: Task queued
     - `PROCESSING`: Task running (includes progress metadata)
     - `SUCCESS`: Task completed (includes result summary)
     - `FAILURE`: Task failed (includes error message)

**Task Implementation** (`apps/users/tasks.py`):

```python
@shared_task(bind=True)
def import_doctors_task(self, csv_content, lab_client_id=None):
    """
    Import doctors from CSV asynchronously.

    - Parses CSV row by row
    - Skips empty rows
    - Skips duplicates (checks existing matricula)
    - Updates progress every 100 rows
    - Creates doctors with is_verified=True (no email required)
    - Returns summary: { created, skipped, errors }
    """
```

**Name Parsing** (`_parse_name` helper):
- **"Last, First"** format → `first_name="First"`, `last_name="Last"`
- **"First Last"** format → `first_name="First"`, `last_name="Last"`
- **"Single"** format → `first_name="Single"`, `last_name=""`

**Doctor Creation**:
```python
User.objects.create_user(
    first_name=first_name,
    last_name=last_name,
    matricula=matricula,  # From CSV
    role="doctor",
    is_active=True,
    is_verified=True,     # Auto-verified, no email needed
    email=None,           # Optional for doctors
)
```

**Key Design Decisions**:
1. **Email Not Required**: Doctors use `matricula` as unique identifier
2. **Auto-Verified**: Doctors don't need email verification (`is_verified=True`)
3. **Idempotent**: Skips existing matriculas instead of erroring
4. **Async Processing**: Handles large CSV files (1000+ doctors) without timeouts
5. **Progress Updates**: Frontend shows real-time progress via polling

**Frontend Integration** (`src/views/admin/PatientsView.vue`):
- Import button triggers file upload
- Modal shows progress spinner while processing
- Polls status endpoint every 2 seconds
- Displays results: Created, Skipped, Errors
- Refreshes user list on completion

**Celery Configuration**:
- **CRITICAL**: New Celery tasks require worker restart!
  ```bash
  docker-compose restart celery_worker
  ```
- Task registers automatically via `autodiscover_tasks()`
- Verify with: `docker logs labcontrol_celery_worker | grep import_doctors_task`

### Studies (`/api/v1/studies/`)

Defined in `apps/studies/urls.py`:

```python
# Study CRUD
GET    /api/v1/studies/                           # List studies (filtered by role)
POST   /api/v1/studies/                           # Create study (admin/staff)
GET    /api/v1/studies/{uuid}/                    # Get study details
PATCH  /api/v1/studies/{uuid}/                    # Update study
DELETE /api/v1/studies/{uuid}/                    # Delete study (admin only)

# Result management
POST   /api/v1/studies/{uuid}/upload_result/      # Upload result file (admin/staff)
GET    /api/v1/studies/{uuid}/download_result/    # Download result file
DELETE /api/v1/studies/{uuid}/delete-result/      # Delete result file (admin/staff)

# Filtered lists
GET    /api/v1/studies/with-results/              # Studies with results (admin/staff)
GET    /api/v1/studies/available-for-upload/      # Studies ready for result upload

# Practices and Determinations
GET    /api/v1/studies/practices/                 # List active practices
POST   /api/v1/studies/practices/                 # Create practice (admin/staff)
GET    /api/v1/studies/practices/{uuid}/          # Get practice details
PATCH  /api/v1/studies/practices/{uuid}/          # Update practice
DELETE /api/v1/studies/practices/{uuid}/          # Delete practice

GET    /api/v1/studies/determinations/            # List determinations
POST   /api/v1/studies/determinations/            # Create determination (admin/staff)

# User Determinations (individual result values)
GET    /api/v1/studies/user-determinations/       # List user determinations
POST   /api/v1/studies/user-determinations/       # Create user determination
PATCH  /api/v1/studies/user-determinations/{uuid}/  # Update user determination

# Utility
GET    /api/v1/studies/last-protocol-number/      # Get last protocol number for auto-increment
```

**Permissions**:
- Patients: Can only view their own studies
- Doctors: Can view studies they ordered
- Lab Staff: Can view/create/update all studies for their lab
- Admin: Full access

**Filters**:
```python
# Available filters on /api/v1/studies/
?patient={uuid}           # Filter by patient
?study_practices__practice={uuid}  # Filter by practice
?status=pending           # Filter by status
?ordering=-created_at     # Order by field (prefix '-' for descending)
?search=protocol          # Search in protocol_number, patient name
```

### Appointments (`/api/v1/appointments/`)

```python
GET    /api/v1/appointments/              # List appointments
POST   /api/v1/appointments/              # Create appointment
GET    /api/v1/appointments/{uuid}/       # Get appointment
PATCH  /api/v1/appointments/{uuid}/       # Update appointment
DELETE /api/v1/appointments/{uuid}/       # Cancel appointment
```

### Payments (`/api/v1/payments/`)

```python
GET    /api/v1/payments/invoices/         # List invoices
POST   /api/v1/payments/invoices/         # Create invoice
GET    /api/v1/payments/invoices/{uuid}/  # Get invoice
PATCH  /api/v1/payments/invoices/{uuid}/  # Update invoice

GET    /api/v1/payments/                  # List payments
POST   /api/v1/payments/                  # Record payment
GET    /api/v1/payments/{uuid}/           # Get payment
```

### Notifications (`/api/v1/notifications/`)

```python
GET    /api/v1/notifications/             # List user's notifications
GET    /api/v1/notifications/{uuid}/      # Get notification
PATCH  /api/v1/notifications/{uuid}/      # Mark as read
DELETE /api/v1/notifications/{uuid}/      # Delete notification
```

### Analytics (`/api/v1/analytics/`)

```python
GET    /api/v1/analytics/dashboard/               # Dashboard overview
GET    /api/v1/analytics/studies/                 # Study statistics
GET    /api/v1/analytics/studies/trends/          # Study trends over time
GET    /api/v1/analytics/revenue/                 # Revenue statistics
GET    /api/v1/analytics/revenue/trends/          # Revenue trends
GET    /api/v1/analytics/appointments/            # Appointment statistics
GET    /api/v1/analytics/users/                   # User statistics
GET    /api/v1/analytics/popular-practices/       # Most popular practices
GET    /api/v1/analytics/top-revenue-practices/   # Highest revenue practices
```

---

## 🔐 Authentication & Permissions

### Authentication

Uses **JWT (JSON Web Tokens)** via `djangorestframework-simplejwt`.

**Login Flow**:
1. POST `/api/v1/auth/login/` with `{ "email": "...", "password": "..." }`
2. Receive `{ "access": "...", "refresh": "...", "user": {...} }`
3. Include `Authorization: Bearer <access_token>` in all authenticated requests
4. When access token expires, POST to `/api/v1/auth/token/refresh/` with `{ "refresh": "..." }`

**Token Lifetimes** (config/settings/base.py):
- Access token: 1 hour
- Refresh token: 7 days

**Important**: The User model uses `uuid` as primary key, so JWT tokens contain `user_id` as UUID string.

### Permissions

Custom permission classes in `apps/core/permissions.py` and `apps/users/permissions.py`:

```python
class IsAdminUser(permissions.BasePermission):
    """Only admin users can access"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'admin'

class IsAdminOrLabStaff(permissions.BasePermission):
    """Admin or lab staff can access"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ['admin', 'lab_staff']

class IsPatientOwner(permissions.BasePermission):
    """Patient can only access their own resources"""
    def has_object_permission(self, request, view, obj):
        if request.user.role in ['admin', 'lab_staff']:
            return True
        return obj.patient == request.user
```

**Usage in Views**:
```python
from apps.core.permissions import IsAdminOrLabStaff

class StudyViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsAdminOrLabStaff]
```

### Email Verification

New patient registrations require email verification:

1. User registers → `is_verified=False`, verification token generated
2. Email sent with link: `{FRONTEND_URL}/verify-email?token={verification_token}`
3. Frontend calls POST `/api/v1/auth/verify-email/` with token
4. Backend sets `is_verified=True`, user can log in

**Manual verification** (for development):
```bash
make verify-email EMAIL=user@example.com
# OR
python manage.py verify_email user@example.com
```

---

## ⚙️ Key Patterns & Conventions

### 1. UUID Primary Keys — CRITICAL ⚠️

**All models use UUID primary keys**, not auto-increment IDs.

```python
# ✅ CORRECT - Use .pk or .uuid
user.pk
study.pk
str(obj.pk)
Count("pk", filter=Q(...))

# ❌ WRONG - Do NOT use .id (will fail!)
user.id          # AttributeError: 'User' object has no attribute 'id'
study.id         # AttributeError
```

**Why UUIDs?**
- Security: No enumeration attacks (can't guess `/api/v1/users/2/`)
- Distributed systems: UUIDs can be generated client-side
- Database merging: No ID conflicts

**Serializers**:
```python
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['uuid', 'email', 'first_name', ...]  # Use 'uuid', not 'id'
```

### 2. Multi-Tenant Filtering

All queries for multi-tenant models should filter by `lab_client_id`:

```python
# In views/viewsets
def get_queryset(self):
    queryset = Study.objects.all()

    # Filter by lab client for non-admin users
    if not self.request.user.role == 'admin':
        queryset = queryset.filter(lab_client_id=self.request.user.lab_client_id)

    return queryset
```

**Models with multi-tenancy**:
- `User`
- `Study`
- `Appointment`
- `Invoice`

### 3. Custom Managers

All models have custom managers for common queries:

```python
# apps/studies/managers.py
class StudyManager(models.Manager):
    def pending(self):
        return self.filter(status='pending')

    def completed(self):
        return self.filter(status='completed')

    def for_patient(self, patient):
        return self.filter(patient=patient)

    def for_lab(self, lab_client_id):
        return self.filter(lab_client_id=lab_client_id)
```

**Usage**:
```python
Study.objects.pending()                    # Get all pending studies
Study.objects.for_patient(user)            # Get studies for a patient
Study.objects.for_lab(1).completed()       # Chainable
```

### 4. Audit Trail with django-simple-history

Critical models use `HistoricalRecords` to track all changes:

```python
from simple_history.models import HistoricalRecords

class Study(BaseModel):
    # ... fields ...
    history = HistoricalRecords()
```

**Query history**:
```python
study = Study.objects.get(pk=some_uuid)
study.history.all()               # All historical records
study.history.as_of(datetime)     # State at a specific time
```

**Models with audit trail**:
- `User`, `Study`, `Appointment`, `Invoice`, `Payment`, `Notification`

### 5. File Uploads

**Media files** are stored in `/app/media/` and served by Nginx in production.

```python
# models.py
class User(AbstractBaseUser):
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True)

class Study(BaseModel):
    results_file = models.FileField(upload_to='study_results/', blank=True)
```

**Upload endpoint example** (apps/studies/views.py):
```python
@action(detail=True, methods=['post'], permission_classes=[IsAdminOrLabStaff])
def upload_result(self, request, pk=None):
    study = self.get_object()
    file = request.FILES.get('file')

    if not file:
        return Response({'error': 'No file provided'}, status=400)

    study.results_file = file
    study.status = 'completed'
    study.completed_at = timezone.now()
    study.save()

    return Response({'message': 'Result uploaded successfully'})
```

**Frontend request**:
```javascript
const formData = new FormData();
formData.append('file', file);

await axios.post(`/api/v1/studies/${studyId}/upload_result/`, formData, {
  headers: { 'Content-Type': 'multipart/form-data' }
});
```

### 6. Serializer Patterns

**Read-only fields**:
```python
class StudySerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    practice_name = serializers.CharField(source='practice.name', read_only=True)

    class Meta:
        model = Study
        fields = ['uuid', 'protocol_number', 'patient', 'patient_name', 'practice', 'practice_name', ...]
        read_only_fields = ['uuid', 'created_at', 'updated_at']
```

**Nested serializers**:
```python
class StudyDetailSerializer(serializers.ModelSerializer):
    patient = UserSerializer(read_only=True)
    practice = PracticeSerializer(read_only=True)
    determination_results = UserDeterminationSerializer(many=True, read_only=True)

    class Meta:
        model = Study
        fields = '__all__'
```

### 7. ViewSet Patterns

**Filtering queryset by user role**:
```python
class StudyViewSet(viewsets.ModelViewSet):
    queryset = Study.objects.all()
    serializer_class = StudySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()

        if user.role == 'patient':
            # Patients can only see their own studies
            return queryset.filter(patient=user)
        elif user.role == 'doctor':
            # Doctors can see studies they ordered
            return queryset.filter(ordered_by=user)
        elif user.role in ['lab_staff', 'admin']:
            # Staff can see all studies for their lab
            if user.role != 'admin':
                queryset = queryset.filter(lab_client_id=user.lab_client_id)
            return queryset

        return queryset.none()
```

**Custom actions**:
```python
@action(detail=True, methods=['post'])
def upload_result(self, request, pk=None):
    """Upload result file for a study"""
    # Implementation...
    pass

@action(detail=False, methods=['get'])
def pending(self, request):
    """List all pending studies"""
    studies = self.get_queryset().filter(status='pending')
    serializer = self.get_serializer(studies, many=True)
    return Response(serializer.data)
```

### 8. Accent-insensitive Search (added 2026-04-25)

All search across user/study fields is **case AND accent insensitive** so that
`'si'` matches `'Sí'`, `'munoz'` matches `'Muñoz'`, `'gonzalez'` matches
`'González'`. Required for Spanish-language patient data.

Implementation: `apps/core/search.unaccent_icontains_q(value, *fields)` builds
a `Q()` object using Postgres' `unaccent()` extension via the bilateral
`__unaccent` lookup transform. Extension enabled by migration
`apps.core.0001_unaccent_extension`.

```python
from apps.core.search import unaccent_icontains_q

# In a custom filter_search method
queryset.filter(
    unaccent_icontains_q(
        value,
        "first_name", "last_name", "email", "dni",
        "phone_number", "matricula",
    )
)
```

Used by `UserFilter`, `StudyFilter`, `DeterminationFilter`, and the
`/users/search-patients/` and `/users/search-doctors/` endpoints.

### 9. Pet/Veterinary Patient Filtering (added 2026-04-25)

The lab serves veterinary patients alongside humans, but PACIENTES has no
schema-level discriminator. `apps/labwin_sync/mappers.is_pet_candidate(...)`
combines two signals to skip pets at sync time:

1. **Structural**: `last_name` (parsed from `NOMBRE_FLD`) starts with `'167'`
   — the lab's pet HCLIN range.
2. **Practice-based**: any of the protocol's DETERS rows maps to a Practice
   with code starting with `VET` or name containing veterinary keywords
   (`veterinari`, `canin`, `felin`, `canis`, `bovin`, `porcin`, `equin`,
   `caprin`, `aves`).

Pet IF: `dni == '' AND (signal 1 OR signal 2)`. The `dni=''` guard prevents
false positives — verified against real data, 0 patients with a DNI matched.
If the lab adds an explicit pet/vet flag to LabWin in the future, replace
both signals with that single source of truth.

---

## 🧪 Testing

**Test Suite**: 459 tests passing, 0 regressions (as of 2026-04-25)

### BaseTestCase (tests/base.py)

All tests inherit from `BaseTestCase`, which provides factory methods:

```python
from tests.base import BaseTestCase

class StudyTests(BaseTestCase):
    def test_create_study(self):
        # Create test users
        patient = self.create_patient()
        doctor = self.create_doctor()

        # Create practice
        practice = self.create_practice(name="Blood Test", price=100.00)

        # Create study
        study = self.create_study(patient=patient, practice=practice)

        # Assertions
        self.assertEqual(study.patient, patient)
        self.assertEqual(study.status, 'pending')
```

### Factory Methods

```python
# User factories
self.create_user(email='test@example.com', role='patient', **kwargs)
self.create_admin()                  # Creates admin user
self.create_lab_staff(lab_client_id=1)  # Creates lab staff
self.create_doctor()                 # Creates doctor
self.create_patient()                # Creates patient

# Other factories
self.create_practice(name='Test', price=100, **kwargs)
self.create_study(patient, practice, **kwargs)
self.create_appointment(patient, study, **kwargs)
self.create_invoice(patient, study, **kwargs)
self.create_payment(invoice, **kwargs)
self.create_notification(user, **kwargs)

# Authentication helpers
client = self.authenticate(user)     # Returns authenticated APIClient
client, user = self.authenticate_as_patient()
client, user = self.authenticate_as_admin()
client, user = self.authenticate_as_lab_staff(lab_client_id=1)
```

### Running Tests

```bash
# All tests
make test

# With coverage
make test-coverage

# Specific app
python manage.py test apps.users

# Specific test
python manage.py test apps.studies.tests.StudyViewSetTests.test_create_study

# Fast (skip migrations)
make test-fast
```

### Test Example

```python
from rest_framework import status
from tests.base import BaseTestCase

class StudyViewSetTests(BaseTestCase):
    def test_patient_can_only_see_own_studies(self):
        # Arrange
        patient1 = self.create_patient(email='patient1@test.com')
        patient2 = self.create_patient(email='patient2@test.com')
        practice = self.create_practice()

        study1 = self.create_study(patient=patient1, practice=practice)
        study2 = self.create_study(patient=patient2, practice=practice)

        # Act
        client = self.authenticate(patient1)
        response = client.get('/api/v1/studies/')

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['uuid'], str(study1.pk))
```

---

## 💾 Database

### PostgreSQL Configuration

**Database**: PostgreSQL 15 (Alpine)

**Connection**:
```python
# .env
DATABASE_URL=postgresql://labcontrol_user:password@db:5432/labcontrol_db
```

**Settings** (config/settings/base.py):
```python
DATABASES = {
    'default': env.db('DATABASE_URL'),
}
```

### Migrations

**All migrations were deleted and recreated on 2026-02-17.** There is no legacy migration history.

```bash
# Create migrations
make makemigrations
# OR
python manage.py makemigrations

# Apply migrations
make migrate
# OR
python manage.py migrate

# Show migrations
make showmigrations

# Create migration for specific app
python manage.py makemigrations users
```

**Migration files**: `apps/{app_name}/migrations/0001_initial.py`, `0002_*.py`, etc.

### Database Reset (DESTRUCTIVE!)

```bash
# WARNING: Destroys all data!
make db-reset
```

This will:
1. Drop the database
2. Recreate it
3. Run all migrations
4. Create seed users

### Common Database Queries

```python
# Get all studies with results
Study.objects.exclude(results_file='')

# Get pending studies for a lab
Study.objects.filter(
    status='pending',
    lab_client_id=1
).order_by('-created_at')

# Get user with all related studies
user = User.objects.prefetch_related('studies').get(pk=user_uuid)

# Aggregate queries
from django.db.models import Count, Sum
Invoice.objects.aggregate(
    total_revenue=Sum('total_amount'),
    invoice_count=Count('pk')
)

# Annotate queries
from django.db.models import Count
Practice.objects.annotate(
    study_count=Count('studies')
).order_by('-study_count')
```

---

## ⚡ Celery Tasks

**Celery** is used for asynchronous tasks (emails, notifications, reminders).

### Configuration

**Broker**: Redis
**Result Backend**: Django DB
**Config**: `config/celery.py`

```python
# config/celery.py
from celery import Celery

app = Celery('labcontrol')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
```

### Task Example

```python
# apps/notifications/tasks.py
from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings

@shared_task
def send_result_ready_notification(study_uuid):
    """
    Send email notification when study results are ready.

    Called from Study.upload_result() view.
    """
    from apps.studies.models import Study

    study = Study.objects.get(pk=study_uuid)
    patient = study.patient

    subject = f"Results Ready: {study.practice.name}"
    message = f"Dear {patient.first_name}, your lab results are ready. Login to view them."

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[patient.email],
        fail_silently=False,
    )

    # Create in-app notification
    from apps.notifications.models import Notification
    Notification.objects.create(
        user=patient,
        title="Results Ready",
        message=f"Your {study.practice.name} results are ready to view.",
        notification_type='result_ready',
        channel='in_app',
        status='sent',
        related_study_id=study.pk,
    )
```

**Calling tasks**:
```python
# In views
from apps.notifications.tasks import send_result_ready_notification

def upload_result(request, study_id):
    # ... upload logic ...

    # Trigger async task
    send_result_ready_notification.delay(study.pk)
```

### Running Celery

**Development**:
```bash
# Worker
celery -A config worker -l info

# Beat (scheduler)
celery -A config beat -l info
```

**Production** (Docker):
```bash
# Containers run automatically via docker-compose.prod.yml
docker logs labcontrol_celery_worker
docker logs labcontrol_celery_beat
```

---

## 🔄 LabWin Sync

Automated nightly sync of lab results from the LabWin Firebird 2.x database to LabControl.

### App Structure

```
apps/labwin_sync/
├── models.py           # SyncLog, SyncedRecord
├── tasks.py            # sync_labwin_results Celery task
├── mappers.py          # LabWin row → Django model field mapping
├── admin.py            # SyncLog/SyncedRecord admin views
├── connectors/
│   ├── __init__.py     # get_connector() factory
│   ├── base.py         # Abstract connector interface
│   ├── firebird.py     # Real Firebird connector (firebirdsql)
│   └── mock.py         # Mock connector with sample data (dev/tests)
└── management/commands/
    └── sync_labwin.py  # Manual sync trigger
```

### LabWin Database Tables

| Table | Purpose | Key Fields |
|-------|---------|------------|
| PACIENTES | Patient orders (one row per visit) | `NUMERO_FLD` (order ID), `NOMBRE_FLD`, `HCLIN_FLD` (DNI), `SEXO_FLD`, `FNACIM_FLD` |
| DETERS | Practices/results per order (887K records) | `NUMERO_FLD` (→PACIENTES), `ABREV_FLD` (practice code), `RESULT_FLD`, `VALIDADO_FLD` |
| MEDICOS | Doctor definitions | `NUMERO_FLD`, `NOMBRE_FLD`, `MATNAC_FLD` (matricula) |
| NOMEN | Practice definitions | `ABREV_FLD`, `NOMBRE_FLD`, `DIASTARDA_FLD` (turnaround days) |

### Data Mapping

| LabWin | LabControl | Matching Key |
|--------|-----------|--------------|
| PACIENTES | User (role=patient) | `dni` = `HCLIN_FLD` |
| MEDICOS | User (role=doctor) | `matricula` = `MATNAC_FLD` |
| NOMEN | Practice | `code` = `ABREV_FLD` |
| DETERS (grouped by NUMERO) | Study | `protocol_number` = `"LW-{NUMERO}"` |
| DETERS (each row) | StudyPractice | `code` = `ABREV_FLD`, `result` = `RESULT_FLD` |

### Sync Models

**SyncLog** — Tracks each sync run:
- `status`: started / completed / failed / partial
- Counters: `patients_created`, `patients_updated`, `doctors_created`, `studies_created`, `studies_updated`, `study_practices_created`
- Cursor: `last_synced_numero` (BigIntegerField), `last_synced_fecha` (CharField)
- `errors` (JSONField), `error_count`

**SyncedRecord** — Maps LabWin records to LabControl objects for deduplication:
- `source_table` + `source_key` + `lab_client_id` (unique together)
- `target_model`, `target_uuid`

### Sync Flow

1. Celery Beat triggers `sync_labwin_results` nightly at 2 AM (currently manual until the lab signup workflow is locked in)
2. Task computes the **date window** (rolling-window strategy, since 2026-04-28):
   - **First run** for this `lab_client_id` → window starts `LABWIN_SYNC_INITIAL_DAYS` ago (default 90)
   - **Every subsequent run** → window starts `LABWIN_SYNC_ROLLING_DAYS` ago (default 2), regardless of how far the prior sync got. This re-scans the last couple of days every night so late-validated rows from yesterday get picked up.
   - `full_sync=True` bypasses the window entirely (one-off re-imports).
   - Older data (the lab's 14+ years of history pre-window) is intentionally skipped per business decision: only recent data is valid for the patient portal.
3. Connects to LabWin via connector factory (mock or real based on `LABWIN_USE_MOCK`)
4. Fetches validated DETERS where `FECHA_FLD >= window_start`, in batches of 500
5. For each batch: fetches PACIENTES, MEDICOS, NOMEN for referenced IDs
6. Groups DETERS rows by NUMERO_FLD — creates 1 Study per NUMERO, N StudyPractice records per Study
7. Creates **or updates** patients, doctors, practices, studies, study_practices. Re-syncs are idempotent and refresh:
   - `Study.is_paid` (from `DEBEBONO_FLD`) and `Study.is_validated` if they changed
   - `StudyPractice.result` if `RESULT_FLD` changed and is non-empty
   - New `StudyPractice` rows if the lab added practices to an existing protocol
   - Patient `phone_number / direction / location / carnet` if they changed
   - **Not** refreshed: study `status / service_date / patient FK / ordered_by FK`, removed practices, doctor / practice fields. Track as TODO if those become important.
8. Updates SyncLog with counts. `last_synced_fecha` / `last_synced_numero` are written for audit trail but no longer drive the cursor (rolling-window replaces the resume-from-cursor logic).

### Connector Abstraction

```python
from apps.labwin_sync.connectors import get_connector

with get_connector() as connector:
    for batch in connector.fetch_validated_deters(since_fecha="20251028"):
        pacientes = connector.fetch_pacientes([row["NUMERO_FLD"] for row in batch])
        # ... process batch
```

**Mock connector**: In-memory sample data, no Firebird dependency. Used in tests and dev.
**Firebird connector**: Uses `firebirdsql` pure Python driver. Connection params from Django settings.

### Configuration

```env
LABWIN_USE_MOCK=True              # Set False for production (requires backup pipeline — see below)
LABWIN_FDB_HOST=localhost         # In prod: "firebird" (docker service name)
LABWIN_FDB_PORT=3050
LABWIN_FDB_DATABASE=              # Path to .fdb file on Firebird server
LABWIN_FDB_USER=SYSDBA
LABWIN_FDB_PASSWORD=<from 1Password: "LabControl LabWin SYSDBA">
LABWIN_SYNC_BATCH_SIZE=500
LABWIN_DEFAULT_LAB_CLIENT_ID=1
# Date window — see "Sync Flow" above
LABWIN_SYNC_INITIAL_DAYS=90
LABWIN_SYNC_ROLLING_DAYS=2
```

### Production Data Ingestion — Backup Pipeline

**Status (2026-04-25)**: Phase A + B shipped. End-to-end sync validated against the real DB — 3,062 studies + 2,877 patients ingested. `LABWIN_USE_MOCK=True` is still the default in `.env.production`; flip to `False` is gated on the lab's decision about the no-email patient signup workflow (see CLAUDE.md "Workflow open question").

**⚠️ IMPORTANTE:** El VPS **no puede conectarse directo** al Firebird de la PC del laboratorio (la PC no tiene IP pública ni puertos abiertos). Los datos llegan vía un pipeline de backups nocturnos:

```
PC Lab ─[gbak + gzip + SFTP, 02:00]─► VPS /srv/labwin_backups/incoming/
                                            │
                                            │ (Celery Beat 04:00 — pendiente)
                                            ▼
                                    import_uploaded_backup task
                                            │
                                            ├─► firebirdsql.services.restore_database
                                            │   → contenedor labcontrol_firebird
                                            └─► sync_labwin_results()
```

Cuando se active el schedule, este flow reemplaza el schedule standalone de `sync_labwin_results` en producción.

**Ver guía completa:** [`LABWIN_BACKUP_PIPELINE.md`](./LABWIN_BACKUP_PIPELINE.md) — arquitectura, status real por fase, seguridad, modos de fallo, y métricas baseline.

**Componentes que ya están en producción (2026-04-25):**
- Usuario SFTP `backup_user` con chroot a `/srv/labwin_backups/` (key auth ed25519)
- Servicio `firebird` (jacobalberty/firebird:2.5-ss) en `docker-compose.prod.yml`, accesible como `firebird:3050` desde la docker network
- Service class `apps/labwin_sync/services/backup_import.BackupImporter`
- Task `apps.labwin_sync.tasks.import_uploaded_backup`
- Management command `python manage.py import_backup [--file PATH] [--restore-only] [--sync-only] [--use-celery]`
- Script `upload_backup.py` corriendo manualmente en la PC del lab (Task Scheduler 02:00 todavía pendiente)

**Pendientes para activar el flujo automático completo:**
- Decisión del lab sobre signup de pacientes sin email
- Flip `LABWIN_USE_MOCK=False` en `.env.production`
- Celery Beat schedule (cron 04:00) y cambio del sync window de "todo desde 2026-02-01" a rolling "ayer + hoy"
- Task Scheduler en la PC del lab para corrida automática 02:00

### Management Command

```bash
python manage.py sync_labwin              # Incremental sync (from last cursor)
python manage.py sync_labwin --full       # Full sync (ignore cursor)
python manage.py sync_labwin --use-celery # Run via Celery worker

# Production only (after backup pipeline is live — see LABWIN_BACKUP_PIPELINE.md):
python manage.py import_backup            # Restore latest .fbk.gz + sync
python manage.py import_backup --restore-only
python manage.py import_backup --sync-only
```

### Idempotency

Three layers prevent duplicate records:
1. **SyncedRecord**: Maps `(source_table, source_key, lab_client_id)` → target UUID
2. **Natural key matching**: DNI for patients, matricula for doctors, code for practices
3. **Unique constraints**: `protocol_number` on Study

### FTP PDF Fetch (Phase 13)

Fetches PDF result files from an FTP server and attaches them to matching studies.

#### How It Works

1. LabWin sync creates studies with `sample_id = NUMERO_FLD` (e.g., "100001")
2. The lab's LabWin system exports PDF result files to an FTP server, named `{NUMERO_FLD}.pdf`
3. `fetch_ftp_pdfs` task lists PDFs on FTP, matches `{NUMERO}.pdf` → `Study.sample_id`
4. Downloads and saves the PDF to `study.results_file`
5. Optionally deletes the PDF from FTP after successful download

#### FTP Connector Abstraction

Follows the same pattern as the LabWin DB connector:

```python
from apps.labwin_sync.ftp import get_ftp_connector

with get_ftp_connector() as ftp:
    files = ftp.list_pdf_files()          # ["100001.pdf", "100002.pdf"]
    content = ftp.download_file("100001.pdf")  # bytes
    ftp.delete_file("100001.pdf")         # Remove from FTP
```

- **Mock connector**: In-memory PDF files for dev/tests. No FTP server needed.
- **Real connector**: Uses Python's `ftplib` (FTP or FTPS). Connection params from Django settings.

#### Celery Tasks

```python
# Fetch PDFs and attach to studies
fetch_ftp_pdfs.delay(lab_client_id=1, delete_after_download=False)

# Clean up already-processed PDFs from FTP
cleanup_ftp_pdfs.delay(lab_client_id=1)
```

**`fetch_ftp_pdfs`** returns:
```python
{
    "files_found": 10,
    "files_matched": 8,      # Found matching study
    "files_attached": 6,     # Downloaded and saved
    "files_skipped": 4,      # No match or already has PDF
    "files_deleted": 0,      # Deleted from FTP (if delete_after_download=True)
    "error_count": 0,
}
```

**`cleanup_ftp_pdfs`**: Scans FTP for PDFs whose matching study already has `results_file`, and deletes them from FTP.

#### Configuration

```env
LABWIN_FTP_USE_MOCK=True          # Set False for production
LABWIN_FTP_HOST=localhost
LABWIN_FTP_PORT=21
LABWIN_FTP_USER=
LABWIN_FTP_PASSWORD=
LABWIN_FTP_DIRECTORY=/results     # FTP directory containing PDFs
LABWIN_FTP_USE_TLS=False          # Set True for FTPS
```

#### API Endpoint

```
POST /api/v1/labwin-sync/fetch-pdfs/    # Trigger FTP PDF fetch (admin/staff only)
```

Request body (optional):
```json
{ "delete_after_download": false }
```

Returns: `{ "message": "...", "task_id": "..." }` (202 Accepted)

#### Management Command

```bash
python manage.py fetch_ftp_pdfs                  # Fetch without deleting from FTP
python manage.py fetch_ftp_pdfs --delete          # Fetch and delete from FTP
python manage.py fetch_ftp_pdfs --cleanup         # Only delete already-processed PDFs
python manage.py fetch_ftp_pdfs --use-celery      # Run via Celery worker
python manage.py fetch_ftp_pdfs --lab-client-id 1 # Specify lab client
```

#### Key Design Decisions

1. **Separate from LabWin DB sync**: FTP fetch runs independently (different schedule, different server)
2. **Skips existing PDFs**: Studies that already have `results_file` are skipped
3. **Optional delete**: `delete_after_download=False` by default for safety
4. **Cleanup task**: Separate task to clean up FTP files after verification
5. **Mock connector**: In-memory PDFs matching DETERS NUMERO_FLDs for testing

#### Real Filename Format (validated 2026-04-25)

Files arrive named `{NUMERO}-{DNI}-{NAME}.pdf` (e.g. `220197-39592918-SIRI,FRANCO.pdf`), not the originally-assumed `{NUMERO}.pdf`. The connector parser was updated 2026-04-25 to extract the protocol number as the first dash-separated segment. **24 real PDFs attached end-to-end** in the first run; 32 of 56 PDFs were skipped because their NUMERO falls outside the imported-study range (those studies aren't yet in Postgres — see CLAUDE.md TODO "PDF import workflow for files outside the imported-study NUMERO range").

The original 2026-04-22 push also landed files in the chroot root (`/`) instead of `/results`; lab now uploads via `cd results` before transferring.

### Future Phases

- **Phase 2**: ✅ Done 2026-04-25 — Phase B of the LabWin backup pipeline ingested real Firebird data via `firebirdsql.services.restore_database` (no remote Firebird credentials needed, lab pushes backups via SFTP — see LABWIN_BACKUP_PIPELINE.md).
- **Phase 3**: Parse pipe-delimited `RESULT_FLD` into UserDetermination records (requires RESULTS template table from LabWin) — still pending.

---

## 🛠️ Development Workflow

### Local Development Setup

```bash
# 1. Clone repository
git clone https://github.com/sebastiangolijow/LabControl-by-Golijow-Master-Solutions.git
cd LabControl-by-Golijow-Master-Solutions

# 2. Create .env file
cp .env.example .env
# Edit .env with your settings

# 3. Start Docker containers
make up
# OR
docker-compose up -d

# 4. Run migrations
make migrate

# 5. Create seed users
make seed-users

# 6. Create superuser (optional)
make superuser
```

**Services**:
- Django: http://localhost:8000
- PostgreSQL: localhost:5432
- Redis: localhost:6379
- Celery Worker: Background
- Celery Beat: Background

### Common Commands

```bash
# Docker
make up           # Start all containers
make down         # Stop all containers
make restart      # Restart all containers
make logs         # View logs
make shell        # Django shell

# Database
make migrate          # Run migrations
make makemigrations   # Create migrations
make showmigrations   # Show migration status
make db-reset         # Reset database (DESTRUCTIVE!)

# Testing
make test             # Run all tests
make test-coverage    # Run tests with coverage report
make test-verbose     # Run tests with verbose output
make test-fast        # Run tests without migrations

# Code Quality
make format           # Format code with black
make lint             # Lint code with flake8
make isort            # Sort imports
make quality          # Run all quality checks (format + lint + isort)

# Utilities
make seed-users                 # Create seed users
make superuser                  # Create superuser
make verify-email EMAIL=x@y.com # Verify user email
make load_practices             # Load practice catalog
make throttle-reset             # Clear rate limit cache
```

### Environment Variables

**Required** (.env):
```env
# Django
DJANGO_SECRET_KEY=your-secret-key-here
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_SETTINGS_MODULE=config.settings.dev

# Database
DATABASE_URL=postgresql://labcontrol_user:password@db:5432/labcontrol_db

# Redis
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# Email
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=noreply@labcontrol.com

# Frontend
FRONTEND_URL=http://localhost:5173

# CORS
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://localhost:8080
CSRF_TRUSTED_ORIGINS=http://localhost:8000

# Django Admin URL
ADMIN_URL=django-admin/  # Default: admin/
```

### Django Admin

**URL**: http://localhost:8000/django-admin/ (or `/{ADMIN_URL}`)

**Login**: Use superuser credentials or admin seed user:
- Email: `admin@labcontrol.com`
- Password: `test1234`

**Registered models**:
- Users
- Studies, Practices, Determinations, UserDeterminations
- Appointments
- Invoices, Payments
- Notifications

---

## 📝 Common Tasks

### 1. Add a New Field to User Model

```bash
# 1. Edit apps/users/models.py
class User(AbstractBaseUser):
    # ... existing fields ...
    new_field = models.CharField(max_length=100, blank=True)

# 2. Create migration
python manage.py makemigrations users

# 3. Review migration file
cat apps/users/migrations/0003_user_new_field.py

# 4. Apply migration
python manage.py migrate

# 5. Update serializer
# Edit apps/users/serializers.py
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [..., 'new_field']

# 6. Update tests
# Edit tests/test_users.py

# 7. Run tests
make test
```

### 2. Create a New API Endpoint

```python
# apps/studies/views.py
from rest_framework.decorators import action
from rest_framework.response import Response

class StudyViewSet(viewsets.ModelViewSet):
    # ... existing code ...

    @action(detail=False, methods=['get'], permission_classes=[IsAdminOrLabStaff])
    def statistics(self, request):
        """Get study statistics"""
        total_studies = self.get_queryset().count()
        pending_studies = self.get_queryset().filter(status='pending').count()
        completed_studies = self.get_queryset().filter(status='completed').count()

        return Response({
            'total': total_studies,
            'pending': pending_studies,
            'completed': completed_studies,
        })
```

**URL**: `GET /api/v1/studies/statistics/`

### 3. Add a Celery Task

```python
# apps/notifications/tasks.py
from celery import shared_task
from django.core.mail import send_mail

@shared_task
def send_appointment_reminder(appointment_uuid):
    """Send appointment reminder 24 hours before appointment"""
    from apps.appointments.models import Appointment

    appointment = Appointment.objects.get(pk=appointment_uuid)

    send_mail(
        subject="Appointment Reminder",
        message=f"You have an appointment tomorrow at {appointment.scheduled_time}",
        from_email="noreply@labcontrol.com",
        recipient_list=[appointment.patient.email],
    )

    appointment.reminder_sent = True
    appointment.reminder_sent_at = timezone.now()
    appointment.save()
```

**Schedule task** (using Celery Beat):
```python
# config/settings/base.py
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'send-appointment-reminders': {
        'task': 'apps.notifications.tasks.send_appointment_reminder',
        'schedule': crontab(hour=9, minute=0),  # Daily at 9 AM
    },
}
```

### 4. Add Custom Manager Method

```python
# apps/studies/managers.py
class StudyManager(models.Manager):
    # ... existing methods ...

    def overdue(self):
        """Get studies past their expected completion date"""
        from django.utils import timezone
        from datetime import timedelta

        return self.filter(
            status='pending',
            created_at__lt=timezone.now() - timedelta(days=7)
        )
```

**Usage**:
```python
overdue_studies = Study.objects.overdue()
```

### 5. Add Permission Class

```python
# apps/core/permissions.py
from rest_framework import permissions

class CanViewStudyResults(permissions.BasePermission):
    """
    Patients can view their own study results.
    Doctors can view results for studies they ordered.
    Lab staff and admin can view all results.
    """
    def has_object_permission(self, request, view, obj):
        user = request.user

        if user.role in ['admin', 'lab_staff']:
            return True

        if user.role == 'doctor':
            return obj.ordered_by == user

        if user.role == 'patient':
            return obj.patient == user

        return False
```

**Usage in ViewSet**:
```python
from apps.core.permissions import CanViewStudyResults

class StudyViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, CanViewStudyResults]
```

---

## 🎓 Best Practices

### 1. Always Use Transactions for Multi-Step Operations

```python
from django.db import transaction

@transaction.atomic
def create_study_with_invoice(patient, practice):
    """Create study and invoice in a single transaction"""
    study = Study.objects.create(
        patient=patient,
        practice=practice,
        protocol_number=generate_protocol_number(),
        status='pending',
    )

    invoice = Invoice.objects.create(
        patient=patient,
        study=study,
        invoice_number=generate_invoice_number(),
        total_amount=practice.price,
    )

    return study, invoice
```

### 2. Use select_related() and prefetch_related() for Performance

```python
# ❌ BAD - N+1 queries
studies = Study.objects.all()
for study in studies:
    print(study.patient.email)       # Query per iteration
    print(study.practice.name)       # Query per iteration

# ✅ GOOD - Single query with joins
studies = Study.objects.select_related('patient', 'practice').all()
for study in studies:
    print(study.patient.email)       # No additional query
    print(study.practice.name)       # No additional query

# ✅ GOOD - For many-to-many or reverse FKs
practices = Practice.objects.prefetch_related('determinations').all()
for practice in practices:
    for determination in practice.determinations.all():  # No additional query
        print(determination.name)
```

### 3. Validate Data in Serializers

```python
class StudySerializer(serializers.ModelSerializer):
    class Meta:
        model = Study
        fields = '__all__'

    def validate_protocol_number(self, value):
        """Ensure protocol number is unique"""
        if Study.objects.filter(protocol_number=value).exists():
            raise serializers.ValidationError("Protocol number already exists")
        return value

    def validate(self, attrs):
        """Cross-field validation"""
        if attrs.get('status') == 'completed' and not attrs.get('results_file'):
            raise serializers.ValidationError({
                'results_file': 'Results file required for completed studies'
            })
        return attrs
```

### 4. Use Logging

```python
import logging

logger = logging.getLogger(__name__)

def upload_result(request, study_id):
    try:
        study = Study.objects.get(pk=study_id)
        # ... upload logic ...
        logger.info(f"Result uploaded for study {study.protocol_number}")
        return Response({'success': True})
    except Study.DoesNotExist:
        logger.error(f"Study not found: {study_id}")
        return Response({'error': 'Study not found'}, status=404)
    except Exception as e:
        logger.exception(f"Error uploading result for study {study_id}")
        return Response({'error': str(e)}, status=500)
```

### 5. Document Your Code

```python
def calculate_invoice_total(invoice):
    """
    Calculate total invoice amount including tax and discounts.

    Args:
        invoice (Invoice): The invoice to calculate

    Returns:
        Decimal: The total amount

    Formula:
        total = (subtotal - discount) + tax

    Example:
        >>> invoice = Invoice(subtotal=100, tax_amount=21, discount_amount=10)
        >>> calculate_invoice_total(invoice)
        Decimal('111.00')
    """
    return (invoice.subtotal - invoice.discount_amount) + invoice.tax_amount
```

---

## 🚀 Production Deployment

See **DEPLOYMENT.md** for complete production deployment guide.

**Quick reference**:
- Server: Hostinger VPS (72.60.137.226), user: `deploy`
- URL: https://labmolecuar-portal-clientes-staging.com:8443
- App location: `/opt/labcontrol/`
- Deployment: Docker Compose (`docker-compose.prod.yml`)
- Containers (7, all healthy as of 2026-04-25): web, nginx, db, redis, celery_worker, celery_beat, **firebird** (jacobalberty/firebird:2.5-ss — added Phase B, hosts the restored LabWin DB)
- Database: PostgreSQL (Docker volume)
- Static files: Nginx + WhiteNoise
- Media files: Nginx volume mount
- Backup: `/opt/labcontrol/backups/2026-03-22-working-config/`
- Log tailing (added 2026-04-25): `make logs-prod*` from laptop, `labcontrol-logs` wrapper on the VPS

**Critical deployment notes**:
- **NEVER rsync `.env.production`** — it overwrites server credentials with local template values
- **Always `docker compose build` before `up -d --force-recreate`** when changing Python code — the web/celery_worker/celery_beat images COPY `apps/` at build time, so a recreate-only spins up the OLD code (symptom: `docker exec <container> grep` shows the previous version)
- **Rebuild ALL celery images** when adding new Celery tasks — celery_worker and celery_beat use separate Docker images that must be rebuilt independently
- After rebuilding, recreate containers: `docker compose -f docker-compose.prod.yml up -d --force-recreate celery_worker celery_beat`
- **For compose-level config changes (healthchecks, env, volumes)** use `up -d --force-recreate <svc>`, NOT `restart`. `restart` only restarts the running container — it doesn't re-read `docker-compose.yml`, so new healthcheck/env/volumes/network changes are silently ignored.
- `firebirdsql` requires v1.4.5+ (v1.3.0 has a circular import bug that fails during Docker build)
- `passlib` is required by `firebirdsql.services.restore_database` — already in `requirements/base.txt`

---

## 📞 Getting Help

### Documentation
- Django: https://docs.djangoproject.com/en/4.2/
- DRF: https://www.django-rest-framework.org/
- Celery: https://docs.celeryproject.org/
- PostgreSQL: https://www.postgresql.org/docs/15/

### Common Issues

**Issue**: `AttributeError: 'User' object has no attribute 'id'`
**Solution**: Use `.pk` or `.uuid` instead of `.id` (we use UUID primary keys)

**Issue**: Tests failing with database errors
**Solution**: Ensure `DJANGO_SETTINGS_MODULE=config.settings.test` is set

**Issue**: Migrations out of sync
**Solution**: Run `make showmigrations` to check status, then `make migrate`

**Issue**: `firebirdsql` circular import during Docker build
**Solution**: Use `firebirdsql>=1.4.5` (v1.3.0 has a known circular import bug)

**Issue**: Celery tasks not registered after deployment
**Solution**: Rebuild celery Docker images (`docker compose -f docker-compose.prod.yml build celery_worker celery_beat`) and recreate containers (`up -d --force-recreate`, not `restart`). The worker loads tasks on startup from the image, and `restart` doesn't re-read compose-level config.

**Issue**: `.env.production` overwritten during rsync deploy
**Solution**: Exclude `.env.production` from rsync. If overwritten, restore from backup: `cp /opt/labcontrol/backups/2026-03-22-working-config/.env.production.backup /opt/labcontrol/.env.production`

**Issue**: `firebirdsql.services.restore_database` fails with `ModuleNotFoundError: passlib`
**Solution**: Add `passlib` to `requirements/base.txt`, rebuild celery images. Required for the Services API auth.

**Issue**: Backup restore fails with charset errors / mojibake in patient names
**Solution**: Set `LABWIN_FDB_CHARSET=ISO8859_1` in `.env.production`. The source DB has charset `NONE`, so the connector has to declare an explicit charset.

---

**Document Version**: 1.2
**Last Updated**: April 25, 2026
**Maintained By**: Development Team
