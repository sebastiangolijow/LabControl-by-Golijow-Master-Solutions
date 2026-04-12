"""
Tests for LabWin Firebird sync feature.

Tests cover:
- Data mappers (name parsing, date parsing, field mapping)
- Connector factory
- Mock connector behavior
- Sync task (creates records, idempotency, incremental sync, error handling)
"""

from datetime import date, datetime
from unittest.mock import patch

from django.test import override_settings

from apps.labwin_sync.connectors import get_connector
from apps.labwin_sync.connectors.mock import (
    SAMPLE_DETERS,
    SAMPLE_MEDICOS,
    SAMPLE_NOMEN,
    SAMPLE_PACIENTES,
    MockLabWinConnector,
)
from apps.labwin_sync.mappers import (
    map_doctor,
    map_patient,
    map_practice,
    map_study,
    parse_date,
    parse_datetime,
    parse_name,
)
from apps.labwin_sync.models import SyncedRecord, SyncLog
from apps.labwin_sync.tasks import sync_labwin_results
from apps.studies.models import Practice, Study
from apps.users.models import User
from tests.base import BaseTestCase

# ======================
# Mapper Tests
# ======================


class ParseNameTests(BaseTestCase):
    """Tests for the parse_name helper."""

    def test_comma_separated_last_first(self):
        first, last = parse_name("Garcia, Maria")
        self.assertEqual(first, "Maria")
        self.assertEqual(last, "Garcia")

    def test_space_separated_first_last(self):
        first, last = parse_name("Pedro Rodriguez")
        self.assertEqual(first, "Pedro")
        self.assertEqual(last, "Rodriguez")

    def test_single_name(self):
        first, last = parse_name("SingleName")
        self.assertEqual(first, "SingleName")
        self.assertEqual(last, "")

    def test_empty_string(self):
        first, last = parse_name("")
        self.assertEqual(first, "")
        self.assertEqual(last, "")

    def test_none(self):
        first, last = parse_name(None)
        self.assertEqual(first, "")
        self.assertEqual(last, "")

    def test_whitespace_stripped(self):
        first, last = parse_name("  Garcia ,  Maria  ")
        self.assertEqual(first, "Maria")
        self.assertEqual(last, "Garcia")

    def test_multiple_spaces_first_last(self):
        first, last = parse_name("Ana Maria Fernandez")
        self.assertEqual(first, "Ana")
        self.assertEqual(last, "Maria Fernandez")


class ParseDateTests(BaseTestCase):
    """Tests for the parse_date helper."""

    def test_valid_date(self):
        result = parse_date("20251028")
        self.assertEqual(result, date(2025, 10, 28))

    def test_empty_string(self):
        self.assertIsNone(parse_date(""))

    def test_none(self):
        self.assertIsNone(parse_date(None))

    def test_invalid_format(self):
        self.assertIsNone(parse_date("2025-10-28"))

    def test_invalid_date_values(self):
        self.assertIsNone(parse_date("20251332"))

    def test_short_string(self):
        self.assertIsNone(parse_date("2025"))


class ParseDatetimeTests(BaseTestCase):
    """Tests for the parse_datetime helper."""

    def test_date_and_time(self):
        result = parse_datetime("20251028", "09:30")
        self.assertEqual(result.year, 2025)
        self.assertEqual(result.month, 10)
        self.assertEqual(result.day, 28)
        self.assertEqual(result.hour, 9)
        self.assertEqual(result.minute, 30)
        self.assertIsNotNone(result.tzinfo)

    def test_date_only(self):
        result = parse_datetime("20251028")
        self.assertEqual(result.year, 2025)
        self.assertEqual(result.hour, 0)
        self.assertIsNotNone(result.tzinfo)

    def test_invalid_date(self):
        self.assertIsNone(parse_datetime("", "09:30"))

    def test_invalid_time_falls_back_to_midnight(self):
        result = parse_datetime("20251028", "invalid")
        self.assertEqual(result.hour, 0)
        self.assertIsNotNone(result.tzinfo)


