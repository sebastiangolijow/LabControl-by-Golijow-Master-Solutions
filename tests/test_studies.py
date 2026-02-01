"""Tests for studies app following TDD principles."""

from decimal import Decimal

from rest_framework import status

from apps.studies.models import Study
from apps.studies.models import StudyType
from tests.base import BaseTestCase


class TestStudyTypeModel(BaseTestCase):
    """Test cases for StudyType model."""

    def test_create_study_type(self):
        """Test creating a study type."""
        study_type = self.create_study_type()
        assert study_type.name == "Complete Blood Count"
        assert study_type.code.startswith("CBC")
        assert study_type.base_price == Decimal("50.00")
        assert study_type.is_active is True

    def test_study_type_has_uuid(self):
        """Test that study type has UUID field."""
        study_type = self.create_study_type()
        self.assertUUID(study_type.uuid)

    def test_study_type_has_timestamps(self):
        """Test that study type has timestamp fields."""
        study_type = self.create_study_type()
        self.assertIsNotNone(study_type.created_at)
        self.assertIsNotNone(study_type.updated_at)
        self.assertTimestampRecent(study_type.created_at)

    def test_study_type_str_representation(self):
        """Test study type string representation."""
        study_type = self.create_study_type()
        assert str(study_type) == f"{study_type.name} ({study_type.code})"

    def test_study_type_custom_staff_active(self):
        """Test StudyTypeManager.active() method."""
        active = self.create_study_type(is_active=True)
        inactive = self.create_study_type(code="INV001", is_active=False)

        active_types = StudyType.objects.active()
        assert active in active_types
        assert inactive not in active_types


class TestStudyModel(BaseTestCase):
    """Test cases for Study model."""

    def test_create_study(self):
        """Test creating a study."""
        study = self.create_study()
        assert study.order_number.startswith("ORD-2024-")
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

        # Update study
        study.status = "in_progress"
        study.save()
        assert study.history.count() == 2  # Created + Updated

    def test_study_str_representation(self):
        """Test study string representation."""
        study = self.create_study()
        expected = f"{study.order_number} - {study.study_type.name}"
        assert str(study) == expected

    def test_study_custom_staff_pending(self):
        """Test StudyManager.pending() method."""
        pending_study = self.create_study(status="pending")
        completed_study = self.create_study(
            order_number="ORD-2024-9999", status="completed"
        )

        pending_studies = Study.objects.pending()
        assert pending_study in pending_studies
        assert completed_study not in pending_studies

    def test_study_custom_staff_completed(self):
        """Test StudyManager.completed() method."""
        pending_study = self.create_study(status="pending")
        completed_study = self.create_study(
            order_number="ORD-2024-9999", status="completed"
        )

        completed_studies = Study.objects.completed()
        assert completed_study in completed_studies
        assert pending_study not in completed_studies

    def test_study_custom_staff_for_patient(self):
        """Test StudyManager.for_patient() method."""
        patient1 = self.create_patient()
        patient2 = self.create_patient()

        study1 = self.create_study(patient=patient1)
        study2 = self.create_study(patient=patient2, order_number="ORD-2024-9999")

        patient1_studies = Study.objects.for_patient(patient1)
        assert study1 in patient1_studies
        assert study2 not in patient1_studies

    def test_study_lab_client_isolation(self):
        """Test multi-tenant isolation."""
        lab1_patient = self.create_patient(lab_client_id=1)
        lab2_patient = self.create_patient(lab_client_id=2)

        lab1_study = self.create_study(patient=lab1_patient)
        lab2_study = self.create_study(
            patient=lab2_patient, order_number="ORD-2024-9999"
        )

        lab1_studies = Study.objects.for_lab(1)
        assert lab1_study in lab1_studies
        assert lab2_study not in lab1_studies


class TestStudyAPI(BaseTestCase):
    """Test cases for Study API endpoints."""

    def test_list_study_types(self):
        """Test listing active study types."""
        client, user = self.authenticate_as_patient()
        _study_type = self.create_study_type()  # noqa: F841

        response = client.get("/api/v1/studies/types/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_list_patient_studies(self):
        """Test patient can see their own studies."""
        client, patient = self.authenticate_as_patient()
        study = self.create_study(patient=patient)

        response = client.get("/api/v1/studies/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["order_number"] == study.order_number

    def test_patient_cannot_see_other_patient_studies(self):
        """Test patients cannot see other patients' studies."""
        client, patient1 = self.authenticate_as_patient()
        patient2 = self.create_patient()

        # Create study for another patient
        _study = self.create_study(patient=patient2)  # noqa: F841

        response = client.get("/api/v1/studies/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 0

    def test_lab_staff_can_see_lab_studies(self):
        """Test lab manager can see all studies in their lab."""
        client, staff = self.authenticate_as_lab_staff()
        patient = self.create_patient(lab_client_id=staff.lab_client_id)

        _study = self.create_study(patient=patient)  # noqa: F841

        response = client.get("/api/v1/studies/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) >= 1
