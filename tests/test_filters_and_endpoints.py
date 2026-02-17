"""Tests for django_filters integration and new endpoints."""

from django.contrib.auth import get_user_model
from rest_framework import status

from apps.studies.models import Study
from tests.base import BaseTestCase

User = get_user_model()


class TestUserFilter(BaseTestCase):
    """Test cases for UserFilter with django_filters."""

    def test_user_search_filter_by_email(self):
        """Test searching users by email."""
        client, admin = self.authenticate_as_admin()

        # Create test users
        user1 = self.create_patient(email="john.doe@example.com")
        user2 = self.create_patient(email="jane.smith@example.com")

        # Search by email
        response = client.get("/api/v1/users/?search=john.doe")
        assert response.status_code == status.HTTP_200_OK
        emails = [u["email"] for u in response.data["results"]]
        assert user1.email in emails
        assert user2.email not in emails

    def test_user_search_filter_by_first_name(self):
        """Test searching users by first name."""
        client, admin = self.authenticate_as_admin()

        # Create test users
        user1 = self.create_patient(first_name="Alexander")
        user2 = self.create_patient(first_name="Benjamin")

        # Search by first name
        response = client.get("/api/v1/users/?search=Alex")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        assert any(u["first_name"] == "Alexander" for u in results)
        assert not any(u["first_name"] == "Benjamin" for u in results)

    def test_user_search_filter_by_last_name(self):
        """Test searching users by last name."""
        client, admin = self.authenticate_as_admin()

        # Create test users
        user1 = self.create_patient(last_name="Johnson")
        user2 = self.create_patient(last_name="Williams")

        # Search by last name
        response = client.get("/api/v1/users/?search=Johnson")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        assert any(u["last_name"] == "Johnson" for u in results)
        assert not any(u["last_name"] == "Williams" for u in results)

    def test_user_search_filter_by_dni(self):
        """Test searching users by DNI."""
        client, admin = self.authenticate_as_admin()

        # Create test users
        user1 = self.create_patient(dni="12345678")
        user2 = self.create_patient(dni="87654321")

        # Search by DNI
        response = client.get("/api/v1/users/?search=12345678")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        assert any(u["dni"] == "12345678" for u in results)
        assert not any(u["dni"] == "87654321" for u in results)

    def test_user_filter_by_role(self):
        """Test filtering users by role."""
        client, admin = self.authenticate_as_admin()

        # Create users with different roles
        doctor = self.create_doctor()
        patient = self.create_patient()

        # Filter by doctor role
        response = client.get("/api/v1/users/?role=doctor")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        assert any(u["email"] == doctor.email for u in results)
        assert not any(u["email"] == patient.email for u in results)

    def test_user_filter_by_is_active(self):
        """Test filtering users by is_active status."""
        client, admin = self.authenticate_as_admin()

        # Create active and inactive users
        active_user = self.create_patient(is_active=True)
        inactive_user = self.create_patient(email="inactive@test.com", is_active=False)

        # Filter by active users
        response = client.get("/api/v1/users/?is_active=true")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        assert any(u["email"] == active_user.email for u in results)
        assert not any(u["email"] == inactive_user.email for u in results)

    def test_user_filter_by_lab_client_id(self):
        """Test filtering users by lab_client_id."""
        client, admin = self.authenticate_as_admin()

        # Create users in different labs
        lab1_user = self.create_patient(lab_client_id=1)
        lab2_user = self.create_patient(email="lab2@test.com", lab_client_id=2)

        # Filter by lab 1
        response = client.get("/api/v1/users/?lab_client_id=1")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        assert any(u["email"] == lab1_user.email for u in results)
        assert not any(u["email"] == lab2_user.email for u in results)


class TestStudyFilter(BaseTestCase):
    """Test cases for StudyFilter with django_filters."""

    def test_study_search_filter_by_protocol_number(self):
        """Test searching studies by protocol number."""
        client, admin = self.authenticate_as_admin()

        # Create test studies
        study1 = self.create_study(protocol_number="ORD-2024-0001")
        study2 = self.create_study(protocol_number="ORD-2024-0002")

        # Search by protocol number
        response = client.get("/api/v1/studies/?search=0001")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        assert any(s["protocol_number"] == "ORD-2024-0001" for s in results)
        assert not any(s["protocol_number"] == "ORD-2024-0002" for s in results)

    def test_study_search_filter_by_patient_name(self):
        """Test searching studies by patient name."""
        client, admin = self.authenticate_as_admin()

        # Create patients with studies
        patient1 = self.create_patient(first_name="Michael", last_name="Jordan")
        patient2 = self.create_patient(first_name="LeBron", last_name="James")
        study1 = self.create_study(patient=patient1)
        study2 = self.create_study(patient=patient2)

        # Search by patient first name
        response = client.get("/api/v1/studies/?search=Michael")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        assert any(s["protocol_number"] == study1.protocol_number for s in results)
        assert not any(s["protocol_number"] == study2.protocol_number for s in results)

    def test_study_search_filter_by_practice_name(self):
        """Test searching studies by practice name."""
        client, admin = self.authenticate_as_admin()

        # Create practices and studies
        practice1 = self.create_practice(name="Blood Test")
        practice2 = self.create_practice(name="X-Ray Scan")
        study1 = self.create_study(practice=practice1)
        study2 = self.create_study(practice=practice2)

        # Search by practice name
        response = client.get("/api/v1/studies/?search=Blood")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        assert any(s["protocol_number"] == study1.protocol_number for s in results)
        assert not any(s["protocol_number"] == study2.protocol_number for s in results)

    def test_study_filter_by_status(self):
        """Test filtering studies by status."""
        client, admin = self.authenticate_as_admin()

        # Create studies with different statuses
        pending_study = self.create_study(status="pending")
        completed_study = self.create_study(status="completed")

        # Filter by pending status
        response = client.get("/api/v1/studies/?status=pending")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        assert any(s["protocol_number"] == pending_study.protocol_number for s in results)
        assert not any(
            s["protocol_number"] == completed_study.protocol_number for s in results
        )


