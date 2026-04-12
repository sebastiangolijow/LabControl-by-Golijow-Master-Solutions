"""Tests for users app following TDD principles."""

from django.contrib.auth import get_user_model
from rest_framework import status

from tests.base import BaseTestCase

User = get_user_model()


class TestUserModel(BaseTestCase):
    """Test cases for User model."""

    def test_create_user(self):
        """Test creating a regular user."""
        user = self.create_user(
            email="newuser@example.com",
            first_name="New",
            last_name="User",
        )
        assert user.email == "newuser@example.com"
        assert user.check_password("testpass123")
        assert user.is_active is True
        assert user.is_staff is False
        assert user.is_superuser is False
        assert user.role == "patient"

    def test_create_superuser(self):
        """Test creating a superuser."""
        user = User.objects.create_superuser(
            email="super@example.com",
            password="superpass123",
        )
        assert user.email == "super@example.com"
        assert user.is_active is True
        assert user.is_staff is True
        assert user.is_superuser is True
        assert user.role == "admin"

    def test_user_has_uuid(self):
        """Test that user has UUID field."""
        user = self.create_user()
        self.assertUUID(user.uuid)

    def test_user_has_timestamps(self):
        """Test that user has timestamp fields."""
        user = self.create_user()
        self.assertIsNotNone(user.date_joined)
        self.assertIsNotNone(user.updated_at)
        self.assertTimestampRecent(user.date_joined)

    def test_user_has_audit_trail(self):
        """Test that user has history tracking."""
        user = self.create_user()
        assert hasattr(user, "history")
        assert user.history.count() == 1  # Created

        # Update user
        user.first_name = "Updated"
        user.save()
        assert user.history.count() == 2  # Created + Updated

    def test_user_created_by(self):
        """Test created_by field."""
        admin = self.create_admin()
        user = self.create_user(created_by=admin)

        assert user.created_by == admin
        assert user in admin.created_users.all()

    def test_user_str_representation(self):
        """Test user string representation."""
        user = self.create_user(email="test@example.com")
        assert str(user) == "test@example.com"

    def test_get_full_name(self):
        """Test getting user's full name."""
        user = self.create_user(
            first_name="John",
            last_name="Doe",
        )
        assert user.get_full_name() == "John Doe"

    def test_get_full_name_fallback(self):
        """Test full name falls back to email if name is empty."""
        user = self.create_user(email="test@example.com", first_name="", last_name="")
        assert user.get_full_name() == "test@example.com"

    def test_user_role_properties(self):
        """Test user role property methods."""
        doctor = self.create_doctor()
        patient = self.create_patient()
        staff = self.create_lab_staff()

        assert doctor.is_doctor is True
        assert doctor.is_patient is False

        assert patient.is_patient is True
        assert patient.is_doctor is False

        assert staff.is_lab_staff is True
        assert staff.is_patient is False

    def test_doctor_patients_property(self):
        """Test that doctor.patients returns unique patients from ordered studies."""
        # Create doctor and patients
        doctor = self.create_doctor()
        patient1 = self.create_patient(email="patient1@test.com")
        patient2 = self.create_patient(email="patient2@test.com")
        patient3 = self.create_patient(email="patient3@test.com")

        # Create studies ordered by this doctor
        study1 = self.create_study(patient=patient1, ordered_by=doctor)
        study2 = self.create_study(patient=patient2, ordered_by=doctor)
        # Create another study for patient1 (should not duplicate)
        study3 = self.create_study(patient=patient1, ordered_by=doctor)

        # Get doctor's patients
        doctor_patients = doctor.patients

        # Should return 2 unique patients (patient1 and patient2)
        assert doctor_patients.count() == 2
        assert patient1 in doctor_patients
        assert patient2 in doctor_patients
        assert patient3 not in doctor_patients  # Not ordered by this doctor

        # Should return User objects with role='patient'
        for patient in doctor_patients:
            assert patient.role == "patient"

    def test_doctor_patients_property_empty(self):
        """Test that doctor.patients returns empty queryset when no studies ordered."""
        doctor = self.create_doctor()

        # Doctor has no studies
        assert doctor.patients.count() == 0

    def test_non_doctor_patients_property(self):
        """Test that non-doctor users get empty queryset from patients property."""
        # Create different role users
        patient = self.create_patient()
        admin = self.create_admin()
        staff = self.create_lab_staff()

        # Create a study to ensure there's data in the database
        doctor = self.create_doctor()
        self.create_study(patient=patient, ordered_by=doctor)

        # Non-doctors should always get empty queryset
        assert patient.patients.count() == 0
        assert admin.patients.count() == 0
        assert staff.patients.count() == 0

    def test_doctor_patients_property_is_queryset(self):
        """Test that doctor.patients returns a QuerySet that can be filtered."""
        doctor = self.create_doctor()
        patient1 = self.create_patient(
            email="patient1@test.com", first_name="Alice", last_name="Smith"
        )
        patient2 = self.create_patient(
            email="patient2@test.com", first_name="Bob", last_name="Jones"
        )

        self.create_study(patient=patient1, ordered_by=doctor)
        self.create_study(patient=patient2, ordered_by=doctor)

        # Test that it returns a QuerySet
        doctor_patients = doctor.patients
        assert hasattr(doctor_patients, "filter")
        assert hasattr(doctor_patients, "order_by")

        # Test filtering
        alice_only = doctor_patients.filter(first_name="Alice")
        assert alice_only.count() == 1
        assert patient1 in alice_only

        # Test ordering
        ordered_patients = doctor_patients.order_by("first_name")
        assert list(ordered_patients) == [patient1, patient2]