class MapPatientTests(BaseTestCase):
    """Tests for map_patient mapper."""

    def test_maps_all_fields(self):
        row = SAMPLE_PACIENTES[100001]
        result = map_patient(row)

        self.assertEqual(result["first_name"], "Maria")
        self.assertEqual(result["last_name"], "Garcia")
        self.assertEqual(result["dni"], "30123456")
        self.assertEqual(result["gender"], "F")
        self.assertEqual(result["birthday"], date(1985, 3, 15))
        self.assertEqual(result["mutual_code"], 1)
        self.assertEqual(result["carnet"], "ABC123")
        self.assertEqual(result["phone_number"], "11-2345-6789")
        self.assertEqual(result["direction"], "Av. Corrientes 1234")
        self.assertEqual(result["location"], "CABA")
        self.assertEqual(result["email"], "maria.garcia@test.com")
        self.assertEqual(result["role"], "patient")

    def test_male_gender(self):
        row = SAMPLE_PACIENTES[100002]
        result = map_patient(row)
        self.assertEqual(result["gender"], "M")

    def test_empty_email_returns_none(self):
        row = SAMPLE_PACIENTES[100002]
        result = map_patient(row)
        self.assertIsNone(result["email"])

    def test_fallback_to_telefono_when_no_celular(self):
        row = SAMPLE_PACIENTES[100001].copy()
        row["CELULAR_FLD"] = ""
        result = map_patient(row)
        self.assertEqual(result["phone_number"], "011-4555-1234")


class MapDoctorTests(BaseTestCase):
    """Tests for map_doctor mapper."""

    def test_maps_all_fields(self):
        row = SAMPLE_MEDICOS[501]
        result = map_doctor(row)

        self.assertEqual(result["first_name"], "Juan")
        self.assertEqual(result["last_name"], "Lopez")
        self.assertEqual(result["matricula"], "MN12345")
        self.assertEqual(result["email"], "dr.lopez@test.com")
        self.assertEqual(result["role"], "doctor")

    def test_empty_email_returns_none(self):
        row = SAMPLE_MEDICOS[502]
        result = map_doctor(row)
        self.assertIsNone(result["email"])


class MapPracticeTests(BaseTestCase):
    """Tests for map_practice mapper."""

    def test_maps_all_fields(self):
        row = SAMPLE_NOMEN["HEMC"]
        result = map_practice(row)

        self.assertEqual(result["code"], "HEMC")
        self.assertEqual(result["name"], "Hemograma Completo")
        self.assertEqual(result["delay_days"], 1)
        self.assertTrue(result["is_active"])


class MapStudyTests(BaseTestCase):
    """Tests for map_study mapper."""

    def test_maps_all_fields(self):
        import uuid

        patient_pk = uuid.uuid4()
        practice_pk = uuid.uuid4()
        doctor_pk = uuid.uuid4()
        row = SAMPLE_DETERS[0]  # GLU-Bi for order 100001

        result = map_study(row, patient_pk, practice_pk, doctor_pk)

        self.assertEqual(result["protocol_number"], "LW-100001-GLU-Bi")
        self.assertEqual(result["patient_id"], patient_pk)
        self.assertEqual(result["practice_id"], practice_pk)
        self.assertEqual(result["ordered_by_id"], doctor_pk)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["results"], "92")
        self.assertEqual(result["sample_id"], "100001")

    def test_protocol_number_format(self):
        import uuid

        row = SAMPLE_DETERS[1]  # HEMC for order 100001
        result = map_study(row, uuid.uuid4(), uuid.uuid4())
        self.assertEqual(result["protocol_number"], "LW-100001-HEMC")


# ======================
# Connector Tests
# ======================


class ConnectorFactoryTests(BaseTestCase):
    """Tests for the connector factory."""

    @override_settings(LABWIN_USE_MOCK=True)
    def test_returns_mock_when_setting_true(self):
        connector = get_connector()
        self.assertIsInstance(connector, MockLabWinConnector)

    def test_explicit_use_mock(self):
        connector = get_connector(use_mock=True)
        self.assertIsInstance(connector, MockLabWinConnector)


