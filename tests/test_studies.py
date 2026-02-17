"""Tests for studies app — updated for new study creation flow."""

import datetime
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework import status

from apps.notifications.models import Notification
from apps.studies.models import Practice, Study
from tests.base import BaseTestCase

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pdf(name="results.pdf"):
    """Return a minimal valid-looking PDF SimpleUploadedFile."""
    return SimpleUploadedFile(
        name,
        b"%PDF-1.4\n1 0 obj\n<</Type/Catalog>>\nendobj\n",
        content_type="application/pdf",
    )


# ===========================================================================
# Practice model
# ===========================================================================


class TestPracticeModel(BaseTestCase):
    """Test cases for Practice model."""

    def test_create_practice(self):
        """Test creating a practice."""
        practice = self.create_practice()
        assert practice.name.startswith("Test Practice")
        assert practice.is_active is True

    def test_practice_has_uuid(self):
        """Test that practice has UUID field."""
        practice = self.create_practice()
        self.assertUUID(practice.uuid)

    def test_practice_has_timestamps(self):
        """Test that practice has timestamp fields."""
        practice = self.create_practice()
        self.assertIsNotNone(practice.created_at)
        self.assertIsNotNone(practice.updated_at)
        self.assertTimestampRecent(practice.created_at)

    def test_practice_str_representation(self):
        """Test practice string representation."""
        practice = self.create_practice(name="Blood Test")
        assert str(practice) == "Blood Test"


# ===========================================================================
# Study model
# ===========================================================================


class TestStudyModel(BaseTestCase):
    """Test cases for Study model."""

    def test_create_study(self):
        """Test creating a study."""
        study = self.create_study()
        assert study.protocol_number.startswith("PROT-2024-")
        assert study.status == "pending"
        assert study.is_pending is True
        assert study.is_completed is False

    def test_study_has_uuid(self):
        """Test that study has UUID field."""
        study = self.create_study()
        self.assertUUID(study.uuid)

    def test_study_has_timestamps(self):
        """Test that study has timestamp fields."""
        study = self.create_study()
        self.assertIsNotNone(study.created_at)
        self.assertIsNotNone(study.updated_at)
        self.assertTimestampRecent(study.created_at)

    def test_study_has_audit_trail(self):
        """Test that study has history tracking."""
        study = self.create_study()
        assert hasattr(study, "history")
        assert study.history.count() == 1  # Created

        study.status = "in_progress"
        study.save()
        assert study.history.count() == 2  # Created + Updated

    def test_study_str_representation(self):
        """Test study string representation."""
        study = self.create_study()
        expected = f"{study.protocol_number} - {study.practice.name}"
        assert str(study) == expected

    def test_study_solicited_date_field(self):
        """Test that study has solicited_date field distinct from sample_collected_at."""
        patient = self.create_patient()
        practice = self.create_practice()
        solicited = datetime.date(2026, 2, 10)
        collected = timezone.datetime(2026, 2, 12, 9, 30, tzinfo=timezone.utc)

        study = self.create_study(
            patient=patient,
            practice=practice,
            solicited_date=solicited,
            sample_collected_at=collected,
        )
        study.refresh_from_db()
        assert study.solicited_date == solicited
        assert study.sample_collected_at == collected

    def test_study_custom_manager_pending(self):
        """Test StudyManager.pending() method."""
        pending_study = self.create_study(status="pending")
        completed_study = self.create_study(
            protocol_number="PROT-2024-9999", status="completed"
        )

        pending_studies = Study.objects.pending()
        assert pending_study in pending_studies
        assert completed_study not in pending_studies

    def test_study_custom_manager_completed(self):
        """Test StudyManager.completed() method."""
        pending_study = self.create_study(status="pending")
        completed_study = self.create_study(
            protocol_number="PROT-2024-9999", status="completed"
        )

        completed_studies = Study.objects.completed()
        assert completed_study in completed_studies
        assert pending_study not in completed_studies

    def test_study_custom_manager_for_patient(self):
        """Test StudyManager.for_patient() method."""
        patient1 = self.create_patient()
        patient2 = self.create_patient()

        study1 = self.create_study(patient=patient1)
        study2 = self.create_study(patient=patient2, protocol_number="PROT-2024-9999")

        patient1_studies = Study.objects.for_patient(patient1)
        assert study1 in patient1_studies
        assert study2 not in patient1_studies

    def test_study_lab_client_isolation(self):
        """Test multi-tenant isolation."""
        lab1_patient = self.create_patient(lab_client_id=1)
        lab2_patient = self.create_patient(lab_client_id=2)

        lab1_study = self.create_study(patient=lab1_patient)
        lab2_study = self.create_study(
            patient=lab2_patient, protocol_number="PROT-2024-9999"
        )

        lab1_studies = Study.objects.for_lab(1)
        assert lab1_study in lab1_studies
        assert lab2_study not in lab1_studies