class TestDoctorPermissions(BaseTestCase):
    """Test cases for doctor role permissions."""

    def test_doctor_can_only_see_patients(self):
        """Test that doctors can only see patients in user list."""
        client, doctor = self.authenticate_as_admin()
        doctor.role = "doctor"
        doctor.save()

        # Create users with different roles
        patient = self.create_patient()
        admin = self.create_admin(email="admin@test.com")
        lab_staff = self.create_lab_staff(email="staff@test.com")

        # Doctor should only see patients
        response = client.get("/api/v1/users/")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        # Should see patients but not admin or lab staff
        emails = [u["email"] for u in results]
        assert patient.email in emails
        # Doctor will see themselves if they're in the list
        # But should not see admin or lab_staff
        assert admin.email not in emails
        assert lab_staff.email not in emails

    def test_doctor_can_only_see_own_ordered_studies(self):
        """Test that doctors can only see studies they ordered."""
        client, doctor = self.authenticate_as_admin()
        doctor.role = "doctor"
        doctor.save()

        # Create another doctor
        other_doctor = self.create_doctor(email="other.doctor@test.com")

        # Create studies ordered by different doctors
        my_study = self.create_study(ordered_by=doctor)
        other_study = self.create_study(ordered_by=other_doctor)

        # Doctor should only see their own studies
        response = client.get("/api/v1/studies/")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        protocol_numbers = [s["protocol_number"] for s in results]
        assert my_study.protocol_number in protocol_numbers
        assert other_study.protocol_number not in protocol_numbers


class TestAvailableForUploadEndpoint(BaseTestCase):
    """Test cases for the available-for-upload endpoint."""

    def test_available_for_upload_returns_pending_studies(self):
        """Test that endpoint returns studies without results."""
        client, admin = self.authenticate_as_admin()

        # Create studies with and without results
        pending_study = self.create_study(status="pending")
        in_progress_study = self.create_study(status="in_progress")
        completed_study = self.create_study(
            status="completed", results_file="results.pdf"
        )

        # Get available studies
        response = client.get("/api/v1/studies/available-for-upload/")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        protocol_numbers = [s["protocol_number"] for s in results]

        # Should include pending and in_progress
        assert pending_study.protocol_number in protocol_numbers
        assert in_progress_study.protocol_number in protocol_numbers

        # Should not include completed with results
        assert completed_study.protocol_number not in protocol_numbers

    def test_available_for_upload_requires_admin_or_lab_staff(self):
        """Test that only admin and lab staff can access endpoint."""
        # Try as patient (should fail)
        client, patient = self.authenticate_as_patient()
        response = client.get("/api/v1/studies/available-for-upload/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Try as doctor (should fail)
        client, doctor = self.authenticate_as_admin()
        doctor.role = "doctor"
        doctor.save()
        response = client.get("/api/v1/studies/available-for-upload/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Try as admin (should succeed)
        client, admin = self.authenticate_as_admin()
        response = client.get("/api/v1/studies/available-for-upload/")
        assert response.status_code == status.HTTP_200_OK

        # Try as lab staff (should succeed)
        client, lab_staff = self.authenticate_as_lab_staff()
        response = client.get("/api/v1/studies/available-for-upload/")
        assert response.status_code == status.HTTP_200_OK

    def test_available_for_upload_search_filter(self):
        """Test search filter on available-for-upload endpoint."""
        client, admin = self.authenticate_as_admin()

        # Create pending studies
        patient1 = self.create_patient(first_name="Alice")
        patient2 = self.create_patient(first_name="Bob")
        study1 = self.create_study(patient=patient1, status="pending")
        study2 = self.create_study(patient=patient2, status="pending")

        # Search by patient name
        response = client.get("/api/v1/studies/available-for-upload/?search=Alice")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        protocol_numbers = [s["protocol_number"] for s in results]
        assert study1.protocol_number in protocol_numbers
        assert study2.protocol_number not in protocol_numbers


class TestPermissionsClassUpdate(BaseTestCase):
    """Test cases for updated permissions classes."""

    def test_is_admin_or_lab_staff_permission(self):
        """Test IsAdminOrLabManager permission with lab_staff role."""
        # Admin should have access
        client, admin = self.authenticate_as_admin()
        response = client.get("/api/v1/studies/available-for-upload/")
        assert response.status_code == status.HTTP_200_OK

        # Lab staff should have access
        client, lab_staff = self.authenticate_as_lab_staff()
        response = client.get("/api/v1/studies/available-for-upload/")
        assert response.status_code == status.HTTP_200_OK

        # Doctor should NOT have access
        client, doctor = self.authenticate_as_admin()
        doctor.role = "doctor"
        doctor.save()
        response = client.get("/api/v1/studies/available-for-upload/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Patient should NOT have access
        client, patient = self.authenticate_as_patient()
        response = client.get("/api/v1/studies/available-for-upload/")
        assert response.status_code == status.HTTP_403_FORBIDDEN
