"""Tests for complete patient workflow: Registration -> Appointment -> Results."""

from datetime import date
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status

from apps.notifications.models import Notification
from tests.base import BaseTestCase


class TestPatientWorkflow(BaseTestCase):
    """Test the complete patient workflow end-to-end."""

    def test_complete_patient_workflow(self):
        """
        Test complete workflow:
        1. Patient registers
        2. Patient schedules appointment
        3. Lab uploads results
        4. Patient views/downloads results
        5. Notifications are sent
        """
        # ======================================================================
        # STEP 1: Patient Registration
        # ======================================================================
        registration_data = {
            "email": "newpatient@test.com",
            "password": "securepassword123",
            "password_confirm": "securepassword123",
            "first_name": "John",
            "last_name": "Doe",
            "phone_number": "+1234567890",
            "lab_client_id": 1,
        }

        # Register patient (public endpoint, no authentication required)
        response = self.client.post(
            "/api/v1/users/register/", registration_data, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert "user" in response.data
        assert response.data["user"]["email"] == "newpatient@test.com"
        assert response.data["user"]["role"] == "patient"

        patient_id = response.data["user"]["id"]

        # ======================================================================
        # STEP 2: Patient Login and Schedule Appointment
        # ======================================================================
        # Create a study type first (before authentication)
        study_type = self.create_study_type(name="Blood Test", code="BT001")

        # Authenticate as the newly registered patient
        client, patient = self.authenticate_user_by_email("newpatient@test.com")

        # Get available study types
        response = client.get("/api/v1/studies/types/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) >= 1

        # Schedule an appointment
        tomorrow = date.today() + timedelta(days=1)
        appointment_data = {
            "scheduled_date": tomorrow.isoformat(),
            "scheduled_time": "10:00:00",
            "duration_minutes": 30,
            "reason": "Blood test for routine checkup",
            "notes": "Fasting since last night",
        }

        response = client.post("/api/v1/appointments/", appointment_data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert str(response.data["patient"]) == str(patient_id)
        assert response.data["status"] == "scheduled"
        _appointment_id = response.data["id"]  # noqa: F841

        # Verify appointment confirmation notification was created
        notifications = Notification.objects.filter(
            user=patient, notification_type="appointment_reminder"
        )
        assert notifications.count() == 1
        assert "confirmed" in notifications.first().message.lower()

        # ======================================================================
        # STEP 3: Lab Staff Processes Sample and Uploads Results
        # ======================================================================
        # Create lab staff user
        lab_staff = self.create_lab_staff(
            email="staff@lab.com", lab_client_id=patient.lab_client_id
        )
        staff_client = self.authenticate(lab_staff)

        # Create a study for the patient
        study = self.create_study(
            patient=patient,
            study_type=study_type,
            status="in_progress",
            lab_client_id=patient.lab_client_id,
        )

        # Lab staff uploads results
        # Create a fake PDF file
        pdf_content = b"%PDF-1.4 fake pdf content"
        results_file = SimpleUploadedFile(
            "test_results.pdf",
            pdf_content,
            content_type="application/pdf",
        )

        upload_data = {
            "results_file": results_file,
            "results": "All values within normal range.",
        }

        response = staff_client.post(
            f"/api/v1/studies/{study.pk}/upload_result/",
            upload_data,
            format="multipart",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["message"] == "Results uploaded successfully."

        # Verify study status was updated
        study.refresh_from_db()
        assert study.status == "completed"
        assert study.results_file is not None
        assert study.completed_at is not None

        # Verify result ready notification was created
        result_notifications = Notification.objects.filter(
            user=patient, notification_type="result_ready"
        )
        assert result_notifications.count() == 1
        assert (
            "results are now available" in result_notifications.first().message.lower()
        )

        # ======================================================================
        # STEP 4: Patient Views and Downloads Results
        # ======================================================================
        # Patient views their studies
        response = client.get("/api/v1/studies/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["status"] == "completed"
        assert response.data["results"][0]["results_file"] is not None

        # Patient downloads results
        response = client.get(f"/api/v1/studies/{study.pk}/download_result/")
        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "application/pdf"
        assert "attachment" in response["Content-Disposition"]

        # ======================================================================
        # STEP 5: Verify Patient Cannot Access Other Patients' Results
        # ======================================================================
        # Create another patient with a study
        other_patient = self.create_patient(email="other@test.com")
        other_study = self.create_study(
            patient=other_patient,
            study_type=study_type,
            status="completed",
        )

        # Original patient tries to download other patient's results
        response = client.get(f"/api/v1/studies/{other_study.pk}/download_result/")
        # Should get 404 because the queryset filters out studies not belonging to the patient
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_patient_cannot_upload_results(self):
        """Test that patients cannot upload results (only lab staff can)."""
        client, patient = self.authenticate_as_patient()
        study = self.create_study(patient=patient, status="in_progress")

        pdf_content = b"%PDF-1.4 fake pdf content"
        results_file = SimpleUploadedFile(
            "test_results.pdf",
            pdf_content,
            content_type="application/pdf",
        )

        upload_data = {
            "results_file": results_file,
            "results": "Test results",
        }

        response = client.post(
            f"/api/v1/studies/{study.pk}/upload_result/",
            upload_data,
            format="multipart",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Only lab staff can upload results" in response.data["error"]

    def test_appointment_cancellation_workflow(self):
        """Test appointment cancellation sends notification."""
        client, patient = self.authenticate_as_patient()

        # Create an appointment
        appointment = self.create_appointment(patient=patient, status="scheduled")

        # Patient cancels appointment
        response = client.post(f"/api/v1/appointments/{appointment.pk}/cancel/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["appointment"]["status"] == "cancelled"

        # Verify cancellation notification
        notifications = Notification.objects.filter(
            user=patient,
            notification_type="info",
            related_appointment_id=appointment.id,
        )
        assert notifications.count() == 1
        assert "cancelled" in notifications.first().message.lower()

    def test_upcoming_appointments_endpoint(self):
        """Test that patients can view their upcoming appointments."""
        client, patient = self.authenticate_as_patient()

        # Create appointments
        future_date = date.today() + timedelta(days=7)
        past_date = date.today() - timedelta(days=7)

        upcoming_apt = self.create_appointment(
            patient=patient,
            scheduled_date=future_date,
            status="scheduled",
        )
        _past_apt = self.create_appointment(  # noqa: F841
            patient=patient,
            scheduled_date=past_date,
            status="scheduled",
        )
        _completed_apt = self.create_appointment(  # noqa: F841
            patient=patient,
            scheduled_date=future_date,
            status="completed",
        )

        # Get upcoming appointments
        response = client.get("/api/v1/appointments/upcoming/")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1  # Only the future scheduled appointment
        assert str(response.data[0]["id"]) == str(upcoming_apt.pk)

    def test_patient_registration_validation(self):
        """Test patient registration validation."""
        # Test password mismatch
        registration_data = {
            "email": "test@test.com",
            "password": "password123",
            "password_confirm": "password456",
            "first_name": "John",
            "last_name": "Doe",
            "lab_client_id": 1,
        }

        response = self.client.post(
            "/api/v1/users/register/", registration_data, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "password" in str(response.data).lower()

    def test_cannot_schedule_appointment_in_past(self):
        """Test that appointments cannot be scheduled in the past."""
        client, patient = self.authenticate_as_patient()

        past_date = date.today() - timedelta(days=1)
        appointment_data = {
            "scheduled_date": past_date.isoformat(),
            "scheduled_time": "10:00:00",
            "duration_minutes": 30,
            "reason": "Test",
        }

        response = client.post("/api/v1/appointments/", appointment_data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "past" in str(response.data).lower()

    def test_result_file_validation(self):
        """Test file upload validation for results."""
        lab_staff = self.create_lab_staff(email="staff@lab.com", lab_client_id=1)
        client = self.authenticate(lab_staff)

        patient = self.create_patient(lab_client_id=1)
        study = self.create_study(
            patient=patient,
            status="in_progress",
            lab_client_id=1,
        )

        # Test invalid file type (text file)
        invalid_file = SimpleUploadedFile(
            "test.txt",
            b"Invalid content",
            content_type="text/plain",
        )

        upload_data = {
            "results_file": invalid_file,
        }

        response = client.post(
            f"/api/v1/studies/{study.pk}/upload_result/",
            upload_data,
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "PDF, JPEG, and PNG" in str(response.data)
