# Backend Changes: Doctor Fields & Study Date Renaming

**Date**: April 11, 2026
**Status**: ✅ Implemented (Migrations pending execution)

---

## 📋 Summary of Changes

This document outlines all backend changes made to address laboratory feedback regarding:
1. Flexible required fields for doctor users
2. Safe doctor deletion without losing related studies
3. Renamed study date fields with proper Spanish labels

---

## 🔧 Changes Implemented

### 1. User Model - Doctor Support (`apps/users/models.py`)

#### **Added Fields**:
- **`matricula`** (CharField, max_length=50, blank=True)
  - Purpose: Medical license number for doctors
  - Required for doctors only
  - Optional for other roles

- **`deleted_at`** (DateTimeField, null=True, blank=True)
  - Purpose: Soft-delete timestamp
  - Allows preserving user records when deleted
  - Prevents login when set (used with `is_active=False`)

#### **New Methods**:
```python
user.soft_delete()  # Soft-delete user (sets deleted_at, is_active=False)
user.restore()      # Restore soft-deleted user
user.is_deleted     # Property to check if user is deleted
```

#### **Migration**:
- `apps/users/migrations/0002_add_matricula_and_soft_delete.py`
- Adds `matricula` and `deleted_at` to both `User` and `HistoricalUser` models

---

### 2. Study Model - Date Field Renaming (`apps/studies/models.py`)

#### **Field Changes**:

| Old Field Name | New Field Name | New Verbose Name | Purpose |
|----------------|----------------|------------------|---------|
| `sample_collected_at` | `service_date` | `fecha de atención` | Date of service/sample collection |
| `completed_at` | `completed_at` (unchanged) | `fecha de entrega` | Date results were delivered |
| `solicited_date` | `solicited_date` (unchanged) | `fecha de solicitud` | Date study was requested |

#### **Migration**:
- `apps/studies/migrations/0004_rename_sample_collected_at_and_update_labels.py`
- Renames `sample_collected_at` → `service_date`
- Updates verbose_name for all date fields with Spanish labels
- Updates both `Study` and `HistoricalStudy` models

---

### 3. Serializer Updates

#### **User Serializers** (`apps/users/serializers.py`)

**a) UserSerializer**:
- Added `matricula` field to all user serializations

**b) UserCreateSerializer**:
- Added `matricula` to fields list

**c) UserUpdateSerializer**:
- Added `matricula` to updatable fields

**d) AdminUserCreateSerializer** (MAJOR UPDATE):
- **Removed hard-coded `extra_kwargs`** (fields no longer universally required)
- **Implemented role-based validation** in `validate()` method:

  **Doctor Role Requirements**:
  - ✅ `email` (required)
  - ✅ `first_name` (required)
  - ✅ `last_name` (required)
  - ✅ `matricula` (required)
  - ❌ phone_number, dni, birthday, address, etc. (optional)

  **Patient Role Requirements**:
  - ✅ `email` (required)
  - ✅ `first_name` (required)
  - ✅ `last_name` (required)
  - ✅ `phone_number` (required)
  - ✅ `dni` (required)
  - ✅ `birthday` (required)
  - ❌ matricula, address, etc. (optional)

  **Admin/Lab Staff Role Requirements**:
  - ✅ `email` (required)
  - ✅ `first_name` (required)
  - ✅ `last_name` (required)
  - ❌ All other fields (optional)

#### **Study Serializers** (`apps/studies/serializers.py`)

**Updated Fields**:
- `StudySerializer`: Changed `sample_collected_at` → `service_date`
- `StudyCreateSerializer`: Changed `sample_collected_at` → `service_date`
- Added inline comments for clarity

---

## 🔐 Doctor Deletion Safety

### Current Behavior (Already Safe ✅)

The `Study.ordered_by` field uses `on_delete=models.SET_NULL`:
```python
ordered_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.SET_NULL,  # ← Protects studies when doctor is deleted
    null=True,
    blank=True,
    related_name='ordered_studies',
)
```

### What This Means:
1. **Hard Delete**: When doctor is deleted, `study.ordered_by` is set to `NULL` (study is preserved)
2. **Soft Delete**: New `soft_delete()` method sets `deleted_at` and `is_active=False`
   - Preserves user record completely
   - Studies remain linked to doctor
   - Doctor cannot log in
   - Can be restored later if needed

### Recommended Practice:
**Always use `user.soft_delete()` instead of `user.delete()`** for doctor accounts.

---

## 📊 Database Migrations

### Migration Files Created:

