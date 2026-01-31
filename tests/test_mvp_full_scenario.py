"""
Full MVP Scenario Test - Complete End-to-End Workflow.

This test validates ALL 11 MVP user stories (US1-US11) in a single comprehensive scenario.
It simulates real-world usage of the patient results portal from both patient and admin perspectives.
"""

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status

from apps.notifications.models import Notification
from apps.studies.models import Study
from tests.base import BaseTestCase


class MVPFullScenarioTest(BaseTestCase):
    """
    Complete end-to-end MVP scenario test covering all user stories.

    This test simulates a real-world workflow:
    1. Admin searches for and selects a patient (US6, US7)
    2. Patient registers and logs in (US1)
    3. Patient views their (initially empty) results list (US2)
    4. Admin uploads a result for the patient (US8, US9)
    5. Patient receives notifications (US4, US9)
    6. Patient views updated results list (US2)
    7. Patient downloads the PDF result (US3)
    8. Patient manages notifications (US5)
    9. Admin manages uploaded results (US10)
    10. Security boundaries are enforced (US11)
    """

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_mvp_full_scenario(self):
        """Test complete MVP workflow covering all 11 user stories."""

        # ===================================================================
        # SETUP: Create lab infrastructure
        # ===================================================================
        lab_client_id = 1
        study_type = self.create_study_type(
            name="Complete Blood Count",
            code="CBC",
            category="Hematology",
        )

        # ===================================================================
        # US6: Admin Login
        # ===================================================================
        print("\n[US6] Admin logs in securely...")
        admin = self.create_admin()
        admin_client = self.authenticate(admin)

        # Verify admin can access admin endpoints
        response = admin_client.get("/api/v1/users/")
        assert response.status_code == status.HTTP_200_OK
        print("✓ Admin authenticated successfully")

        # ===================================================================
        # US1: Patient Account Creation and Access
        # ===================================================================
        print("\n[US1] Patient registers and logs in...")
        registration_data = {
            "email": "patient@mvptest.com",
            "password": "SecurePass123!",
            "password_confirm": "SecurePass123!",
            "first_name": "María",
            "last_name": "González",
            "phone_number": "+525512345678",
            "lab_client_id": lab_client_id,
        }

        # Patient registers (public endpoint)
        response = self.client.post(
            "/api/v1/users/register/", registration_data, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["user"]["role"] == "patient"
        assert response.data["user"]["email"] == "patient@mvptest.com"
        patient_id = response.data["user"]["id"]
        print(f"✓ Patient registered successfully (ID: {patient_id})")

        # Patient logs in
        patient_client, patient = self.authenticate_user_by_email("patient@mvptest.com")
        print("✓ Patient logged in successfully")

        # ===================================================================
        # US7: Admin Searches for Patient
        # ===================================================================
        print("\n[US7] Admin searches for patient to assign results...")

        # Search by name
        response = admin_client.get("/api/v1/users/search-patients/?search=María")
        assert response.status_code == status.HTTP_200_OK
        results = response.data.get("results", response.data)
        assert len(results) >= 1
        found_patient = next(
            (p for p in results if p["email"] == "patient@mvptest.com"), None
        )
        assert found_patient is not None
        print(
            f"✓ Admin found patient by name: {found_patient['first_name']} {found_patient['last_name']}"
        )

        # Search by email
        response = admin_client.get(
            "/api/v1/users/search-patients/?email=patient@mvptest.com"
        )
        assert response.status_code == status.HTTP_200_OK
        results = response.data.get("results", response.data)
        assert len(results) == 1
        print("✓ Admin found patient by email")

        # Verify lab staff CANNOT search patients
        lab_staff = self.create_lab_staff(lab_client_id=lab_client_id)
        staff_client = self.authenticate(lab_staff)
        response = staff_client.get("/api/v1/users/search-patients/")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        print("✓ Lab staff correctly denied access to patient search")

        # ===================================================================
        # US2: Patient Views Empty Results List
        # ===================================================================
        print("\n[US2] Patient views their (initially empty) results list...")
        response = patient_client.get("/api/v1/studies/")
        assert response.status_code == status.HTTP_200_OK
        results = response.data.get("results", response.data)
        initial_count = len(results)
        print(f"✓ Patient sees {initial_count} results (initially)")

        # ===================================================================
        # US8: Admin Uploads Patient Result PDF
        # ===================================================================
        print("\n[US8] Admin uploads lab result for patient...")

        # Create a study for the patient
        study = self.create_study(
            patient=patient,
            study_type=study_type,
            status="in_progress",
            lab_client_id=lab_client_id,
        )
        print(f"✓ Study created: {study.order_number}")

        # Prepare PDF result file
        pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        pdf_file = SimpleUploadedFile(
            "complete_blood_count_results.pdf",
            pdf_content,
            content_type="application/pdf",
        )

        upload_data = {
            "results_file": pdf_file,
            "results": "Complete Blood Count - All values within normal range. Hemoglobin: 14.2 g/dL",
        }

        # Clear mail outbox before upload
        mail.outbox = []

        # Admin uploads results
        response = admin_client.post(
            f"/api/v1/studies/{study.pk}/upload_result/",
            upload_data,
            format="multipart",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["message"] == "Results uploaded successfully."
        print("✓ Admin uploaded results successfully")

        # Verify study status updated
        study.refresh_from_db()
        assert study.status == "completed"
        assert study.results_file is not None
        assert study.completed_at is not None
        print(f"✓ Study status updated to: {study.status}")

        # ===================================================================
        # US4 & US9: Patient Receives Notifications
        # ===================================================================
        print("\n[US4, US9] Verify patient received notifications...")

        # Check in-app notification was created
        in_app_notifications = Notification.objects.filter(
            user=patient, notification_type="result_ready", channel="in_app"
        )
        assert in_app_notifications.count() >= 1
        notification = in_app_notifications.first()
        assert "Complete Blood Count" in notification.message
        assert notification.status == "sent"
        print(f"✓ In-app notification created: '{notification.title}'")

        # Check email notification was sent
        assert len(mail.outbox) >= 1
        email = mail.outbox[-1]  # Get most recent email
        assert "patient@mvptest.com" in email.to
        assert "Complete Blood Count" in email.subject
        assert "Results Are Ready" in email.subject
        assert "Complete Blood Count" in email.body
        print(f"✓ Email notification sent to: {email.to[0]}")
        print(f"  Subject: {email.subject}")

        # ===================================================================
        # US2: Patient Views Updated Results List
        # ===================================================================
        print("\n[US2] Patient views updated results list...")
        response = patient_client.get("/api/v1/studies/")
        assert response.status_code == status.HTTP_200_OK
        results = response.data.get("results", response.data)
        assert len(results) == initial_count + 1

        # Find the newly added study
        # Debug: print all IDs in results
        result_ids = [r["id"] for r in results]
        new_result = next((r for r in results if str(r["id"]) == str(study.pk)), None)
        assert (
            new_result is not None
        ), f"Study {str(study.pk)} not found in results list. Available IDs: {result_ids}"
        assert new_result["status"] == "completed"
        assert new_result["results_file"] is not None
        assert new_result["study_type_detail"]["name"] == "Complete Blood Count"
        print(f"✓ Patient sees {len(results)} results (new result visible)")
        print(
            f"  New result: {new_result['study_type_detail']['name']} - {new_result['status']}"
        )

        # ===================================================================
        # US3: Patient Downloads Result PDF
        # ===================================================================
        print("\n[US3] Patient downloads result PDF...")
        response = patient_client.get(f"/api/v1/studies/{study.pk}/download_result/")
        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "application/pdf"
        assert "attachment" in response["Content-Disposition"]
        assert f"results_{study.order_number}.pdf" in response["Content-Disposition"]
        print(f"✓ Patient downloaded PDF: {response['Content-Disposition']}")

        # ===================================================================
        # US5: Patient Manages Notifications
        # ===================================================================
        print("\n[US5] Patient manages notifications...")

        # Get unread count
        response = patient_client.get("/api/v1/notifications/unread_count/")
        assert response.status_code == status.HTTP_200_OK
        unread_count = response.data["unread_count"]
        assert unread_count >= 1
        print(f"✓ Unread notifications: {unread_count}")

        # List all notifications
        response = patient_client.get("/api/v1/notifications/")
        assert response.status_code == status.HTTP_200_OK
        notifications_list = response.data.get("results", response.data)
        assert len(notifications_list) >= 1
        print(f"✓ Patient sees {len(notifications_list)} total notifications")

        # Mark specific notification as read
        notification_id = notifications_list[0]["id"]
        response = patient_client.post(
            f"/api/v1/notifications/{notification_id}/mark_as_read/"
        )
        assert response.status_code == status.HTTP_200_OK
        print(f"✓ Marked notification {notification_id} as read")

        # Verify unread count decreased
        response = patient_client.get("/api/v1/notifications/unread_count/")
        new_unread_count = response.data["unread_count"]
        assert new_unread_count == unread_count - 1
        print(f"✓ Unread count decreased: {unread_count} → {new_unread_count}")

        # Mark all as read
        response = patient_client.post("/api/v1/notifications/mark_all_as_read/")
        assert response.status_code == status.HTTP_200_OK
        print("✓ Marked all notifications as read")

        # Verify unread count is now 0
        response = patient_client.get("/api/v1/notifications/unread_count/")
        assert response.data["unread_count"] == 0
        print("✓ Unread count is now 0")

        # ===================================================================
        # US10: Admin Manages Uploaded Results
        # ===================================================================
        print("\n[US10] Admin manages uploaded results...")

        # List all studies with results
        response = admin_client.get("/api/v1/studies/with-results/")
        assert response.status_code == status.HTTP_200_OK
        results = response.data.get("results", response.data)
        assert len(results) >= 1
        has_our_study = any(str(r["id"]) == str(study.pk) for r in results)
        assert has_our_study
        print(f"✓ Admin sees {len(results)} studies with results")

        # Admin replaces result (re-upload)
        new_pdf_content = b"%PDF-1.4\nUpdated results content\n"
        new_pdf_file = SimpleUploadedFile(
            "complete_blood_count_results_v2.pdf",
            new_pdf_content,
            content_type="application/pdf",
        )

        response = admin_client.post(
            f"/api/v1/studies/{study.pk}/upload_result/",
            {"results_file": new_pdf_file, "results": "Updated results"},
            format="multipart",
        )
        assert response.status_code == status.HTTP_200_OK
        print("✓ Admin replaced result successfully")

        # Verify lab staff CANNOT replace results
        response = staff_client.post(
            f"/api/v1/studies/{study.pk}/upload_result/",
            {"results_file": new_pdf_file, "results": "Unauthorized update"},
            format="multipart",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        print("✓ Lab staff correctly denied result replacement")

        # Admin deletes result
        response = admin_client.delete(f"/api/v1/studies/{study.pk}/delete-result/")
        assert response.status_code == status.HTTP_200_OK
        print("✓ Admin deleted result successfully")

        # Verify study status reset
        study.refresh_from_db()
        assert study.status == "in_progress"
        assert not study.results_file
        print(f"✓ Study status reset to: {study.status}")

        # Verify lab staff CANNOT delete results
        # Re-upload first (need to create new PDF file as the old one was consumed)
        reupload_pdf_file = SimpleUploadedFile(
            "reupload_results.pdf",
            b"%PDF-1.4\nReupload content\n",
            content_type="application/pdf",
        )
        response = admin_client.post(
            f"/api/v1/studies/{study.pk}/upload_result/",
            {"results_file": reupload_pdf_file, "results": "Test"},
            format="multipart",
        )
        assert response.status_code == status.HTTP_200_OK

        response = staff_client.delete(f"/api/v1/studies/{study.pk}/delete-result/")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        print("✓ Lab staff correctly denied result deletion")

        # ===================================================================
        # US11: Enforce Security & Permissions
        # ===================================================================
        print("\n[US11] Verify security boundaries are enforced...")

        # Create another patient with different lab
        other_patient = self.create_patient(
            email="other@mvptest.com", lab_client_id=2  # Different lab
        )
        other_study = self.create_study(
            patient=other_patient,
            study_type=study_type,
            status="completed",
            lab_client_id=2,
        )

        # Original patient tries to view other patient's results
        response = patient_client.get("/api/v1/studies/")
        assert response.status_code == status.HTTP_200_OK
        results = response.data.get("results", response.data)

        # Should not see other patient's study
        has_other_study = any(r["id"] == str(other_study.pk) for r in results)
        assert not has_other_study
        print("✓ Patient CANNOT see other patients' results in list")

        # Original patient tries to download other patient's result
        response = patient_client.get(
            f"/api/v1/studies/{other_study.pk}/download_result/"
        )
        # Should get 404 because queryset filters it out
        assert response.status_code == status.HTTP_404_NOT_FOUND
        print("✓ Patient CANNOT download other patients' results")

        # Patient tries to access admin endpoints
        response = patient_client.get("/api/v1/users/search-patients/")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        print("✓ Patient CANNOT access admin patient search")

        response = patient_client.get("/api/v1/studies/with-results/")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        print("✓ Patient CANNOT access admin results list")

        # Patient tries to delete results
        response = patient_client.delete(f"/api/v1/studies/{study.pk}/delete-result/")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        print("✓ Patient CANNOT delete results")

        # Verify multi-tenant isolation (lab manager sees only their lab)
        lab_manager = self.create_lab_manager(lab_client_id=1)
        manager_client = self.authenticate(lab_manager)

        response = manager_client.get("/api/v1/users/search-patients/?search=other")
        assert response.status_code == status.HTTP_200_OK
        results = response.data.get("results", response.data)
        # Should not see patient from lab_client_id=2
        has_other_patient = any(r["email"] == "other@mvptest.com" for r in results)
        assert not has_other_patient
        print("✓ Lab manager CANNOT see patients from other labs")

        # ===================================================================
        # SUMMARY
        # ===================================================================
        print("\n" + "=" * 70)
        print("MVP FULL SCENARIO TEST COMPLETE - ALL USER STORIES VALIDATED ✓")
        print("=" * 70)
        print(
            """
Summary:
- US1  ✓ Patient registration and login
- US2  ✓ View list of results
- US3  ✓ Download result PDF
- US4  ✓ Receive notification when results ready
- US5  ✓ Manage notifications
- US6  ✓ Admin login
- US7  ✓ Search/select patient (admin only)
- US8  ✓ Upload patient result PDF
- US9  ✓ Trigger patient notification automatically
- US10 ✓ Manage uploaded results (replace, delete, list)
- US11 ✓ Security boundaries enforced

Total Assertions: ~60+
Total User Stories Covered: 11/11 (100%)
Multi-tenant Security: ✓ Verified
RBAC Permissions: ✓ Verified
Email Notifications: ✓ Verified
"""
        )

        print("All MVP features working as expected! 🎉")

    def test_mvp_workflow_edge_cases(self):
        """Test edge cases and error scenarios in MVP workflow."""

        print("\n[EDGE CASES] Testing MVP workflow edge cases...")

        # Test duplicate email registration
        registration_data = {
            "email": "duplicate@test.com",
            "password": "Pass123!",
            "password_confirm": "Pass123!",
            "first_name": "Test",
            "last_name": "User",
            "lab_client_id": 1,
        }

        response = self.client.post(
            "/api/v1/users/register/", registration_data, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED

        # Try to register again with same email
        response = self.client.post(
            "/api/v1/users/register/", registration_data, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        print("✓ Duplicate email registration correctly rejected")

        # Test password mismatch
        registration_data["email"] = "newuser@test.com"
        registration_data["password_confirm"] = "DifferentPass!"
        response = self.client.post(
            "/api/v1/users/register/", registration_data, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        print("✓ Password mismatch correctly rejected")

        # Test downloading non-existent result
        patient_client, patient = self.authenticate_as_patient()
        study = self.create_study(patient=patient, status="in_progress")

        response = patient_client.get(f"/api/v1/studies/{study.pk}/download_result/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        print("✓ Downloading non-existent result correctly returns 404")

        # Test uploading invalid file type
        lab_staff = self.create_lab_staff(lab_client_id=1)
        staff_client = self.authenticate(lab_staff)

        invalid_file = SimpleUploadedFile(
            "test.exe", b"Invalid content", content_type="application/x-executable"
        )

        response = staff_client.post(
            f"/api/v1/studies/{study.pk}/upload_result/",
            {"results_file": invalid_file},
            format="multipart",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        print("✓ Invalid file type correctly rejected")

        print("\n✓ All edge cases handled correctly!")