class MockConnectorTests(BaseTestCase):
    """Tests for the mock connector."""

    def test_context_manager(self):
        with MockLabWinConnector() as conn:
            self.assertTrue(conn._connected)
        self.assertFalse(conn._connected)

    def test_fetch_validated_deters_returns_all(self):
        with MockLabWinConnector() as conn:
            all_rows = []
            for batch in conn.fetch_validated_deters():
                all_rows.extend(batch)
            # Should only return validated rows (VALIDADO_FLD == "1")
            validated_count = sum(
                1 for row in SAMPLE_DETERS if row.get("VALIDADO_FLD") == "1"
            )
            self.assertEqual(len(all_rows), validated_count)
            # Verify all returned rows are validated
            for row in all_rows:
                self.assertEqual(row["VALIDADO_FLD"], "1")

    def test_fetch_validated_deters_incremental(self):
        with MockLabWinConnector() as conn:
            all_rows = []
            for batch in conn.fetch_validated_deters(
                since_fecha="20251028", since_numero=100001
            ):
                all_rows.extend(batch)
            # Should get rows after 100001 on 20251028 + all on later dates
            self.assertTrue(len(all_rows) < len(SAMPLE_DETERS))
            for row in all_rows:
                self.assertTrue(
                    row["FECHA_FLD"] > "20251028"
                    or (row["FECHA_FLD"] == "20251028" and row["NUMERO_FLD"] > 100001)
                )

    def test_fetch_pacientes(self):
        with MockLabWinConnector() as conn:
            result = conn.fetch_pacientes([100001, 100002])
            self.assertIn(100001, result)
            self.assertIn(100002, result)
            self.assertEqual(result[100001]["NOMBRE_FLD"], "Garcia, Maria")

    def test_fetch_pacientes_missing_key(self):
        with MockLabWinConnector() as conn:
            result = conn.fetch_pacientes([999999])
            self.assertEqual(result, {})

    def test_fetch_medicos(self):
        with MockLabWinConnector() as conn:
            result = conn.fetch_medicos([501])
            self.assertIn(501, result)
            self.assertEqual(result[501]["MATNAC_FLD"], "MN12345")

    def test_fetch_nomen(self):
        with MockLabWinConnector() as conn:
            result = conn.fetch_nomen(["GLU-Bi", "HEMC"])
            self.assertIn("GLU-Bi", result)
            self.assertIn("HEMC", result)


# ======================
# Sync Task Tests
# ======================