# ===========================================================================
# Practice API
# ===========================================================================


class TestPracticeAPI(BaseTestCase):
    """Tests for the practice CRUD endpoints."""

    def test_list_practices_authenticated_patient(self):
        """Any authenticated user can list practices."""
        client, _ = self.authenticate_as_patient()
        self.create_practice()

        response = client.get("/api/v1/studies/practices/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_admin_can_create_practice(self):
        """Admin/lab staff can create a practice."""
        client, _ = self.authenticate_as_lab_staff()

        data = {
            "name": "Hemograma Completo",
            "technique": "Citometría de flujo",
            "sample_type": "Sangre venosa",
            "sample_quantity": "5 mL",
            "delay_days": 1,
            "price": "500.00",
        }
        response = client.post("/api/v1/studies/practices/", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "Hemograma Completo"

    def test_patient_cannot_create_practice(self):
        """Patients cannot create practices."""
        client, _ = self.authenticate_as_patient()
        data = {"name": "Forbidden Practice", "delay_days": 0, "price": "0.00"}
        response = client.post("/api/v1/studies/practices/", data, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_update_practice(self):
        """Admin can update an existing practice."""
        client, _ = self.authenticate_as_admin(is_superuser=True)
        practice = self.create_practice(name="Old Name")

        response = client.patch(
            f"/api/v1/studies/practices/{practice.pk}/",
            {"name": "New Name"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "New Name"


# ===========================================================================
# Study list / retrieve API
# ===========================================================================


class TestStudyListAPI(BaseTestCase):
    """Test cases for Study list/retrieve endpoints."""

    def test_list_patient_studies(self):
        """Patient can see their own studies."""
        client, patient = self.authenticate_as_patient()
        study = self.create_study(patient=patient)

        response = client.get("/api/v1/studies/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["protocol_number"] == study.protocol_number

    def test_patient_cannot_see_other_patient_studies(self):
        """Patients cannot see other patients' studies."""
        client, _ = self.authenticate_as_patient()
        other_patient = self.create_patient()
        self.create_study(patient=other_patient)

        response = client.get("/api/v1/studies/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 0

    def test_lab_staff_can_see_lab_studies(self):
        """Lab staff can see all studies in their lab."""
        client, staff = self.authenticate_as_lab_staff()
        patient = self.create_patient(lab_client_id=staff.lab_client_id)
        self.create_study(patient=patient)

        response = client.get("/api/v1/studies/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) >= 1

    def test_study_serializer_includes_solicited_date(self):
        """Study API response includes solicited_date field."""
        client, patient = self.authenticate_as_patient()
        study = self.create_study(
            patient=patient,
            solicited_date=datetime.date(2026, 1, 15),
        )

        response = client.get(f"/api/v1/studies/{study.pk}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["solicited_date"] == "2026-01-15"

    def test_study_serializer_includes_patient_name(self):
        """Study response includes patient_name computed field."""
        client, staff = self.authenticate_as_lab_staff()
        patient = self.create_patient(
            lab_client_id=staff.lab_client_id,
            first_name="Ana",
            last_name="Pérez",
        )
        study = self.create_study(patient=patient)

        response = client.get(f"/api/v1/studies/{study.pk}/")
        assert response.status_code == status.HTTP_200_OK
        assert "Ana" in response.data["patient_name"]
        assert "Pérez" in response.data["patient_name"]

    def test_study_serializer_includes_practice_detail(self):
        """Study response includes practice_detail nested object."""
        client, patient = self.authenticate_as_patient()
        practice = self.create_practice(name="Hepatograma")
        study = self.create_study(patient=patient, practice=practice)

        response = client.get(f"/api/v1/studies/{study.pk}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["practice_detail"]["name"] == "Hepatograma"


# ===========================================================================
# Study creation API (new flow: create study + optional file in one request)
# ===========================================================================


class TestStudyCreateAPI(BaseTestCase):
    """
    Tests for the new study creation endpoint (POST /studies/).

    New flow:
    - Staff creates a study (with all metadata) in a single request.
    - If a results_file is included → status = 'completed', completed_at set,
      patient notification triggered.
    - If no results_file → status = 'pending'.
    - solicited_date and sample_collected_at are independent date fields.
    - protocol_number must be unique.
    """

    def setUp(self):
        super().setUp()
        self.staff_client, self.staff = self.authenticate_as_lab_staff(lab_client_id=1)
        self.patient = self.create_patient(lab_client_id=1)
        self.practice = self.create_practice(name="Hemograma")

    def _base_payload(self, **overrides):
        payload = {
            "patient": str(self.patient.pk),
            "practice": str(self.practice.pk),
            "protocol_number": "2026-001",
        }
        payload.update(overrides)
        return payload

    # ── Happy path: no file ──────────────────────────────────────────────────

    def test_create_study_without_file_sets_pending(self):
        """Creating a study without a PDF sets status=pending."""
        response = self.staff_client.post(
            "/api/v1/studies/",
            self._base_payload(),
            format="multipart",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["study"]["status"] == "pending"
        assert response.data["study"]["completed_at"] is None
        assert response.data["message"] == "Study created successfully."

    def test_create_study_without_file_no_notification(self):
        """No notification is created when study is created without a file."""
        self.staff_client.post(
            "/api/v1/studies/",
            self._base_payload(),
            format="multipart",
        )
        assert not Notification.objects.filter(
            user=self.patient, notification_type="result_ready"
        ).exists()

    # ── Happy path: with file ────────────────────────────────────────────────

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_create_study_with_file_sets_completed(self):
        """Creating a study with a PDF sets status=completed and completed_at."""
        payload = self._base_payload()
        payload["results_file"] = _make_pdf()

        response = self.staff_client.post(
            "/api/v1/studies/", payload, format="multipart"
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["study"]["status"] == "completed"
        assert response.data["study"]["completed_at"] is not None

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_create_study_with_file_triggers_notification(self):
        """An in-app notification is created when a study is created with a PDF."""
        payload = self._base_payload()
        payload["results_file"] = _make_pdf()

        self.staff_client.post("/api/v1/studies/", payload, format="multipart")

        notification = Notification.objects.filter(
            user=self.patient,
            notification_type="result_ready",
        ).first()
        assert notification is not None
        assert notification.status == "sent"
        assert "Hemograma" in notification.message

    # ── Dates ────────────────────────────────────────────────────────────────

    def test_create_study_with_solicited_date(self):
        """solicited_date is stored independently from sample_collected_at."""
        payload = self._base_payload(
            solicited_date="2026-02-10",
        )
        response = self.staff_client.post(
            "/api/v1/studies/", payload, format="multipart"
        )
        assert response.status_code == status.HTTP_201_CREATED

        study_id = response.data["study"]["id"]
        study = Study.objects.get(pk=study_id)
        assert study.solicited_date == datetime.date(2026, 2, 10)
        assert study.sample_collected_at is None

    def test_create_study_with_both_dates(self):
        """Both solicited_date and sample_collected_at can be set independently."""
        payload = self._base_payload(
            solicited_date="2026-02-10",
            sample_collected_at="2026-02-12T09:30:00",
        )
        response = self.staff_client.post(
            "/api/v1/studies/", payload, format="multipart"
        )
        assert response.status_code == status.HTTP_201_CREATED

        study_id = response.data["study"]["id"]
        study = Study.objects.get(pk=study_id)
        assert study.solicited_date == datetime.date(2026, 2, 10)
        assert study.sample_collected_at is not None

    # ── Validations ──────────────────────────────────────────────────────────

    def test_create_study_duplicate_protocol_number_rejected(self):
        """Duplicate protocol_number returns 400."""
        self.create_study(patient=self.patient, protocol_number="2026-DUP")

        payload = self._base_payload(protocol_number="2026-DUP")
        response = self.staff_client.post(
            "/api/v1/studies/", payload, format="multipart"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "protocol_number" in response.data

    def test_create_study_missing_required_fields(self):
        """Missing patient/practice/protocol_number returns 400."""
        response = self.staff_client.post(
            "/api/v1/studies/",
            {"protocol_number": "2026-X"},
            format="multipart",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_study_invalid_file_type_rejected(self):
        """Non-PDF/JPEG/PNG file is rejected with 400."""
        exe_file = SimpleUploadedFile(
            "virus.exe", b"MZ\x90\x00", content_type="application/x-executable"
        )
        payload = self._base_payload()
        payload["results_file"] = exe_file

        response = self.staff_client.post(
            "/api/v1/studies/", payload, format="multipart"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_study_oversized_file_rejected(self):
        """File larger than 10 MB is rejected."""
        big_content = b"%PDF-1.4\n" + b"X" * (10 * 1024 * 1024 + 1)
        big_file = SimpleUploadedFile(
            "big.pdf", big_content, content_type="application/pdf"
        )
        payload = self._base_payload(protocol_number="2026-BIG")
        payload["results_file"] = big_file

        response = self.staff_client.post(
            "/api/v1/studies/", payload, format="multipart"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    # ── Permissions ──────────────────────────────────────────────────────────

    def test_patient_cannot_create_study(self):
        """Patients are not allowed to create studies."""
        client, patient = self.authenticate_as_patient()
        payload = {
            "patient": str(patient.pk),
            "practice": str(self.practice.pk),
            "protocol_number": "2026-FORBIDDEN",
        }
        response = client.post("/api/v1/studies/", payload, format="multipart")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_cannot_create_study(self):
        """Unauthenticated requests are rejected (401 or 403)."""
        from rest_framework.test import APIClient

        anon = APIClient()
        response = anon.post(
            "/api/v1/studies/",
            self._base_payload(),
            format="multipart",
        )
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )


# ===========================================================================
# Last protocol number hint endpoint
# ===========================================================================


class TestLastProtocolNumberEndpoint(BaseTestCase):
    """Tests for GET /studies/last-protocol-number/."""

    def test_returns_null_when_no_studies(self):
        """Returns null when lab has no studies yet."""
        client, _ = self.authenticate_as_lab_staff()
        response = client.get("/api/v1/studies/last-protocol-number/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["last_protocol_number"] is None

    def test_returns_last_protocol_number(self):
        """Returns the highest protocol_number in the lab."""
        client, staff = self.authenticate_as_lab_staff(lab_client_id=1)
        patient = self.create_patient(lab_client_id=1)
        self.create_study(patient=patient, protocol_number="2026-001")
        self.create_study(patient=patient, protocol_number="2026-002")

        response = client.get("/api/v1/studies/last-protocol-number/")
        assert response.status_code == status.HTTP_200_OK
        # Ordered by -protocol_number (string): "2026-002" > "2026-001"
        assert response.data["last_protocol_number"] is not None

    def test_patient_cannot_access_hint(self):
        """Patients cannot access the last protocol number hint."""
        client, _ = self.authenticate_as_patient()
        response = client.get("/api/v1/studies/last-protocol-number/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_lab_staff_can_access_hint(self):
        """Lab staff can access the last protocol number hint."""
        client, _ = self.authenticate_as_lab_staff()
        response = client.get("/api/v1/studies/last-protocol-number/")
        assert response.status_code == status.HTTP_200_OK


# ===========================================================================
# End-to-end: complete study upload workflow
# ===========================================================================


class TestStudyUploadEndToEnd(BaseTestCase):
    """
    End-to-end tests covering the complete study creation and result upload flows.

    Scenario A: Create study without PDF → status pending → upload PDF later → completed
    Scenario B: Create study with PDF in one shot → status completed immediately
    Scenario C: Admin replaces / deletes result
    """

    def setUp(self):
        super().setUp()
        self.admin_client, self.admin = self.authenticate_as_admin(is_superuser=True)
        self.staff_client, self.staff = self.authenticate_as_lab_staff(lab_client_id=1)
        self.patient = self.create_patient(
            lab_client_id=1,
            first_name="Carlos",
            last_name="García",
            email="carlos@example.com",
        )
        self.doctor = self.create_doctor(first_name="Dr", last_name="House")
        self.practice = self.create_practice(name="Perfil Lipídico")

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_scenario_a_create_pending_then_upload(self):
        """
        Scenario A: Staff creates a pending study, then uploads results separately.

        Steps:
        1. Staff creates study (no file) → pending
        2. Patient sees study as pending
        3. Staff uploads PDF via upload_result → completed + notification
        4. Patient sees completed study
        5. Patient downloads PDF
        """
        from django.core import mail

        # ── Step 1: create study without file ─────────────────────────────
        create_payload = {
            "patient": str(self.patient.pk),
            "practice": str(self.practice.pk),
            "protocol_number": "2026-A001",
            "solicited_date": "2026-02-10",
            "ordered_by": str(self.doctor.pk),
        }
        response = self.staff_client.post(
            "/api/v1/studies/", create_payload, format="multipart"
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        study_id = response.data["study"]["id"]
        assert response.data["study"]["status"] == "pending"
        assert response.data["study"]["completed_at"] is None
        assert response.data["study"]["ordered_by_name"] is not None

        # ── Step 2: patient sees the study as pending ──────────────────────
        patient_client = self.authenticate(self.patient)
        response = patient_client.get("/api/v1/studies/")
        assert response.status_code == status.HTTP_200_OK
        study_data = next(
            (s for s in response.data["results"] if str(s["id"]) == str(study_id)), None
        )
        assert study_data is not None
        assert study_data["status"] == "pending"
        assert study_data["solicited_date"] == "2026-02-10"

        # ── Step 3: staff uploads PDF ──────────────────────────────────────
        mail.outbox = []
        upload_response = self.staff_client.post(
            f"/api/v1/studies/{study_id}/upload_result/",
            {"results_file": _make_pdf("perfil_lipidico.pdf"), "results": "LDL: 120"},
            format="multipart",
        )
        assert upload_response.status_code == status.HTTP_200_OK
        assert upload_response.data["study"]["status"] == "completed"
        assert upload_response.data["study"]["completed_at"] is not None

        # notification created
        assert Notification.objects.filter(
            user=self.patient, notification_type="result_ready"
        ).exists()
        # email sent
        assert len(mail.outbox) >= 1
        assert "carlos@example.com" in mail.outbox[-1].to

        # ── Step 4: patient sees completed study ───────────────────────────
        response = patient_client.get("/api/v1/studies/")
        study_data = next(
            (s for s in response.data["results"] if str(s["id"]) == str(study_id)), None
        )
        assert study_data["status"] == "completed"
        assert study_data["results_file"] is not None

        # ── Step 5: patient downloads PDF ──────────────────────────────────
        response = patient_client.get(f"/api/v1/studies/{study_id}/download_result/")
        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "application/pdf"
        assert "attachment" in response["Content-Disposition"]

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_scenario_b_create_with_file_in_one_shot(self):
        """
        Scenario B: Staff creates study + uploads PDF in a single request.

        Steps:
        1. Staff POST /studies/ with results_file → completed immediately
        2. Notification created for patient
        3. Patient can download result right away
        4. /studies/with-results/ lists the study
        5. /studies/available-for-upload/ does NOT include the study
        """
        from django.core import mail

        mail.outbox = []

        create_payload = {
            "patient": str(self.patient.pk),
            "practice": str(self.practice.pk),
            "protocol_number": "2026-B001",
            "solicited_date": "2026-02-15",
            "sample_collected_at": "2026-02-15T08:00:00",
            "results_file": _make_pdf("resultado_b.pdf"),
            "results": "Colesterol total: 190 mg/dL",
        }
        response = self.staff_client.post(
            "/api/v1/studies/", create_payload, format="multipart"
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        study_id = response.data["study"]["id"]

        # Study is immediately completed
        assert response.data["study"]["status"] == "completed"
        assert response.data["study"]["completed_at"] is not None
        assert response.data["study"]["results_file"] is not None

        # Notification sent
        assert Notification.objects.filter(
            user=self.patient, notification_type="result_ready"
        ).exists()
        assert len(mail.outbox) >= 1
        assert "carlos@example.com" in mail.outbox[-1].to

        # Patient can download immediately
        patient_client = self.authenticate(self.patient)
        dl_response = patient_client.get(f"/api/v1/studies/{study_id}/download_result/")
        assert dl_response.status_code == status.HTTP_200_OK
        assert dl_response["Content-Type"] == "application/pdf"

        # Appears in with-results admin list
        response = self.admin_client.get("/api/v1/studies/with-results/")
        assert response.status_code == status.HTTP_200_OK
        ids = [str(s["id"]) for s in response.data.get("results", response.data)]
        assert str(study_id) in ids

        # Does NOT appear in available-for-upload
        response = self.admin_client.get("/api/v1/studies/available-for-upload/")
        assert response.status_code == status.HTTP_200_OK
        ids = [str(s["id"]) for s in response.data.get("results", response.data)]
        assert str(study_id) not in ids

    def test_scenario_c_admin_replaces_and_deletes_result(self):
        """
        Scenario C: Admin replaces existing result, then deletes it.

        Steps:
        1. Create a completed study with a result file
        2. Admin replaces result via upload_result
        3. Admin deletes result → study reverts to in_progress
        4. Study now appears in available-for-upload
        """
        # Setup: completed study
        study = self.create_study(
            patient=self.patient,
            practice=self.practice,
            status="in_progress",
            lab_client_id=1,
        )
        # Upload initial result via staff
        self.staff_client.post(
            f"/api/v1/studies/{study.pk}/upload_result/",
            {"results_file": _make_pdf("v1.pdf"), "results": "Version 1"},
            format="multipart",
        )
        study.refresh_from_db()
        assert study.status == "completed"

        # ── Step 2: admin replaces ─────────────────────────────────────────
        response = self.admin_client.post(
            f"/api/v1/studies/{study.pk}/upload_result/",
            {"results_file": _make_pdf("v2.pdf"), "results": "Version 2"},
            format="multipart",
        )
        assert response.status_code == status.HTTP_200_OK
        study.refresh_from_db()
        assert study.status == "completed"
        assert "v2.pdf" in study.results_file.name

        # ── Step 3: admin deletes ──────────────────────────────────────────
        response = self.admin_client.delete(
            f"/api/v1/studies/{study.pk}/delete-result/"
        )
        assert response.status_code == status.HTTP_200_OK
        study.refresh_from_db()
        assert study.status == "in_progress"
        assert not study.results_file

        # ── Step 4: now available for upload ──────────────────────────────
        response = self.admin_client.get("/api/v1/studies/available-for-upload/")
        ids = [str(s["id"]) for s in response.data.get("results", response.data)]
        assert str(study.pk) in ids

    def test_soft_delete_study(self):
        """Admin can soft-delete a study; it disappears from lists."""
        study = self.create_study(
            patient=self.patient, practice=self.practice, lab_client_id=1
        )
        study_id = str(study.pk)

        response = self.admin_client.delete(f"/api/v1/studies/{study_id}/")
        assert response.status_code == status.HTTP_200_OK

        study.refresh_from_db()
        assert study.is_deleted is True

        # Does not appear in list
        patient_client = self.authenticate(self.patient)
        response = patient_client.get("/api/v1/studies/")
        ids = [str(s["id"]) for s in response.data.get("results", [])]
        assert study_id not in ids

    def test_patient_cannot_access_other_patient_study(self):
        """Patient cannot download or view another patient's study."""
        other_patient = self.create_patient(email="other@example.com")
        other_study = self.create_study(
            patient=other_patient,
            practice=self.practice,
            status="completed",
        )

        patient_client = self.authenticate(self.patient)

        # List: other patient's study not visible
        response = patient_client.get("/api/v1/studies/")
        ids = [str(s["id"]) for s in response.data.get("results", [])]
        assert str(other_study.pk) not in ids

        # Download: 404 because queryset excludes it
        response = patient_client.get(
            f"/api/v1/studies/{other_study.pk}/download_result/"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_doctor_ordered_by_appears_in_response(self):
        """ordered_by_name is populated in study response when a doctor is assigned."""
        study = self.create_study(
            patient=self.patient,
            practice=self.practice,
            ordered_by=self.doctor,
            lab_client_id=1,
        )

        patient_client = self.authenticate(self.patient)
        response = patient_client.get(f"/api/v1/studies/{study.pk}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["ordered_by_name"] is not None
        assert "House" in response.data["ordered_by_name"]