class TestUserManager(BaseTestCase):
    """Test cases for User custom manager."""

    def test_active_users(self):
        """Test UserManager.active() method."""
        active_user = self.create_user(is_active=True)
        inactive_user = self.create_user(email="inactive@test.com", is_active=False)

        active_users = User.objects.active()
        assert active_user in active_users
        assert inactive_user not in active_users

    def test_inactive_users(self):
        """Test UserQuerySet.inactive() method."""
        active_user = self.create_user(is_active=True)
        inactive_user = self.create_user(email="inactive@test.com", is_active=False)

        inactive_users = User.objects.inactive()
        assert inactive_user in inactive_users
        assert active_user not in inactive_users

    def test_by_role(self):
        """Test UserManager.by_role() method."""
        doctor = self.create_doctor()
        patient = self.create_patient()

        doctors = User.objects.by_role("doctor")
        assert doctor in doctors
        assert patient not in doctors

    def test_admins(self):
        """Test UserManager.admins() method."""
        admin = self.create_admin()
        patient = self.create_patient()

        admins = User.objects.admins()
        assert admin in admins
        assert patient not in admins

    def test_lab_staff(self):
        """Test UserManager.lab_staff() method."""
        staff = self.create_lab_staff()
        patient = self.create_patient()

        lab_staff = User.objects.lab_staff()
        assert staff in lab_staff
        assert patient not in lab_staff

    def test_patients(self):
        """Test UserManager.patients() method."""
        patient = self.create_patient()
        doctor = self.create_doctor()

        patients = User.objects.patients()
        assert patient in patients
        assert doctor not in patients

    def test_for_lab(self):
        """Test UserManager.for_lab() method."""
        lab1_user = self.create_user(lab_client_id=1)
        lab2_user = self.create_user(email="lab2@test.com", lab_client_id=2)

        lab1_users = User.objects.for_lab(1)
        assert lab1_user in lab1_users
        assert lab2_user not in lab1_users

    def test_verified_users(self):
        """Test UserQuerySet.verified() method."""
        verified = self.create_user(is_verified=True)
        unverified = self.create_user(email="unverified@test.com", is_verified=False)

        verified_users = User.objects.verified()
        assert verified in verified_users
        assert unverified not in verified_users

    def test_chainable_queries(self):
        """Test that manager methods are chainable."""
        lab1_patient = self.create_patient(lab_client_id=1, is_active=True)
        lab2_patient = self.create_patient(
            email="lab2@test.com", lab_client_id=2, is_active=True
        )
        lab1_doctor = self.create_doctor(lab_client_id=1, is_active=True)
        inactive_patient = self.create_patient(
            email="inactive@test.com", lab_client_id=1, is_active=False
        )

        # Chain: active patients in lab 1
        result = User.objects.active().patients().for_lab(1)

        assert lab1_patient in result
        assert lab2_patient not in result
        assert lab1_doctor not in result
        assert inactive_patient not in result