@override_settings(
    LABWIN_USE_MOCK=True,
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class SyncTaskTests(BaseTestCase):
    """Integration tests for the sync_labwin_results task."""

    def test_sync_creates_records(self):
        """Full sync creates patients, doctors, practices, and studies."""
        result = sync_labwin_results(lab_client_id=1, full_sync=True)

        self.assertGreater(result["studies_created"], 0)
        self.assertGreater(result["patients_created"], 0)
        self.assertGreater(result["practices_created"], 0)

        # Verify studies exist with LW- prefix (only validated rows)
        lw_studies = Study.objects.filter(protocol_number__startswith="LW-")
        validated_count = sum(
            1 for row in SAMPLE_DETERS if row.get("VALIDADO_FLD") == "1"
        )
        self.assertEqual(lw_studies.count(), validated_count)

        # Verify patients created
        synced_patients = SyncedRecord.objects.filter(source_table="PACIENTES")
        self.assertGreater(synced_patients.count(), 0)

    def test_sync_creates_sync_log(self):
        """Sync creates a SyncLog record with correct status."""
        sync_labwin_results(lab_client_id=1, full_sync=True)

        log = SyncLog.objects.first()
        self.assertIsNotNone(log)
        self.assertIn(log.status, ["completed", "partial"])
        self.assertIsNotNone(log.completed_at)
        self.assertEqual(log.lab_client_id, 1)
        self.assertGreater(log.studies_created, 0)

    def test_sync_is_idempotent(self):
        """Running sync twice with same data creates no duplicates."""
        result1 = sync_labwin_results(lab_client_id=1, full_sync=True)
        studies_after_first = Study.objects.filter(
            protocol_number__startswith="LW-"
        ).count()

        result2 = sync_labwin_results(lab_client_id=1, full_sync=True)
        studies_after_second = Study.objects.filter(
            protocol_number__startswith="LW-"
        ).count()

        # No new studies created on second run
        self.assertEqual(studies_after_first, studies_after_second)
        self.assertEqual(result2["studies_created"], 0)

    def test_sync_incremental(self):
        """Incremental sync only processes records after the cursor."""
        # First full sync
        sync_labwin_results(lab_client_id=1, full_sync=True)
        first_count = Study.objects.filter(protocol_number__startswith="LW-").count()

        # Second incremental sync (no new data in mock)
        result = sync_labwin_results(lab_client_id=1, full_sync=False)

        # No new studies since cursor is past all mock data
        self.assertEqual(result["studies_created"], 0)
        self.assertEqual(
            Study.objects.filter(protocol_number__startswith="LW-").count(),
            first_count,
        )

    def test_sync_cursor_saved(self):
        """SyncLog saves the cursor for incremental sync."""
        sync_labwin_results(lab_client_id=1, full_sync=True)

        log = SyncLog.objects.filter(status__in=["completed", "partial"]).first()
        self.assertIsNotNone(log)
        self.assertIsNotNone(log.last_synced_numero)
        self.assertTrue(log.last_synced_fecha)

    def test_sync_study_has_results(self):
        """Synced studies contain the raw RESULT_FLD value."""
        sync_labwin_results(lab_client_id=1, full_sync=True)

        glu_study = Study.objects.filter(protocol_number="LW-100001-GLU-Bi").first()
        self.assertIsNotNone(glu_study)
        self.assertEqual(glu_study.results, "92")

        hemc_study = Study.objects.filter(protocol_number="LW-100001-HEMC").first()
        self.assertIsNotNone(hemc_study)
        self.assertIn("|", hemc_study.results)  # Pipe-delimited

    def test_sync_study_status_completed(self):
        """Synced studies have status 'completed'."""
        sync_labwin_results(lab_client_id=1, full_sync=True)

        for study in Study.objects.filter(protocol_number__startswith="LW-"):
            self.assertEqual(study.status, "completed")

    def test_sync_creates_practices_with_code(self):
        """Synced practices have the LabWin code set."""
        sync_labwin_results(lab_client_id=1, full_sync=True)

        glu = Practice.objects.filter(code="GLU-Bi").first()
        self.assertIsNotNone(glu)
        self.assertEqual(glu.name, "Glucemia Basal")

    def test_sync_doctor_matched_by_matricula(self):
        """Existing doctors are matched by matricula, not duplicated."""
        # Pre-create a doctor with matching matricula
        existing = self.create_doctor(matricula="MN12345")

        sync_labwin_results(lab_client_id=1, full_sync=True)

        # Should not have created a duplicate doctor with this matricula
        doctors_with_mat = User.objects.filter(matricula="MN12345", role="doctor")
        self.assertEqual(doctors_with_mat.count(), 1)
        self.assertEqual(doctors_with_mat.first().pk, existing.pk)

    def test_sync_patient_matched_by_dni(self):
        """Existing patients are matched by DNI, not duplicated."""
        existing = self.create_patient(dni="30123456", lab_client_id=1)

        sync_labwin_results(lab_client_id=1, full_sync=True)

        patients_with_dni = User.objects.filter(
            dni="30123456",
            role="patient",
            lab_client_id=1,
        )
        self.assertEqual(patients_with_dni.count(), 1)

    def test_sync_lab_client_id_assigned(self):
        """Synced records have the correct lab_client_id."""
        sync_labwin_results(lab_client_id=42, full_sync=True)

        for study in Study.objects.filter(protocol_number__startswith="LW-"):
            self.assertEqual(study.lab_client_id, 42)

    def test_sync_error_handling_continues(self):
        """Sync continues processing after individual row errors."""
        with patch(
            "apps.labwin_sync.tasks._get_or_create_patient",
            side_effect=[Exception("test error"), None],
        ):
            # Should not raise, should complete with errors
            result = sync_labwin_results(lab_client_id=1, full_sync=True)
            self.assertGreater(result["error_count"], 0)

            # SyncLog should record the errors
            log = SyncLog.objects.order_by("-started_at").first()
            self.assertGreater(log.error_count, 0)


# ======================
# Model Tests
# ======================


class SyncLogModelTests(BaseTestCase):
    """Tests for the SyncLog model."""

    def test_create_sync_log(self):
        log = SyncLog.objects.create(
            status="started",
            lab_client_id=1,
        )
        self.assertEqual(str(log.pk), str(log.uuid))
        self.assertEqual(log.status, "started")
        self.assertIsNotNone(log.started_at)

    def test_sync_log_str(self):
        log = SyncLog.objects.create(status="completed", lab_client_id=1)
        self.assertIn("completed", str(log))


class SyncedRecordModelTests(BaseTestCase):
    """Tests for the SyncedRecord model."""

    def test_create_synced_record(self):
        import uuid

        log = SyncLog.objects.create(status="started", lab_client_id=1)
        record = SyncedRecord.objects.create(
            source_table="DETERS",
            source_key="100001:GLU-Bi",
            target_model="Study",
            target_uuid=uuid.uuid4(),
            lab_client_id=1,
            sync_log=log,
        )
        self.assertEqual(record.source_table, "DETERS")
        self.assertIn("DETERS", str(record))

    def test_unique_together_constraint(self):
        import uuid

        from django.db import IntegrityError

        log = SyncLog.objects.create(status="started", lab_client_id=1)
        SyncedRecord.objects.create(
            source_table="DETERS",
            source_key="100001:GLU-Bi",
            target_model="Study",
            target_uuid=uuid.uuid4(),
            lab_client_id=1,
            sync_log=log,
        )
        with self.assertRaises(IntegrityError):
            SyncedRecord.objects.create(
                source_table="DETERS",
                source_key="100001:GLU-Bi",
                target_model="Study",
                target_uuid=uuid.uuid4(),
                lab_client_id=1,
                sync_log=log,
            )
