"""Tests for MVP features."""

from unittest.mock import patch

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status

from apps.notifications.models import Notification
from apps.notifications.tasks import send_result_notification_email
from apps.studies.models import Study
from tests.base import BaseTestCase


class EmailNotificationTests(BaseTestCase):
    """Tests for email notification system (US4, US9)."""

    def setUp(self):
        """Set up test data."""
        super().setUp()
        self.patient = self.create_patient(lab_client_id=1)
        self.lab_staff = self.create_lab_staff(lab_client_id=1)
        self.study_type = self.create_study_type(name="Blood Test")
        self.study = self.create_study(
            patient=self.patient,
            study_type=self.study_type,
            lab_client_id=1,
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_email_sent_on_result_upload(self):
        """Test that email is sent when results are uploaded."""
        # Authenticate as lab staff
        client = self.authenticate(self.lab_staff)

        # Create a test PDF file
        pdf_content = b"%PDF-1.4 test content"
        pdf_file = SimpleUploadedFile(
            "results.pdf", pdf_content, content_type="application/pdf"
        )

        # Upload result
        response = client.post(
            f"/api/v1/studies/{self.study.pk}/upload_result/",
            {"results_file": pdf_file, "results": "All normal"},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check that email was sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]

        # Verify email content
        self.assertIn("Blood Test", email.subject)
        self.assertIn("Results Are Ready", email.subject)
        self.assertEqual(email.to, [self.patient.email])
        self.assertIn("Blood Test", email.body)

        # Verify in-app notification was also created
        notification_exists = Notification.objects.filter(
            user=self.patient, notification_type="result_ready"
        ).exists()
        self.assertTrue(notification_exists)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_send_result_notification_email_task(self):
        """Test the Celery task for sending result notification emails."""
        # Call the task directly (synchronous in tests)
        result = send_result_notification_email(
            user_id=self.patient.pk,
            study_id=self.study.pk,
            study_type_name=self.study_type.name,
        )

        # Check that email was sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]

        # Verify email content
        self.assertIn("Blood Test", email.subject)
        self.assertEqual(email.to, [self.patient.email])

        # Verify result message
        self.assertIn("sent to", result)

    def test_email_notification_retries_on_failure(self):
        """Test that email task retries on failure."""
        with patch("apps.notifications.tasks.EmailMultiAlternatives") as mock_email:
            # Mock email send to raise exception
            mock_email.return_value.send.side_effect = Exception("SMTP error")

            # Call task and expect it to raise retry exception
            with self.assertRaises(Exception):
                send_result_notification_email(
                    user_id=self.patient.pk,
                    study_id=self.study.pk,
                    study_type_name=self.study_type.name,
                )


class PatientSearchTests(BaseTestCase):
    """Tests for patient search endpoint (US7)."""

    def setUp(self):
        """Set up test data."""
        super().setUp()
        self.admin = self.create_admin()
        self.lab_manager = self.create_lab_manager(lab_client_id=1)
        self.lab_staff = self.create_lab_staff(lab_client_id=1)
        self.patient1 = self.create_patient(
            email="john.doe@example.com",
            first_name="John",
            last_name="Doe",
            lab_client_id=1,
        )
        self.patient2 = self.create_patient(
            email="jane.smith@example.com",
            first_name="Jane",
            last_name="Smith",
            lab_client_id=1,
        )
        self.patient3 = self.create_patient(
            email="bob.jones@example.com",
            first_name="Bob",
            last_name="Jones",
            lab_client_id=2,  # Different lab
        )

    def test_admin_can_search_patients(self):
        """Test that admins can search for patients."""
        client = self.authenticate(self.admin)

        response = client.get("/api/v1/users/search-patients/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should see all patients (3 total) - paginated response
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 3)

    def test_lab_manager_can_search_patients(self):
        """Test that lab managers can search patients."""
        client = self.authenticate(self.lab_manager)

        response = client.get("/api/v1/users/search-patients/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should see only patients in their lab (2 patients)
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 2)

    def test_lab_staff_cannot_search_patients(self):
        """Test that lab staff cannot search patients."""
        client = self.authenticate(self.lab_staff)

        response = client.get("/api/v1/users/search-patients/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_patient_cannot_search_patients(self):
        """Test that patients cannot search other patients."""
        client = self.authenticate(self.patient1)

        response = client.get("/api/v1/users/search-patients/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_search_by_name(self):
        """Test searching patients by name."""
        client = self.authenticate(self.admin)

        response = client.get("/api/v1/users/search-patients/?search=john")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["email"], "john.doe@example.com")

    def test_search_by_email(self):
        """Test searching patients by email."""
        client = self.authenticate(self.admin)

        response = client.get(
            "/api/v1/users/search-patients/?email=jane.smith@example.com"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["email"], "jane.smith@example.com")

    def test_lab_manager_cannot_see_other_lab_patients(self):
        """Test that lab managers cannot see patients from other labs."""
        client = self.authenticate(self.lab_manager)

        # Lab manager is in lab_client_id=1, should not see patient3 (lab_client_id=2)
        response = client.get("/api/v1/users/search-patients/?search=bob")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 0)


class AdminResultsManagementTests(BaseTestCase):
    """Tests for admin results management endpoints (US10)."""

    def setUp(self):
        """Set up test data."""
        super().setUp()
        self.admin = self.create_admin(lab_client_id=1)
        self.lab_manager = self.create_lab_manager(lab_client_id=1)
        self.lab_staff = self.create_lab_staff(lab_client_id=1)
        self.patient = self.create_patient(lab_client_id=1)
        self.study_type = self.create_study_type(name="X-Ray")
        self.study = self.create_study(
            patient=self.patient,
            study_type=self.study_type,
            lab_client_id=1,
        )

        # Upload initial result
        pdf_content = b"%PDF-1.4 test content"
        self.pdf_file = SimpleUploadedFile(
            "results.pdf", pdf_content, content_type="application/pdf"
        )

    def test_admin_can_replace_results(self):
        """Test that admins can replace existing results."""
        # First upload
        client = self.authenticate(self.admin)
        response = client.post(
            f"/api/v1/studies/{self.study.pk}/upload_result/",
            {"results_file": self.pdf_file, "results": "First upload"},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Second upload (replace)
        pdf_content2 = b"%PDF-1.4 updated content"
        pdf_file2 = SimpleUploadedFile(
            "results_v2.pdf", pdf_content2, content_type="application/pdf"
        )
        response = client.post(
            f"/api/v1/studies/{self.study.pk}/upload_result/",
            {"results_file": pdf_file2, "results": "Second upload"},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify result was replaced
        self.study.refresh_from_db()
        self.assertIn("results_v2.pdf", self.study.results_file.name)

    def test_lab_staff_cannot_replace_results(self):
        """Test that regular lab staff cannot replace results."""
        # First upload by admin
        admin_client = self.authenticate(self.admin)
        admin_client.post(
            f"/api/v1/studies/{self.study.pk}/upload_result/",
            {"results_file": self.pdf_file, "results": "First upload"},
            format="multipart",
        )

        # Try to replace as lab staff
        staff_client = self.authenticate(self.lab_staff)
        pdf_content2 = b"%PDF-1.4 updated content"
        pdf_file2 = SimpleUploadedFile(
            "results_v2.pdf", pdf_content2, content_type="application/pdf"
        )
        response = staff_client.post(
            f"/api/v1/studies/{self.study.pk}/upload_result/",
            {"results_file": pdf_file2, "results": "Second upload"},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_delete_results(self):
        """Test that admins can delete results."""
        # Upload result
        client = self.authenticate(self.admin)
        client.post(
            f"/api/v1/studies/{self.study.pk}/upload_result/",
            {"results_file": self.pdf_file, "results": "Test upload"},
            format="multipart",
        )

        # Verify result exists
        self.study.refresh_from_db()
        self.assertIsNotNone(self.study.results_file)

        # Delete result
        response = client.delete(f"/api/v1/studies/{self.study.pk}/delete-result/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify result was deleted
        self.study.refresh_from_db()
        self.assertFalse(self.study.results_file)
        self.assertEqual(self.study.status, "in_progress")

    def test_lab_staff_cannot_delete_results(self):
        """Test that lab staff cannot delete results."""
        # Upload result as admin
        admin_client = self.authenticate(self.admin)
        admin_client.post(
            f"/api/v1/studies/{self.study.pk}/upload_result/",
            {"results_file": self.pdf_file, "results": "Test upload"},
            format="multipart",
        )

        # Try to delete as lab staff
        staff_client = self.authenticate(self.lab_staff)
        response = staff_client.delete(
            f"/api/v1/studies/{self.study.pk}/delete-result/"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_list_studies_with_results(self):
        """Test that admins can list all studies with uploaded results."""
        # Upload result for study
        client = self.authenticate(self.admin)

        # Create a fresh PDF file for this test (SimpleUploadedFile can only be used once)
        pdf_content = b"%PDF-1.4 test content"
        pdf_file = SimpleUploadedFile(
            "results.pdf", pdf_content, content_type="application/pdf"
        )

        client.post(
            f"/api/v1/studies/{self.study.pk}/upload_result/",
            {"results_file": pdf_file, "results": "Test upload"},
            format="multipart",
        )

        # Create another study without results (for testing filtering)
        _study_without_results = self.create_study(  # noqa: F841
            patient=self.patient,
            study_type=self.study_type,
            lab_client_id=1,
        )

        # List studies with results
        response = client.get("/api/v1/studies/with-results/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Should only see study with results
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(str(results[0]["id"]), str(self.study.pk))

    def test_patient_cannot_access_admin_endpoints(self):
        """Test that patients cannot access admin result management endpoints."""
        client = self.authenticate(self.patient)

        # Try to delete result
        response = client.delete(f"/api/v1/studies/{self.study.pk}/delete-result/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Try to list studies with results
        response = client.get("/api/v1/studies/with-results/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class NotificationManagementTests(BaseTestCase):
    """Tests for notification management (US5)."""

    def setUp(self):
        """Set up test data."""
        super().setUp()
        self.patient = self.create_patient()
        self.notification1 = self.create_notification(
            user=self.patient, title="Test 1", message="Message 1", status="sent"
        )
        self.notification2 = self.create_notification(
            user=self.patient, title="Test 2", message="Message 2", status="sent"
        )

    def test_patient_can_list_notifications(self):
        """Test that patients can list their notifications."""
        client = self.authenticate(self.patient)

        response = client.get("/api/v1/notifications/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 2)

    def test_patient_can_mark_notification_as_read(self):
        """Test that patients can mark notifications as read."""
        client = self.authenticate(self.patient)

        response = client.post(
            f"/api/v1/notifications/{self.notification1.pk}/mark_as_read/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify notification was marked as read
        self.notification1.refresh_from_db()
        self.assertEqual(self.notification1.status, "read")
        self.assertIsNotNone(self.notification1.read_at)

    def test_patient_can_mark_all_as_read(self):
        """Test that patients can mark all notifications as read."""
        client = self.authenticate(self.patient)

        response = client.post("/api/v1/notifications/mark_all_as_read/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify all notifications were marked as read
        self.notification1.refresh_from_db()
        self.notification2.refresh_from_db()
        self.assertEqual(self.notification1.status, "read")
        self.assertEqual(self.notification2.status, "read")

    def test_patient_can_get_unread_count(self):
        """Test that patients can get unread notification count."""
        client = self.authenticate(self.patient)

        response = client.get("/api/v1/notifications/unread_count/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["unread_count"], 2)

    def test_patient_cannot_see_other_patients_notifications(self):
        """Test that patients cannot see other patients' notifications."""
        other_patient = self.create_patient(email="other@example.com")
        _other_notification = self.create_notification(  # noqa: F841
            user=other_patient, title="Other", message="Other message"
        )

        client = self.authenticate(self.patient)

        response = client.get("/api/v1/notifications/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should only see own notifications (2), not the other patient's
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 2)