class TestUserAPI(BaseTestCase):
    """Test cases for User API endpoints."""

    def test_get_current_user_profile(self):
        """Test getting current user's profile."""
        client, user = self.authenticate_as_patient()
        response = client.get("/api/v1/users/me/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["email"] == user.email

    def test_update_user_profile(self):
        """Test updating user profile."""
        client, user = self.authenticate_as_patient()

        data = {
            "first_name": "Updated",
            "last_name": "Name",
        }
        response = client.put("/api/v1/users/update_profile/", data)

        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.first_name == "Updated"
        assert user.last_name == "Name"

    def test_list_users_as_admin(self):
        """Test listing users as admin."""
        client, admin = self.authenticate_as_admin()

        # Create some users
        self.create_patient()
        self.create_doctor()

        response = client.get("/api/v1/users/")
        assert response.status_code == status.HTTP_200_OK
        # Should see all users including admin
        assert len(response.data["results"]) >= 3

    def test_list_users_as_patient_restricted(self):
        """Test that patients can only see themselves."""
        client, patient = self.authenticate_as_patient()

        # Create another user
        self.create_doctor()

        response = client.get("/api/v1/users/")
        assert response.status_code == status.HTTP_200_OK
        # Should only see their own user
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["email"] == patient.email

    def test_user_uuid_in_api_response(self):
        """Test that UUID is included in API responses."""
        client, user = self.authenticate_as_patient()
        response = client.get("/api/v1/users/me/")

        assert response.status_code == status.HTTP_200_OK
        assert "uuid" in response.data
        self.assertUUID(user.uuid)

    def test_list_users_as_doctor_only_sees_own_patients(self):
        """Test that a doctor only sees patients with studies ordered by them."""
        client, doctor = self.authenticate_as_doctor()

        # Create patients related to this doctor (via studies)
        own_patient1 = self.create_patient(email="own1@test.com")
        own_patient2 = self.create_patient(email="own2@test.com")
        self.create_study(patient=own_patient1, ordered_by=doctor)
        self.create_study(patient=own_patient2, ordered_by=doctor)

        # Create a patient NOT related to this doctor
        other_doctor = self.create_doctor(email="otherdoctor@test.com")
        unrelated_patient = self.create_patient(email="unrelated@test.com")
        self.create_study(patient=unrelated_patient, ordered_by=other_doctor)

        response = client.get("/api/v1/users/")

        assert response.status_code == status.HTTP_200_OK
        returned_emails = [u["email"] for u in response.data["results"]]

        # Doctor should see their own patients
        assert own_patient1.email in returned_emails
        assert own_patient2.email in returned_emails

        # Doctor should NOT see unrelated patients
        assert unrelated_patient.email not in returned_emails

        # Doctor should NOT see themselves or other doctors/staff
        assert doctor.email not in returned_emails
        assert other_doctor.email not in returned_emails


class TestDoctorRoleBasedValidation(BaseTestCase):
    """Test cases for doctor-specific role-based validation."""

    def test_create_doctor_with_email_via_api(self):
        """Test creating a doctor with email via admin API."""
        client, admin = self.authenticate_as_admin()

        data = {
            "email": "doctor@test.com",
            "role": "doctor",
            "first_name": "Dr. Juan",
            "last_name": "Perez",
            "matricula": "MP12345",
        }
        response = client.post("/api/v1/users/create-user/", data)

        assert response.status_code == status.HTTP_201_CREATED, f"Failed with: {response.data}"
        assert "user" in response.data
        user_data = response.data["user"]
        assert user_data["email"] == "doctor@test.com"
        assert user_data["role"] == "doctor"
        assert user_data["matricula"] == "MP12345"
        assert user_data["first_name"] == "Dr. Juan"
        assert user_data["last_name"] == "Perez"

        # Verify doctor was created in database
        doctor = User.objects.get(email="doctor@test.com")
        assert doctor.role == "doctor"
        assert doctor.matricula == "MP12345"
        assert doctor.is_doctor is True

    def test_create_doctor_without_email_via_api(self):
        """Test creating a doctor without email via admin API (email is optional for doctors)."""
        client, admin = self.authenticate_as_admin()

        data = {
            "role": "doctor",
            "first_name": "Dr. Maria",
            "last_name": "Gomez",
            "matricula": "MG54321",
        }
        response = client.post("/api/v1/users/create-user/", data)

        assert response.status_code == status.HTTP_201_CREATED
        assert "user" in response.data
        user_data = response.data["user"]
        assert user_data["email"] is None or user_data["email"] == ""
        assert user_data["role"] == "doctor"
        assert user_data["matricula"] == "MG54321"
        assert user_data["first_name"] == "Dr. Maria"
        assert user_data["last_name"] == "Gomez"

        # Verify doctor was created in database without email
        doctors = User.objects.filter(first_name="Dr. Maria", last_name="Gomez", role="doctor")
        assert doctors.count() == 1
        doctor = doctors.first()
        assert doctor.email is None or doctor.email == ""
        assert doctor.matricula == "MG54321"

    def test_create_doctor_without_matricula_fails(self):
        """Test that creating a doctor without matricula fails validation."""
        client, admin = self.authenticate_as_admin()

        data = {
            "email": "doctor_no_matricula@test.com",
            "role": "doctor",
            "first_name": "Dr. Roberto",
            "last_name": "Sanchez",
            # Missing matricula
        }
        response = client.post("/api/v1/users/create-user/", data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "matricula" in response.data
        assert "required" in str(response.data["matricula"]).lower()

        # Verify doctor was NOT created
        assert not User.objects.filter(email="doctor_no_matricula@test.com").exists()

    def test_create_doctor_without_first_name_fails(self):
        """Test that creating a doctor without first_name fails validation."""
        client, admin = self.authenticate_as_admin()

        data = {
            "role": "doctor",
            # Missing first_name
            "last_name": "Lopez",
            "matricula": "ML11111",
        }
        response = client.post("/api/v1/users/create-user/", data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "first_name" in response.data

    def test_create_doctor_without_last_name_fails(self):
        """Test that creating a doctor without last_name fails validation."""
        client, admin = self.authenticate_as_admin()

        data = {
            "role": "doctor",
            "first_name": "Dr. Carlos",
            # Missing last_name
            "matricula": "MC22222",
        }
        response = client.post("/api/v1/users/create-user/", data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "last_name" in response.data

    def test_create_patient_requires_email(self):
        """Test that creating a patient requires email (unlike doctors)."""
        client, admin = self.authenticate_as_admin()

        data = {
            "role": "patient",
            "first_name": "Ana",
            "last_name": "Martinez",
            "phone_number": "123456789",
            "dni": "12345678",
            "birthday": "1990-01-01",
            # Missing email
        }
        response = client.post("/api/v1/users/create-user/", data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "email" in response.data
        assert "required" in str(response.data["email"]).lower()

    def test_create_admin_requires_email(self):
        """Test that creating an admin requires email (unlike doctors)."""
        client, admin = self.authenticate_as_admin()

        data = {
            "role": "admin",
            "first_name": "Admin",
            "last_name": "User",
            # Missing email
        }
        response = client.post("/api/v1/users/create-user/", data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "email" in response.data
        assert "required" in str(response.data["email"]).lower()

    def test_create_lab_staff_requires_email(self):
        """Test that creating lab staff requires email (unlike doctors)."""
        client, admin = self.authenticate_as_admin()

        data = {
            "role": "lab_staff",
            "first_name": "Lab",
            "last_name": "Staff",
            # Missing email
        }
        response = client.post("/api/v1/users/create-user/", data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "email" in response.data
        assert "required" in str(response.data["email"]).lower()

    def test_create_patient_with_full_profile(self):
        """Test creating a patient with full profile (all required fields)."""
        client, admin = self.authenticate_as_admin()

        data = {
            "email": "patient@test.com",
            "role": "patient",
            "first_name": "Carlos",
            "last_name": "Lopez",
            "phone_number": "987654321",
            "dni": "87654321",
            "birthday": "1985-05-15",
        }
        response = client.post("/api/v1/users/create-user/", data)

        assert response.status_code == status.HTTP_201_CREATED
        assert "user" in response.data
        user_data = response.data["user"]
        assert user_data["email"] == "patient@test.com"
        assert user_data["role"] == "patient"
        assert user_data["phone_number"] == "987654321"
        assert user_data["dni"] == "87654321"
        assert user_data["birthday"] == "1985-05-15"

    def test_create_patient_missing_phone_fails(self):
        """Test that creating a patient without phone_number fails."""
        client, admin = self.authenticate_as_admin()

        data = {
            "email": "patient_no_phone@test.com",
            "role": "patient",
            "first_name": "Test",
            "last_name": "Patient",
            "dni": "11111111",
            "birthday": "1990-01-01",
            # Missing phone_number
        }
        response = client.post("/api/v1/users/create-user/", data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "phone_number" in response.data

    def test_create_patient_missing_dni_fails(self):
        """Test that creating a patient without DNI fails."""
        client, admin = self.authenticate_as_admin()

        data = {
            "email": "patient_no_dni@test.com",
            "role": "patient",
            "first_name": "Test",
            "last_name": "Patient",
            "phone_number": "123456789",
            "birthday": "1990-01-01",
            # Missing dni
        }
        response = client.post("/api/v1/users/create-user/", data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "dni" in response.data

    def test_create_patient_missing_birthday_fails(self):
        """Test that creating a patient without birthday fails."""
        client, admin = self.authenticate_as_admin()

        data = {
            "email": "patient_no_birthday@test.com",
            "role": "patient",
            "first_name": "Test",
            "last_name": "Patient",
            "phone_number": "123456789",
            "dni": "22222222",
            # Missing birthday
        }
        response = client.post("/api/v1/users/create-user/", data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "birthday" in response.data

    def test_doctor_optional_fields_allowed(self):
        """Test that doctors can be created without optional fields (dni, phone, birthday)."""
        client, admin = self.authenticate_as_admin()

        data = {
            "role": "doctor",
            "first_name": "Dr. Simple",
            "last_name": "Doctor",
            "matricula": "SD99999",
            # No email, dni, phone_number, birthday, address, insurance - all optional for doctors
        }
        response = client.post("/api/v1/users/create-user/", data)

        assert response.status_code == status.HTTP_201_CREATED
        assert "user" in response.data
        user_data = response.data["user"]
        assert user_data["role"] == "doctor"
        assert user_data["matricula"] == "SD99999"

        # Verify optional fields are None/empty
        doctor = User.objects.get(matricula="SD99999")
        assert doctor.email is None or doctor.email == ""
        assert doctor.dni == ""
        assert doctor.phone_number == ""
        assert doctor.birthday is None

    def test_matricula_field_in_doctor_response(self):
        """Test that matricula field is included in API responses for doctors."""
        client, admin = self.authenticate_as_admin()

        # Create doctor
        data = {
            "role": "doctor",
            "first_name": "Dr. Test",
            "last_name": "Matricula",
            "matricula": "TM77777",
        }
        create_response = client.post("/api/v1/users/create-user/", data)
        assert create_response.status_code == status.HTTP_201_CREATED
        assert "user" in create_response.data

        # Get doctor details
        doctor_id = create_response.data["user"]["id"]
        get_response = client.get(f"/api/v1/users/{doctor_id}/")
        assert get_response.status_code == status.HTTP_200_OK
        assert "matricula" in get_response.data
        assert get_response.data["matricula"] == "TM77777"

    def test_multiple_doctors_without_email(self):
        """Test that multiple doctors can be created without email (NULL emails allowed)."""
        client, admin = self.authenticate_as_admin()

        # Create first doctor without email
        data1 = {
            "role": "doctor",
            "first_name": "Dr. First",
            "last_name": "NoEmail",
            "matricula": "FNE001",
        }
        response1 = client.post("/api/v1/users/create-user/", data1)
        assert response1.status_code == status.HTTP_201_CREATED

        # Create second doctor without email
        data2 = {
            "role": "doctor",
            "first_name": "Dr. Second",
            "last_name": "NoEmail",
            "matricula": "SNE002",
        }
        response2 = client.post("/api/v1/users/create-user/", data2)
        assert response2.status_code == status.HTTP_201_CREATED

        # Verify both doctors exist
        doctors = User.objects.filter(role="doctor", last_name="NoEmail")
        assert doctors.count() == 2