1. **`apps/users/migrations/0002_add_matricula_and_soft_delete.py`**
   - Adds `matricula` field to User model
   - Adds `deleted_at` field to User model
   - Updates HistoricalUser model

2. **`apps/users/migrations/0003_alter_historicaluser_email_alter_user_email.py`**
   - Makes email field optional (blank=True, null=True)
   - Allows doctors to be created without email addresses
   - Updates both User and HistoricalUser models

3. **`apps/studies/migrations/0004_rename_sample_collected_at_and_update_labels.py`**
   - Renames `sample_collected_at` → `service_date`
   - Updates verbose_name for `solicited_date` → "fecha de solicitud"
   - Updates verbose_name for `service_date` → "fecha de atención"
   - Updates verbose_name for `completed_at` → "fecha de entrega"
   - Updates HistoricalStudy model

### To Apply Migrations:

```bash
# Start Docker containers
make up

# Run migrations
make migrate

# Or manually:
docker compose exec backend python manage.py migrate
```

---

## 🧪 Testing Checklist

### Manual Testing Required:

#### 1. Doctor Creation with Minimal Fields (with email)
```bash
POST /api/v1/users/create-user/
{
  "email": "doctor@example.com",
  "role": "doctor",
  "first_name": "Dr. Juan",
  "last_name": "Perez",
  "matricula": "MP12345"
}
# Should succeed ✅
```

#### 1b. Doctor Creation without Email
```bash
POST /api/v1/users/create-user/
{
  "role": "doctor",
  "first_name": "Dr. Juan",
  "last_name": "Perez",
  "matricula": "MP12345"
}
# Should succeed ✅ (email is optional for doctors)
```

#### 2. Doctor Creation Without Matricula
```bash
POST /api/v1/users/create-user/
{
  "email": "doctor2@example.com",
  "role": "doctor",
  "first_name": "Dr. Maria",
  "last_name": "Gomez"
}
# Should fail with: "Matricula is required for doctors." ❌
```

#### 3. Patient Creation with Full Profile
```bash
POST /api/v1/users/create-user/
{
  "email": "patient@example.com",
  "role": "patient",
  "first_name": "Carlos",
  "last_name": "Lopez",
  "phone_number": "123456789",
  "dni": "12345678",
  "birthday": "1990-01-01"
}
# Should succeed ✅
```

#### 4. Patient Creation with Missing Required Field
```bash
POST /api/v1/users/create-user/
{
  "email": "patient2@example.com",
  "role": "patient",
  "first_name": "Ana",
  "last_name": "Martinez"
  # Missing: phone_number, dni, birthday
}
# Should fail with validation errors ❌
```

#### 5. Study Creation/Retrieval with New Field Names
```bash
GET /api/v1/studies/{uuid}/
# Response should include:
{
  "service_date": "2026-04-11T10:00:00Z",  # ← New field name
  "completed_at": "2026-04-12T15:30:00Z",
  "solicited_date": "2026-04-10"
}
```

#### 6. Doctor Soft Delete
```python
# In Django shell:
from apps.users.models import User

doctor = User.objects.get(email='doctor@example.com')
doctor.soft_delete()

# Verify:
assert doctor.deleted_at is not None
assert doctor.is_active == False
assert doctor.is_deleted == True

# Studies should still exist:
studies = doctor.ordered_studies.all()
assert studies.count() > 0  # Studies preserved
```

---

## 📝 API Documentation Updates Needed

### Updated Request/Response Examples:

#### POST `/api/v1/users/create-user/` (Doctor)
**Request**:
```json
{
  "email": "doctor@clinic.com",
  "role": "doctor",
  "first_name": "Dr. Roberto",
  "last_name": "Sanchez",
  "matricula": "MN98765"
}
```

**Response**:
```json
{
  "id": "uuid-here",
  "email": "doctor@clinic.com",
  "role": "doctor",
  "first_name": "Dr. Roberto",
  "last_name": "Sanchez",
  "matricula": "MN98765",
  "phone_number": "",
  "dni": "",
  "birthday": null,
  ...
}
```

#### GET `/api/v1/studies/{id}/`
**Response** (note renamed fields):
```json
{
  "id": "uuid-here",
  "protocol_number": "2026-001234",
  "patient": "patient-uuid",
  "practice": "practice-uuid",
  "ordered_by": "doctor-uuid",
  "status": "completed",
  "solicited_date": "2026-04-10",
  "service_date": "2026-04-11T09:00:00Z",   ← Renamed from sample_collected_at
  "completed_at": "2026-04-12T14:00:00Z",   ← fecha de entrega
  "results_file": "https://...",
  ...
}
```

