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
