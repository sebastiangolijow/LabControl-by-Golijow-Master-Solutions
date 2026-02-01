"""Tests for doctor-related features following TDD principles."""

from django.core.exceptions import ValidationError
from rest_framework import status

from apps.studies.models import Study
from apps.users.models import User
from tests.base import BaseTestCase


class TestStudyDoctorValidation(BaseTestCase):
    """Test cases for Study.ordered_by doctor validation."""

    def test_study_can_have_doctor_in_ordered_by(self):
        """Test that a study can have a doctor in ordered_by field."""
        doctor = self.create_doctor(first_name="John", last_name="Doe")
        patient = self.create_patient()
        study = self.create_study(patient=patient, ordered_by=doctor)

        assert study.ordered_by == doctor
        assert study.ordered_by.role == "doctor"

    def test_study_ordered_by_can_be_null(self):
        """Test that ordered_by can be null (optional field)."""
        patient = self.create_patient()
        study = self.create_study(patient=patient)

        assert study.ordered_by is None

    def test_study_ordered_by_rejects_non_doctor_role(self):
        """Test that ordered_by validation rejects non-doctor users."""
        patient = self.create_patient()
        non_doctor = self.create_patient()  # Creating another patient

        study = Study(
            patient=patient,
            study_type=self.create_study_type(),
            order_number="ORD-2024-TEST-001",
            ordered_by=non_doctor,
            status="pending",
        )

        # Should raise ValidationError when clean() is called
        with self.assertRaises(ValidationError) as context:
            study.clean()

        assert "ordered_by" in context.exception.message_dict
        assert "Only users with 'doctor' role" in str(context.exception)

    def test_study_ordered_by_rejects_admin(self):
        """Test that ordered_by validation rejects admin users."""
        patient = self.create_patient()
        admin = self.create_admin()

        study = Study(
            patient=patient,
            study_type=self.create_study_type(),
            order_number="ORD-2024-TEST-002",
            ordered_by=admin,
            status="pending",
        )

        with self.assertRaises(ValidationError) as context:
            study.clean()

        assert "ordered_by" in context.exception.message_dict

    def test_study_ordered_by_accepts_doctor(self):
        """Test that ordered_by validation accepts doctor users."""
        patient = self.create_patient()
        doctor = self.create_doctor()

        study = Study(
            patient=patient,
            study_type=self.create_study_type(),
            order_number="ORD-2024-TEST-003",
            ordered_by=doctor,
            status="pending",
        )

        # Should not raise ValidationError
        try:
            study.clean()
        except ValidationError:
            self.fail("ValidationError raised for valid doctor")