---

## 🚀 Deployment Steps

1. **Backup Database**:
   ```bash
   docker compose exec db pg_dump -U labcontrol_user labcontrol_db > backup_$(date +%Y%m%d).sql
   ```

2. **Pull Latest Code**:
   ```bash
   git pull origin main
   ```

3. **Run Migrations**:
   ```bash
   make migrate
   ```

4. **Verify Migrations**:
   ```bash
   make showmigrations
   # Should show:
   # [X] users.0002_add_matricula_and_soft_delete
   # [X] studies.0004_rename_sample_collected_at_and_update_labels
   ```

5. **Test Doctor Creation**:
   - Create a test doctor with minimal fields
   - Verify matricula is required
   - Verify phone/DNI/birthday are optional

6. **Test Study Endpoints**:
   - Verify `service_date` field is returned
   - Verify `sample_collected_at` is not in response
   - Update frontend if needed

---

## 🔄 Backward Compatibility

### Breaking Changes:
1. **API Field Rename**: `sample_collected_at` → `service_date`
   - **Impact**: Frontend must update field references
   - **Migration**: Frontend should handle both field names during transition

2. **Doctor Validation**: Matricula now required for doctor role
   - **Impact**: Doctor creation without matricula will fail
   - **Migration**: Existing doctors without matricula are unaffected (blank allowed)

### Non-Breaking Changes:
- `matricula` field added (optional for existing users)
- `deleted_at` field added (null by default)
- Verbose name changes (backend only, doesn't affect API)

---

## 📚 Frontend Changes Required

### 1. Update Study TypeScript Interfaces:
```typescript
// OLD
interface Study {
  sample_collected_at: string;  // ❌ Remove
  completed_at: string;
}

// NEW
interface Study {
  service_date: string;         // ✅ Add (fecha de atención)
  completed_at: string;         // ✅ Keep (fecha de entrega)
  solicited_date: string;       // ✅ Keep (fecha de solicitud)
}
```

### 2. Update User TypeScript Interfaces:
```typescript
interface User {
  email: string;
  first_name: string;
  last_name: string;
  matricula?: string;  // ✅ Add (optional)
  dni?: string;        // Make optional for doctors
  phone_number?: string; // Make optional for doctors
  birthday?: string;   // Make optional for doctors
  role: 'admin' | 'lab_staff' | 'doctor' | 'patient';
}
```

### 3. Update Doctor Creation Form:
```typescript
// Required fields for doctors:
const doctorRequiredFields = ['email', 'first_name', 'last_name', 'matricula'];

// Required fields for patients:
const patientRequiredFields = [
  'email', 'first_name', 'last_name',
  'phone_number', 'dni', 'birthday'
];
```

### 4. Update Study Display Labels:
```typescript
const studyDateLabels = {
  solicited_date: 'Fecha de Solicitud',
  service_date: 'Fecha de Atención',      // Updated label
  completed_at: 'Fecha de Entrega',       // Updated label
};
```

---

## ✅ Summary

### What Was Fixed:

1. ✅ **Doctor fields are now flexible**
   - Doctors only need: email, first_name, last_name, matricula
   - Phone, DNI, birthday, address are optional

2. ✅ **Doctor deletion is safe**
   - `Study.ordered_by` uses `SET_NULL` (already safe)
   - New `soft_delete()` method preserves all data
   - Studies are never lost when doctor is deleted

3. ✅ **Study date fields renamed with proper Spanish labels**
   - `sample_collected_at` → `service_date` (fecha de atención)
   - `completed_at` → labeled as "fecha de entrega"
   - `solicited_date` → labeled as "fecha de solicitud"

### Files Modified:
- `apps/users/models.py` (added matricula, deleted_at, soft_delete methods)
- `apps/users/serializers.py` (role-based validation)
- `apps/studies/models.py` (renamed field, updated labels)
- `apps/studies/serializers.py` (updated field references)
- `apps/users/migrations/0002_add_matricula_and_soft_delete.py` (new)
- `apps/studies/migrations/0004_rename_sample_collected_at_and_update_labels.py` (new)

### Next Steps:
1. Apply migrations: `make migrate`
2. Test doctor creation with minimal fields
3. Test study endpoints with new field names
4. Update frontend TypeScript interfaces
5. Update frontend forms and labels
6. Deploy to staging for laboratory testing

---

**End of Document**