class TestDoctorPermissions(BaseTestCase):
    """Test cases for doctor-specific permissions."""

    def test_doctor_can_only_see_own_ordered_studies(self):
        """Test that doctors only see studies they ordered."""
        doctor1 = self.create_doctor(first_name="Alice", last_name="Smith")
        doctor2 = self.create_doctor(first_name="Bob", last_name="Jones")
        patient1 = self.create_patient()
        patient2 = self.create_patient()

        # Create studies ordered by different doctors
        study1 = self.create_study(
            patient=patient1, ordered_by=doctor1, order_number="ORD-2024-DOC1"
        )
        study2 = self.create_study(
            patient=patient2, ordered_by=doctor2, order_number="ORD-2024-DOC2"
        )

        # Authenticate as doctor1
        client = self.authenticate(doctor1)
        response = client.get("/api/v1/studies/")

        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        assert len(results) == 1
        assert results[0]["order_number"] == study1.order_number
        assert results[0]["order_number"] != study2.order_number

    def test_doctor_cannot_see_studies_ordered_by_others(self):
        """Test that doctors cannot see studies ordered by other doctors."""
        doctor1 = self.create_doctor()
        doctor2 = self.create_doctor()
        patient = self.create_patient()

        # Create study ordered by doctor2
        _study = self.create_study(patient=patient, ordered_by=doctor2)

        # Authenticate as doctor1
        client = self.authenticate(doctor1)
        response = client.get("/api/v1/studies/")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 0

    def test_doctor_can_download_own_ordered_study_results(self):
        """Test that doctors can download results for studies they ordered."""
        doctor = self.create_doctor()
        patient = self.create_patient()
        study = self.create_study(
            patient=patient, ordered_by=doctor, status="completed"
        )

        # Mock results file (in real scenario, this would be uploaded)
        # For now, we'll just test the permission logic

        client = self.authenticate(doctor)
        response = client.get(f"/api/v1/studies/{study.pk}/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["order_number"] == study.order_number

    def test_doctor_cannot_download_other_doctor_study_results(self):
        """Test that doctors cannot download results ordered by other doctors."""
        doctor1 = self.create_doctor()
        doctor2 = self.create_doctor()
        patient = self.create_patient()
        study = self.create_study(
            patient=patient, ordered_by=doctor2, status="completed"
        )

        # Authenticate as doctor1
        client = self.authenticate(doctor1)
        response = client.get(f"/api/v1/studies/{study.pk}/")

        # Should not be able to see the study
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestStudySerializerDoctorName(BaseTestCase):
    """Test cases for Study serializer ordered_by_name field."""

    def test_serializer_returns_ordered_by_name_when_doctor_assigned(self):
        """Test that serializer returns doctor's full name."""
        doctor = self.create_doctor(first_name="John", last_name="Smith")
        patient = self.create_patient()
        study = self.create_study(patient=patient, ordered_by=doctor)

        client = self.authenticate(patient)
        response = client.get(f"/api/v1/studies/{study.pk}/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["ordered_by_name"] == "John Smith"

    def test_serializer_returns_null_when_no_doctor_assigned(self):
        """Test that serializer returns null when no doctor assigned."""
        patient = self.create_patient()
        study = self.create_study(patient=patient, ordered_by=None)

        client = self.authenticate(patient)
        response = client.get(f"/api/v1/studies/{study.pk}/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["ordered_by_name"] is None

    def test_serializer_includes_ordered_by_uuid(self):
        """Test that serializer includes ordered_by UUID."""
        doctor = self.create_doctor()
        patient = self.create_patient()
        study = self.create_study(patient=patient, ordered_by=doctor)

        client = self.authenticate(patient)
        response = client.get(f"/api/v1/studies/{study.pk}/")

        assert response.status_code == status.HTTP_200_OK
        assert "ordered_by" in response.data
        assert "ordered_by_name" in response.data


class TestAdminUserCreationAPI(BaseTestCase):
    """Test cases for admin user creation endpoint."""

    def test_admin_can_create_doctor(self):
        """Test that admin can create a doctor user."""
        client, admin = self.authenticate_as_admin(is_superuser=True)

        data = {
            "email": "newdoctor@test.com",
            "role": "doctor",
            "first_name": "Jane",
            "last_name": "Doe",
            "phone_number": "+1234567890",
        }

        response = client.post("/api/v1/users/create-user/", data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["user"]["role"] == "doctor"
        assert response.data["user"]["email"] == "newdoctor@test.com"
        assert "User created successfully" in response.data["message"]

        # Verify user was created in database
        user = User.objects.get(email="newdoctor@test.com")
        assert user.role == "doctor"
        assert user.first_name == "Jane"

    def test_admin_can_create_patient(self):
        """Test that admin can create a patient user."""
        client, admin = self.authenticate_as_admin(is_superuser=True)

        data = {
            "email": "newpatient@test.com",
            "role": "patient",
            "first_name": "Bob",
            "last_name": "Smith",
        }

        response = client.post("/api/v1/users/create-user/", data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["user"]["role"] == "patient"

    def test_admin_can_create_admin(self):
        """Test that admin can create another admin user."""
        client, admin = self.authenticate_as_admin(is_superuser=True)

        data = {
            "email": "newadmin@test.com",
            "role": "admin",
            "first_name": "Admin",
            "last_name": "User",
        }

        response = client.post("/api/v1/users/create-user/", data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["user"]["role"] == "admin"

    def test_non_admin_cannot_create_users(self):
        """Test that non-admin users cannot create users."""
        client, patient = self.authenticate_as_patient()

        data = {
            "email": "shouldfail@test.com",
            "role": "doctor",
            "first_name": "Should",
            "last_name": "Fail",
        }

        response = client.post("/api/v1/users/create-user/", data, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_user_with_invalid_role_fails(self):
        """Test that creating user with invalid role fails."""
        client, admin = self.authenticate_as_admin(is_superuser=True)

        data = {
            "email": "invalid@test.com",
            "role": "invalid_role",
            "first_name": "Invalid",
            "last_name": "User",
        }

        response = client.post("/api/v1/users/create-user/", data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_user_with_new_fields(self):
        """Test creating user with new fields (gender, location, etc)."""
        client, admin = self.authenticate_as_admin(is_superuser=True)

        data = {
            "email": "fullprofile@test.com",
            "role": "doctor",
            "first_name": "Complete",
            "last_name": "Profile",
            "phone_number": "+1234567890",
            "gender": "F",
            "location": "New York",
            "direction": "123 Main St",
            "mutual_code": 12345,
            "mutual_name": "Health Insurance Co",
            "carnet": "ABC123456",
        }

        response = client.post("/api/v1/users/create-user/", data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        user = User.objects.get(email="fullprofile@test.com")
        assert user.gender == "F"
        assert user.location == "New York"
        assert user.direction == "123 Main St"
        assert user.mutual_code == 12345
        assert user.mutual_name == "Health Insurance Co"
        assert user.carnet == "ABC123456"


class TestDoctorSearchAPI(BaseTestCase):
    """Test cases for doctor search endpoint."""

    def test_admin_can_search_doctors(self):
        """Test that admin can search for doctors."""
        client, admin = self.authenticate_as_admin(is_superuser=True)

        # Create some doctors
        doctor1 = self.create_doctor(first_name="Alice", last_name="Johnson")
        doctor2 = self.create_doctor(first_name="Bob", last_name="Smith")
        _patient = self.create_patient(first_name="Charlie", last_name="Brown")

        response = client.get("/api/v1/users/search-doctors/")

        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        assert len(results) == 2

        # Verify only doctors are returned
        emails = [r["email"] for r in results]
        assert doctor1.email in emails
        assert doctor2.email in emails

    def test_search_doctors_by_name(self):
        """Test searching doctors by name."""
        client, admin = self.authenticate_as_admin(is_superuser=True)

        doctor1 = self.create_doctor(first_name="Alice", last_name="Johnson")
        _doctor2 = self.create_doctor(first_name="Bob", last_name="Smith")

        response = client.get("/api/v1/users/search-doctors/?search=Alice")

        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        assert len(results) == 1
        assert results[0]["email"] == doctor1.email

    def test_search_doctors_excludes_other_roles(self):
        """Test that doctor search excludes non-doctor users."""
        client, admin = self.authenticate_as_admin(is_superuser=True)

        doctor = self.create_doctor(first_name="Doctor", last_name="Test")
        _patient = self.create_patient(first_name="Patient", last_name="Test")
        _lab_staff = self.create_lab_staff(first_name="Manager", last_name="Test")

        response = client.get("/api/v1/users/search-doctors/")

        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]

        # Should only return the doctor
        assert len(results) == 1
        assert results[0]["email"] == doctor.email
        assert results[0]["role"] == "doctor"

    def test_lab_staff_can_search_doctors_in_their_lab(self):
        """Test that lab managers can search doctors in their lab."""
        client, staff = self.authenticate_as_lab_staff(lab_client_id=1)

        # Create doctors in different labs
        doctor_lab1 = self.create_doctor(
            first_name="Lab1", last_name="Doctor", lab_client_id=1
        )
        _doctor_lab2 = self.create_doctor(
            first_name="Lab2", last_name="Doctor", lab_client_id=2
        )

        response = client.get("/api/v1/users/search-doctors/")

        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]

        # Lab manager should only see doctors from their lab
        assert len(results) == 1
        assert results[0]["email"] == doctor_lab1.email

    def test_non_admin_cannot_search_doctors(self):
        """Test that regular patients cannot search doctors."""
        client, patient = self.authenticate_as_patient()

        response = client.get("/api/v1/users/search-doctors/")

        assert response.status_code == status.HTTP_403_FORBIDDEN
