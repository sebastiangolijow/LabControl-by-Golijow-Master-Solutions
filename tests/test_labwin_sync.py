"""
Tests for LabWin Firebird sync feature.

Tests cover:
- Data mappers (name parsing, date parsing, field mapping)
- Connector factory
- Mock connector behavior
- Sync task (creates records, idempotency, incremental sync, error handling)
- FTP PDF fetch (mock connector, study matching, file attachment)
"""

import gzip
import shutil
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.labwin_sync.connectors import get_connector
from apps.labwin_sync.connectors.mock import (
    SAMPLE_DETERS,
    SAMPLE_MEDICOS,
    SAMPLE_NOMEN,
    SAMPLE_PACIENTES,
    MockLabWinConnector,
)
from apps.labwin_sync.ftp import get_ftp_connector
from apps.labwin_sync.ftp.mock import MockFTPConnector
from apps.labwin_sync.mappers import (
    is_pet_candidate,
    is_vet_practice,
    map_doctor,
    map_is_paid,
    map_patient,
    map_practice,
    map_study,
    map_study_practice,
    parse_date,
    parse_datetime,
    parse_name,
)
from apps.labwin_sync.models import SyncedRecord, SyncLog
from apps.labwin_sync.services.backup_import import (
    BackupImporter,
    BackupImportResult,
    CorruptBackup,
    FirebirdRestoreError,
    NoBackupFound,
)
from apps.labwin_sync.tasks import (
    cleanup_ftp_pdfs,
    fetch_ftp_pdfs,
    import_uploaded_backup,
    sync_labwin_results,
)
from apps.studies.models import Practice, Study, StudyPractice
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
        doctor_pk = uuid.uuid4()
        numero = 100001

        result = map_study(numero, patient_pk, doctor_pk, "20251028", "09:30")

        self.assertEqual(result["protocol_number"], "LW-100001")
        self.assertEqual(result["patient_id"], patient_pk)
        self.assertEqual(result["ordered_by_id"], doctor_pk)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["sample_id"], "100001")

    def test_protocol_number_format(self):
        import uuid

        result = map_study(100002, uuid.uuid4())
        self.assertEqual(result["protocol_number"], "LW-100002")


class MapStudyPracticeTests(BaseTestCase):
    """Tests for map_study_practice mapper."""

    def test_maps_all_fields(self):
        import uuid

        practice_pk = uuid.uuid4()
        row = SAMPLE_DETERS[0]  # GLU-Bi for order 100001

        result = map_study_practice(row, practice_pk)

        self.assertEqual(result["practice_id"], practice_pk)
        self.assertEqual(result["result"], "92")
        self.assertEqual(result["code"], "GLU-Bi")


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
# Mock DETERS rows are dated 2025-10-28 to 2025-10-30. To keep the existing
# SyncTaskTests valid as today's date drifts past the default 90-day window,
# override the window to a value that always covers the mock data. Tests that
# specifically exercise the window logic live in SyncWindowTests below and
# override these settings further.
@override_settings(
    LABWIN_SYNC_INITIAL_DAYS=10000,
    LABWIN_SYNC_ROLLING_DAYS=10000,
)
class SyncTaskTests(BaseTestCase):
    """Integration tests for the sync_labwin_results task."""

    def test_sync_creates_records(self):
        """Full sync creates patients, doctors, practices, and studies."""
        result = sync_labwin_results(lab_client_id=1, full_sync=True)

        self.assertGreater(result["studies_created"], 0)
        self.assertGreater(result["patients_created"], 0)
        self.assertGreater(result["practices_created"], 0)

        # Verify studies exist with LW- prefix (one study per unique NUMERO_FLD)
        lw_studies = Study.objects.filter(protocol_number__startswith="LW-")
        validated_rows = [r for r in SAMPLE_DETERS if r.get("VALIDADO_FLD") == "1"]
        unique_numeros = set(r["NUMERO_FLD"] for r in validated_rows)
        self.assertEqual(lw_studies.count(), len(unique_numeros))

        # Verify StudyPractice records created (one per validated DETERS row)
        self.assertEqual(StudyPractice.objects.count(), len(validated_rows))

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
        """Synced study practices contain the raw RESULT_FLD value."""
        sync_labwin_results(lab_client_id=1, full_sync=True)

        study = Study.objects.filter(protocol_number="LW-100001").first()
        self.assertIsNotNone(study)

        glu_sp = study.study_practices.filter(code="GLU-Bi").first()
        self.assertIsNotNone(glu_sp)
        self.assertEqual(glu_sp.result, "92")

        hemc_sp = study.study_practices.filter(code="HEMC").first()
        self.assertIsNotNone(hemc_sp)
        self.assertIn("|", hemc_sp.result)  # Pipe-delimited

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

    def test_sync_drops_duplicate_email_for_new_patient(self):
        """When a PACIENTES email collides with an existing user, the new
        patient is created with email=None instead of erroring the whole row.

        Real-data case: spouses/family members share an email address; both
        appear as separate PACIENTES rows but our User.email is unique=True.
        """
        from apps.labwin_sync.tasks import _get_or_create_patient

        # Pre-existing user squatting on the email
        User.objects.create_user(
            email="shared@family.com",
            first_name="Existing",
            last_name="User",
            role="patient",
            lab_client_id=1,
        )

        sync_log = SyncLog.objects.create(status="started", lab_client_id=1)
        counters = {
            "patients_created": 0,
            "patients_updated": 0,
            "doctors_created": 0,
            "doctors_updated": 0,
            "practices_created": 0,
            "studies_created": 0,
            "studies_updated": 0,
            "study_practices_created": 0,
        }
        # Synthetic PACIENTES row mirroring the real shape, with same email
        pac_row = {
            "NUMERO_FLD": 999001,
            "NOMBRE_FLD": "GARCIA, MARIA",
            "HCLIN_FLD": "99999001",  # DNI
            "SEXO_FLD": 2,
            "FNACIM_FLD": "19850101",
            "MUTUAL_FLD": 0,
            "MEDICO_FLD": 0,
            "NUMMEDICO_FLD": 0,
            "CARNET_FLD": "",
            "TELEFONO_FLD": "",
            "CELULAR_FLD": "",
            "DIRECCION_FLD": "",
            "LOCALIDAD_FLD": "",
            "EMAIL_FLD": "shared@family.com",  # Same as existing user
        }

        # Should not raise — should create the patient with email=None
        new_pk = _get_or_create_patient(pac_row, 1, sync_log, counters)

        self.assertIsNotNone(new_pk)
        self.assertEqual(counters["patients_created"], 1)
        new_user = User.objects.get(pk=new_pk)
        self.assertIsNone(new_user.email)
        # Names preserved in source casing (mapper doesn't titlecase)
        self.assertEqual(new_user.first_name.upper(), "MARIA")
        self.assertEqual(new_user.last_name.upper(), "GARCIA")


# ======================
# Sync Window Tests (rolling-window cursor behavior)
# ======================


class SyncWindowTests(BaseTestCase):
    """Tests for the date-window cursor logic in sync_labwin_results.

    The task uses two settings:
      - LABWIN_SYNC_INITIAL_DAYS for the very first sync (no prior SyncLog)
      - LABWIN_SYNC_ROLLING_DAYS for every subsequent sync

    These tests verify that the connector receives the correct since_fecha
    based on those settings and the prior-sync state.
    """

    def _capture_since_fecha(self):
        """Patch the connector's fetch_validated_deters to capture the
        since_fecha argument it's called with, then return an empty iterator
        so the task short-circuits."""
        captured = {}

        class _CapturingConnector:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

            def fetch_validated_deters(
                self_inner, since_fecha=None, since_numero=None, batch_size=500
            ):
                captured["since_fecha"] = since_fecha
                captured["since_numero"] = since_numero
                return iter([])  # No batches → task completes immediately

        return captured, _CapturingConnector()

    @override_settings(LABWIN_SYNC_INITIAL_DAYS=90)
    def test_first_sync_uses_initial_window(self):
        """No prior SyncLog → window starts LABWIN_SYNC_INITIAL_DAYS ago."""
        captured, connector = self._capture_since_fecha()

        with patch("apps.labwin_sync.tasks.get_connector", return_value=connector):
            sync_labwin_results(lab_client_id=1, full_sync=False)

        expected = (date.today() - timedelta(days=90)).strftime("%Y%m%d")
        self.assertEqual(captured["since_fecha"], expected)
        self.assertEqual(captured["since_numero"], -1)

    @override_settings(LABWIN_SYNC_INITIAL_DAYS=30)
    def test_initial_window_setting_is_honored(self):
        """Different LABWIN_SYNC_INITIAL_DAYS produces a different cutoff."""
        captured, connector = self._capture_since_fecha()

        with patch("apps.labwin_sync.tasks.get_connector", return_value=connector):
            sync_labwin_results(lab_client_id=1, full_sync=False)

        expected = (date.today() - timedelta(days=30)).strftime("%Y%m%d")
        self.assertEqual(captured["since_fecha"], expected)

    @override_settings(LABWIN_SYNC_ROLLING_DAYS=2)
    def test_subsequent_sync_uses_rolling_window(self):
        """A prior completed SyncLog → window starts LABWIN_SYNC_ROLLING_DAYS ago,
        regardless of how far the prior sync got. The point is to re-scan
        recent days for late-validated rows."""
        # Simulate an earlier successful sync that processed up to a date
        # well in the past.
        SyncLog.objects.create(
            status="completed",
            lab_client_id=1,
            last_synced_fecha="20200101",  # Far in the past
            last_synced_numero=999999,
        )

        captured, connector = self._capture_since_fecha()
        with patch("apps.labwin_sync.tasks.get_connector", return_value=connector):
            sync_labwin_results(lab_client_id=1, full_sync=False)

        # Window is "today minus 2 days", NOT the saved cursor value.
        expected = (date.today() - timedelta(days=2)).strftime("%Y%m%d")
        self.assertEqual(captured["since_fecha"], expected)
        self.assertEqual(captured["since_numero"], -1)

    @override_settings(
        LABWIN_SYNC_INITIAL_DAYS=10000,
        LABWIN_SYNC_ROLLING_DAYS=10000,
    )
    def test_full_sync_bypasses_window(self):
        """full_sync=True skips the date filter entirely (since_fecha=None)."""
        captured, connector = self._capture_since_fecha()

        with patch("apps.labwin_sync.tasks.get_connector", return_value=connector):
            sync_labwin_results(lab_client_id=1, full_sync=True)

        self.assertIsNone(captured["since_fecha"])
        self.assertIsNone(captured["since_numero"])

    @override_settings(
        LABWIN_SYNC_INITIAL_DAYS=10000,
        LABWIN_SYNC_ROLLING_DAYS=10000,
    )
    def test_resync_updates_result_when_changed(self):
        """Re-syncing a study where RESULT_FLD changed overwrites the result.
        This is the contract that makes the rolling window valuable: studies
        already in Postgres get refreshed every run."""
        # First sync — creates the study with original result
        sync_labwin_results(lab_client_id=1, full_sync=True)
        sp = StudyPractice.objects.filter(code="GLU-Bi").first()
        self.assertIsNotNone(sp)
        original_result = sp.result

        # Mutate the mock data: pretend the lab corrected the glucose result
        with patch.object(MockLabWinConnector, "fetch_validated_deters") as mock_fetch:
            mutated_deters = [dict(row) for row in SAMPLE_DETERS]
            for row in mutated_deters:
                if row.get("ABREV_FLD") == "GLU-Bi":
                    row["RESULT_FLD"] = "999"  # Corrected value

            def _fake_fetch(
                self_inner=None, since_fecha=None, since_numero=None, batch_size=500
            ):
                yield mutated_deters

            mock_fetch.side_effect = _fake_fetch

            sync_labwin_results(lab_client_id=1, full_sync=True)

        sp.refresh_from_db()
        self.assertEqual(sp.result, "999")
        self.assertNotEqual(sp.result, original_result)


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


# ======================
# FTP Connector Tests
# ======================


class FTPConnectorFactoryTests(BaseTestCase):
    """Tests for the FTP connector factory."""

    @override_settings(LABWIN_FTP_USE_MOCK=True)
    def test_returns_mock_when_setting_true(self):
        connector = get_ftp_connector()
        self.assertIsInstance(connector, MockFTPConnector)

    def test_explicit_use_mock(self):
        connector = get_ftp_connector(use_mock=True)
        self.assertIsInstance(connector, MockFTPConnector)


class MockFTPConnectorTests(BaseTestCase):
    """Tests for the mock FTP connector."""

    def test_context_manager(self):
        with MockFTPConnector() as conn:
            self.assertTrue(conn._connected)
        self.assertFalse(conn._connected)

    def test_list_pdf_files(self):
        with MockFTPConnector() as conn:
            files = conn.list_pdf_files()
            self.assertEqual(len(files), 3)
            self.assertIn("100001.pdf", files)
            self.assertIn("100002.pdf", files)

    def test_download_file(self):
        with MockFTPConnector() as conn:
            content = conn.download_file("100001.pdf")
            self.assertIsInstance(content, bytes)
            self.assertTrue(len(content) > 0)
            self.assertTrue(content.startswith(b"%PDF"))

    def test_download_missing_file_raises(self):
        with MockFTPConnector() as conn:
            with self.assertRaises(FileNotFoundError):
                conn.download_file("nonexistent.pdf")

    def test_delete_file(self):
        with MockFTPConnector() as conn:
            conn.delete_file("100001.pdf")
            files = conn.list_pdf_files()
            self.assertNotIn("100001.pdf", files)

    def test_delete_missing_file_raises(self):
        with MockFTPConnector() as conn:
            with self.assertRaises(FileNotFoundError):
                conn.delete_file("nonexistent.pdf")

    def test_download_deleted_file_raises(self):
        with MockFTPConnector() as conn:
            conn.delete_file("100001.pdf")
            with self.assertRaises(FileNotFoundError):
                conn.download_file("100001.pdf")

    def test_custom_files(self):
        custom = {"custom.pdf": b"%PDF-test"}
        with MockFTPConnector(files=custom) as conn:
            files = conn.list_pdf_files()
            self.assertEqual(files, ["custom.pdf"])
            content = conn.download_file("custom.pdf")
            self.assertEqual(content, b"%PDF-test")


# ======================
# FTP Fetch Task Tests
# ======================


@override_settings(
    LABWIN_USE_MOCK=True,
    LABWIN_FTP_USE_MOCK=True,
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class FetchFTPPDFsTests(BaseTestCase):
    """Integration tests for the fetch_ftp_pdfs task."""

    def _sync_labwin_first(self):
        """Run LabWin sync to create studies with sample_id values."""
        sync_labwin_results(lab_client_id=1, full_sync=True)
        return Study.objects.filter(protocol_number__startswith="LW-")

    def test_fetch_attaches_pdfs_to_studies(self):
        """PDFs are attached to matching studies."""
        studies = self._sync_labwin_first()
        self.assertTrue(studies.exists())

        result = fetch_ftp_pdfs(lab_client_id=1)

        self.assertGreater(result["files_found"], 0)
        self.assertGreater(result["files_attached"], 0)

        # Verify study has results_file
        study = Study.objects.get(protocol_number="LW-100001")
        self.assertTrue(study.results_file)
        self.assertIn("LW-100001", study.results_file.name)

    def test_fetch_skips_studies_with_existing_file(self):
        """Studies that already have results_file are skipped."""
        self._sync_labwin_first()

        # First fetch attaches PDFs
        fetch_ftp_pdfs(lab_client_id=1)

        # Second fetch should skip them
        result = fetch_ftp_pdfs(lab_client_id=1)

        self.assertEqual(result["files_attached"], 0)
        self.assertGreater(result["files_skipped"], 0)

    def test_fetch_skips_unmatched_files(self):
        """Files without matching studies are skipped."""
        # No LabWin sync — no studies with sample_id
        result = fetch_ftp_pdfs(lab_client_id=1)

        self.assertGreater(result["files_found"], 0)
        self.assertEqual(result["files_attached"], 0)
        self.assertGreater(result["files_skipped"], 0)

    def test_fetch_with_delete(self):
        """PDFs are deleted from FTP after download when requested."""
        self._sync_labwin_first()

        mock_ftp = MockFTPConnector()
        with patch(
            "apps.labwin_sync.tasks.get_ftp_connector",
            return_value=mock_ftp,
        ):
            result = fetch_ftp_pdfs(
                lab_client_id=1,
                delete_after_download=True,
            )

        self.assertGreater(result["files_deleted"], 0)

    def test_fetch_returns_correct_counters(self):
        """Result dict contains all expected counter fields."""
        self._sync_labwin_first()
        result = fetch_ftp_pdfs(lab_client_id=1)

        self.assertIn("files_found", result)
        self.assertIn("files_matched", result)
        self.assertIn("files_attached", result)
        self.assertIn("files_skipped", result)
        self.assertIn("error_count", result)
        self.assertIn("message", result)

    def test_fetch_filters_by_lab_client_id(self):
        """Only studies matching lab_client_id are considered."""
        self._sync_labwin_first()

        # Fetch with a different lab_client_id — no matches
        result = fetch_ftp_pdfs(lab_client_id=999)

        self.assertEqual(result["files_attached"], 0)

    def test_fetch_handles_download_error(self):
        """Errors during download are captured, not raised."""
        self._sync_labwin_first()

        mock_ftp = MockFTPConnector(files={"100001.pdf": b"%PDF-content"})
        # Make download raise for one file
        original_download = mock_ftp.download_file

        def failing_download(filename):
            if filename == "100001.pdf":
                raise IOError("Connection lost")
            return original_download(filename)

        mock_ftp.download_file = failing_download

        with patch(
            "apps.labwin_sync.tasks.get_ftp_connector",
            return_value=mock_ftp,
        ):
            result = fetch_ftp_pdfs(lab_client_id=1)

        self.assertGreater(result["error_count"], 0)


@override_settings(
    LABWIN_USE_MOCK=True,
    LABWIN_FTP_USE_MOCK=True,
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class CleanupFTPPDFsTests(BaseTestCase):
    """Integration tests for the cleanup_ftp_pdfs task."""

    def test_cleanup_deletes_processed_files(self):
        """Files for studies with results_file are deleted from FTP."""
        # Sync + fetch to attach PDFs
        sync_labwin_results(lab_client_id=1, full_sync=True)
        fetch_ftp_pdfs(lab_client_id=1)

        mock_ftp = MockFTPConnector()
        with patch(
            "apps.labwin_sync.tasks.get_ftp_connector",
            return_value=mock_ftp,
        ):
            result = cleanup_ftp_pdfs(lab_client_id=1)

        self.assertGreater(result["files_deleted"], 0)

    def test_cleanup_keeps_unprocessed_files(self):
        """Files for studies without results_file are kept."""
        # Sync but don't fetch — studies exist but have no results_file
        sync_labwin_results(lab_client_id=1, full_sync=True)

        mock_ftp = MockFTPConnector()
        with patch(
            "apps.labwin_sync.tasks.get_ftp_connector",
            return_value=mock_ftp,
        ):
            result = cleanup_ftp_pdfs(lab_client_id=1)

        self.assertEqual(result["files_deleted"], 0)
        self.assertGreater(result["files_kept"], 0)

    def test_cleanup_returns_correct_counters(self):
        """Result dict contains all expected counter fields."""
        mock_ftp = MockFTPConnector()
        with patch(
            "apps.labwin_sync.tasks.get_ftp_connector",
            return_value=mock_ftp,
        ):
            result = cleanup_ftp_pdfs(lab_client_id=1)

        self.assertIn("files_found", result)
        self.assertIn("files_deleted", result)
        self.assertIn("files_kept", result)
        self.assertIn("message", result)


# ======================
# BackupImporter (Phase B)
# ======================


def _make_fake_backup(
    dir_path: Path, name: str = "BASEDAT_20260424.fbk.gz", payload: bytes = None
) -> Path:
    """Write a valid-gzip file ≥ 1024 bytes (clears validate_backup minimum)."""
    if payload is None:
        # 64 KB of random bytes — incompressible, so gzipped size > 64 KB
        import os

        payload = os.urandom(64 * 1024)
    target = dir_path / name
    with gzip.open(target, "wb") as f:
        f.write(payload)
    return target


class BackupImporterDiscoveryTests(BaseTestCase):
    """find_latest_backup + validate_backup."""

    def setUp(self):
        super().setUp()
        self.tmp = Path(tempfile.mkdtemp())
        self.incoming = self.tmp / "incoming"
        self.processed = self.tmp / "processed"
        self.failed = self.tmp / "failed"
        for d in (self.incoming, self.processed, self.failed):
            d.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def _importer(self, **overrides):
        kwargs = {
            "incoming_dir": str(self.incoming),
            "processed_dir": str(self.processed),
            "failed_dir": str(self.failed),
        }
        kwargs.update(overrides)
        return BackupImporter(**kwargs)

    def test_find_latest_backup_returns_newest(self):
        old = _make_fake_backup(self.incoming, "old.fbk.gz")
        new = _make_fake_backup(self.incoming, "new.fbk.gz")
        # Force old's mtime backwards
        import os

        os.utime(old, (1000000, 1000000))
        result = self._importer().find_latest_backup()
        self.assertEqual(result, new)

    def test_find_latest_backup_skips_in_progress_uploads(self):
        partial = self.incoming / "partial.fbk.gz.uploading"
        partial.write_bytes(b"x")
        complete = _make_fake_backup(self.incoming, "complete.fbk.gz")
        result = self._importer().find_latest_backup()
        self.assertEqual(result, complete)

    def test_find_latest_backup_raises_when_empty(self):
        with self.assertRaises(NoBackupFound):
            self._importer().find_latest_backup()

    def test_find_latest_backup_raises_when_dir_missing(self):
        importer = self._importer(incoming_dir="/nonexistent/path/xyz123")
        with self.assertRaises(NoBackupFound):
            importer.find_latest_backup()

    def test_validate_rejects_empty_file(self):
        empty = self.incoming / "empty.fbk.gz"
        empty.touch()
        with self.assertRaises(CorruptBackup):
            self._importer().validate_backup(empty)

    def test_validate_rejects_non_gzip(self):
        bogus = self.incoming / "bogus.fbk.gz"
        bogus.write_bytes(b"this is not gzip" * 100)
        with self.assertRaises(CorruptBackup):
            self._importer().validate_backup(bogus)

    def test_validate_accepts_valid_gzip(self):
        valid = _make_fake_backup(self.incoming)
        # Should not raise
        self._importer().validate_backup(valid)


class BackupImporterMoveTests(BaseTestCase):
    """move_to_processed / move_to_failed."""

    def setUp(self):
        super().setUp()
        self.tmp = Path(tempfile.mkdtemp())
        self.incoming = self.tmp / "incoming"
        self.processed = self.tmp / "processed"
        self.failed = self.tmp / "failed"
        for d in (self.incoming, self.processed, self.failed):
            d.mkdir()
        self.backup = _make_fake_backup(self.incoming)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def _importer(self):
        return BackupImporter(
            incoming_dir=str(self.incoming),
            processed_dir=str(self.processed),
            failed_dir=str(self.failed),
        )

    def test_move_to_processed_appends_timestamp(self):
        self._importer().move_to_processed(self.backup)
        self.assertFalse(self.backup.exists())
        moved = list(self.processed.glob("*.fbk.gz"))
        self.assertEqual(len(moved), 1)
        # Filename should have __YYYYMMDDTHHMMSS suffix before .fbk.gz
        self.assertIn("__", moved[0].name)

    def test_move_to_failed_works(self):
        self._importer().move_to_failed(self.backup)
        self.assertFalse(self.backup.exists())
        self.assertEqual(len(list(self.failed.glob("*.fbk.gz"))), 1)


class BackupImporterRunTests(BaseTestCase):
    """End-to-end run() with mocked firebird + sync."""

    def setUp(self):
        super().setUp()
        self.tmp = Path(tempfile.mkdtemp())
        self.incoming = self.tmp / "incoming"
        self.processed = self.tmp / "processed"
        self.failed = self.tmp / "failed"
        for d in (self.incoming, self.processed, self.failed):
            d.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def _importer(self):
        return BackupImporter(
            incoming_dir=str(self.incoming),
            processed_dir=str(self.processed),
            failed_dir=str(self.failed),
            firebird_password="masterke",  # 8-char (FB 2.5 truncates)
        )

    def test_run_no_backup_returns_skipped(self):
        result = self._importer().run()
        self.assertEqual(result.status, "skipped")
        self.assertIn("No .fbk.gz", result.error)

    @patch("apps.labwin_sync.services.backup_import.BackupImporter.trigger_sync")
    @patch("apps.labwin_sync.services.backup_import.BackupImporter.restore_to_firebird")
    def test_run_happy_path_moves_to_processed(self, mock_restore, mock_sync):
        backup = _make_fake_backup(self.incoming)
        mock_sync.return_value = {"message": "Sync OK", "studies_created": 5}

        result = self._importer().run()

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.backup_filename, backup.name)
        self.assertEqual(result.sync_result["studies_created"], 5)
        self.assertFalse(backup.exists())
        self.assertEqual(len(list(self.processed.glob("*.fbk.gz"))), 1)
        self.assertEqual(len(list(self.failed.glob("*.fbk.gz"))), 0)
        mock_restore.assert_called_once()
        mock_sync.assert_called_once()

    @patch("apps.labwin_sync.services.backup_import.BackupImporter.restore_to_firebird")
    def test_run_restore_failure_moves_to_failed(self, mock_restore):
        backup = _make_fake_backup(self.incoming)
        mock_restore.side_effect = FirebirdRestoreError("simulated restore failure")

        result = self._importer().run()

        self.assertEqual(result.status, "failed")
        self.assertIn("simulated restore failure", result.error)
        self.assertFalse(backup.exists())
        self.assertEqual(len(list(self.failed.glob("*.fbk.gz"))), 1)
        self.assertEqual(len(list(self.processed.glob("*.fbk.gz"))), 0)

    @patch("apps.labwin_sync.services.backup_import.BackupImporter.trigger_sync")
    @patch("apps.labwin_sync.services.backup_import.BackupImporter.restore_to_firebird")
    def test_run_skip_restore_does_not_call_restore(self, mock_restore, mock_sync):
        _make_fake_backup(self.incoming)
        mock_sync.return_value = {"message": "Sync OK"}

        result = self._importer().run(skip_restore=True)

        self.assertEqual(result.status, "completed")
        mock_restore.assert_not_called()
        mock_sync.assert_called_once()

    @patch("apps.labwin_sync.services.backup_import.BackupImporter.trigger_sync")
    @patch("apps.labwin_sync.services.backup_import.BackupImporter.restore_to_firebird")
    def test_run_skip_sync_does_not_call_sync(self, mock_restore, mock_sync):
        _make_fake_backup(self.incoming)

        result = self._importer().run(skip_sync=True)

        self.assertEqual(result.status, "completed")
        mock_restore.assert_called_once()
        mock_sync.assert_not_called()

    @patch("apps.labwin_sync.services.backup_import.BackupImporter.trigger_sync")
    @patch("apps.labwin_sync.services.backup_import.BackupImporter.restore_to_firebird")
    def test_run_creates_synclog(self, mock_restore, mock_sync):
        _make_fake_backup(self.incoming)
        mock_sync.return_value = {"message": "Sync OK"}

        before = SyncLog.objects.count()
        self._importer().run()
        after = SyncLog.objects.count()

        self.assertEqual(after, before + 1)
        log = SyncLog.objects.latest("started_at")
        self.assertEqual(log.status, "completed")


class ImportUploadedBackupTaskTests(BaseTestCase):
    """The thin Celery wrapper task."""

    @patch("apps.labwin_sync.services.backup_import.BackupImporter.run")
    def test_task_returns_result_dict(self, mock_run):
        mock_run.return_value = BackupImportResult(
            status="completed",
            backup_filename="test.fbk.gz",
            backup_size_bytes=1024,
        )
        result = import_uploaded_backup(lab_client_id=1)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["backup_filename"], "test.fbk.gz")

    @patch("apps.labwin_sync.services.backup_import.BackupImporter.run")
    def test_task_passes_explicit_file_as_path(self, mock_run):
        mock_run.return_value = BackupImportResult(status="completed")
        import_uploaded_backup(lab_client_id=1, explicit_file="/some/path.fbk.gz")
        # First positional / kwarg arg should be a Path
        call = mock_run.call_args
        path_arg = call.kwargs.get("explicit_file") or (
            call.args[0] if call.args else None
        )
        self.assertIsInstance(path_arg, Path)
        self.assertEqual(str(path_arg), "/some/path.fbk.gz")


class ImportBackupCommandTests(BaseTestCase):
    """The `import_backup` management command."""

    @patch("apps.labwin_sync.services.backup_import.BackupImporter.run")
    def test_command_runs_synchronously_by_default(self, mock_run):
        mock_run.return_value = BackupImportResult(
            status="completed",
            backup_filename="test.fbk.gz",
            backup_size_bytes=1024,
        )
        from io import StringIO

        out = StringIO()
        call_command("import_backup", stdout=out)
        self.assertIn("completed", out.getvalue())
        mock_run.assert_called_once()

    @patch("apps.labwin_sync.services.backup_import.BackupImporter.run")
    def test_command_restore_only_flag_propagated(self, mock_run):
        mock_run.return_value = BackupImportResult(status="completed")
        call_command("import_backup", "--restore-only")
        self.assertTrue(mock_run.call_args.kwargs["skip_sync"])
        self.assertFalse(mock_run.call_args.kwargs["skip_restore"])

    @patch("apps.labwin_sync.services.backup_import.BackupImporter.run")
    def test_command_sync_only_flag_propagated(self, mock_run):
        mock_run.return_value = BackupImportResult(status="completed")
        call_command("import_backup", "--sync-only")
        self.assertTrue(mock_run.call_args.kwargs["skip_restore"])
        self.assertFalse(mock_run.call_args.kwargs["skip_sync"])

    def test_command_restore_only_and_sync_only_mutually_exclusive(self):
        with self.assertRaises(CommandError):
            call_command("import_backup", "--restore-only", "--sync-only")

    @patch("apps.labwin_sync.services.backup_import.BackupImporter.run")
    def test_command_failed_status_raises_command_error(self, mock_run):
        mock_run.return_value = BackupImportResult(
            status="failed",
            error="simulated failure",
        )
        with self.assertRaises(CommandError):
            call_command("import_backup")

    @patch("apps.labwin_sync.tasks.import_uploaded_backup")
    def test_command_use_celery_dispatches_to_task(self, mock_task):
        mock_task.delay.return_value = MagicMock(id="celery-task-id-123")
        from io import StringIO

        out = StringIO()
        call_command("import_backup", "--use-celery", stdout=out)
        mock_task.delay.assert_called_once()
        self.assertIn("celery-task-id-123", out.getvalue())

    def test_command_use_celery_with_restore_only_errors(self):
        with self.assertRaises(CommandError):
            call_command("import_backup", "--use-celery", "--restore-only")


# ======================
# is_paid / is_validated mapping (Phase 3)
# ======================


class MapIsPaidTests(BaseTestCase):
    """Tests for map_is_paid — derives Study.is_paid from PACIENTES.DEBEBONO_FLD."""

    def test_debebono_1_means_unpaid(self):
        self.assertFalse(map_is_paid({"DEBEBONO_FLD": "1"}))

    def test_debebono_0_means_paid(self):
        self.assertTrue(map_is_paid({"DEBEBONO_FLD": "0"}))

    def test_debebono_empty_means_paid(self):
        # Insurance-covered patients have empty DEBEBONO_FLD; they're paid via mutual.
        self.assertTrue(map_is_paid({"DEBEBONO_FLD": ""}))

    def test_debebono_missing_means_paid(self):
        # Defensive: if the key isn't in the row, default to paid (safest).
        self.assertTrue(map_is_paid({}))

    def test_none_row_means_paid(self):
        self.assertTrue(map_is_paid(None))


class MapStudyIsPaidIsValidatedTests(BaseTestCase):
    """Tests for map_study respecting is_paid and is_validated kwargs."""

    def setUp(self):
        super().setUp()
        import uuid as _uuid

        self.fake_pk = _uuid.uuid4()

    def test_defaults_to_paid_validated(self):
        result = map_study(100001, self.fake_pk)
        self.assertTrue(result["is_paid"])
        self.assertTrue(result["is_validated"])

    def test_explicit_unpaid(self):
        result = map_study(100001, self.fake_pk, is_paid=False)
        self.assertFalse(result["is_paid"])
        self.assertTrue(result["is_validated"])  # default

    def test_explicit_unvalidated(self):
        result = map_study(100001, self.fake_pk, is_validated=False)
        self.assertTrue(result["is_paid"])
        self.assertFalse(result["is_validated"])


class SyncIsPaidIsValidatedTests(BaseTestCase):
    """End-to-end: sync populates is_paid and is_validated correctly."""

    @override_settings(LABWIN_USE_MOCK=True)
    def test_sync_sets_is_paid_from_debebono(self):
        sync_labwin_results(lab_client_id=1, full_sync=True)

        # Mock fixtures: 100001 (DEBEBONO=''), 100002 (DEBEBONO='0'), 100003 (DEBEBONO='1')
        # Expect: 100001 paid, 100002 paid, 100003 unpaid.
        s1 = Study.objects.get(protocol_number="LW-100001")
        s2 = Study.objects.get(protocol_number="LW-100002")
        s3 = Study.objects.get(protocol_number="LW-100003")

        self.assertTrue(s1.is_paid, "Insurance patient (DEBEBONO='') should be paid")
        self.assertTrue(
            s2.is_paid, "Already-paid patient (DEBEBONO='0') should be paid"
        )
        self.assertFalse(
            s3.is_paid, "Owes-bono patient (DEBEBONO='1') should be UNPAID"
        )

    @override_settings(LABWIN_USE_MOCK=True)
    def test_sync_sets_is_validated_true_for_all_imported(self):
        sync_labwin_results(lab_client_id=1, full_sync=True)
        # The connector pre-filters to VALIDADO_FLD='1', so every imported
        # study is validated.
        for study in Study.objects.filter(protocol_number__startswith="LW-"):
            self.assertTrue(
                study.is_validated,
                f"{study.protocol_number} should be is_validated=True",
            )

    @override_settings(LABWIN_USE_MOCK=True)
    def test_resync_updates_is_paid_when_source_changes(self):
        """If a patient pays their bono between backups, the next sync flips is_paid."""
        # First sync — 100003 starts unpaid (DEBEBONO='1' in mock)
        sync_labwin_results(lab_client_id=1, full_sync=True)
        s3 = Study.objects.get(protocol_number="LW-100003")
        self.assertFalse(s3.is_paid)

        # Simulate the lab marking 100003 as paid in the source DB.
        # Mutate the in-memory mock fixture so the next sync sees DEBEBONO_FLD='0'.
        from apps.labwin_sync.connectors.mock import SAMPLE_PACIENTES

        original = SAMPLE_PACIENTES[100003]["DEBEBONO_FLD"]
        SAMPLE_PACIENTES[100003]["DEBEBONO_FLD"] = "0"
        try:
            sync_labwin_results(lab_client_id=1, full_sync=True)
        finally:
            SAMPLE_PACIENTES[100003][
                "DEBEBONO_FLD"
            ] = original  # don't leak across tests

        s3.refresh_from_db()
        self.assertTrue(
            s3.is_paid,
            "Re-sync should flip is_paid=True when source DEBEBONO_FLD changes from '1' to '0'",
        )


# ======================
# fetch_ftp_pdfs filename parsing (Phase 3)
# ======================


class FetchFTPPDFFilenameParsingTests(BaseTestCase):
    """Tests that fetch_ftp_pdfs handles both filename formats from the lab.

    Lab uses two formats:
      {NUMERO}.pdf                          (legacy)
      {NUMERO}-{DNI}-{NOMBRE}.pdf          (current — observed 2026-04-22)
    """

    def setUp(self):
        super().setUp()
        # Create a study with sample_id matching what's in the mock FTP fixtures
        # Mock FTP exposes: 100001.pdf, 100002.pdf, 100003.pdf
        # We synthesize one more study whose sample_id matches a dashed filename
        # so we can verify parsing without modifying the FTP mock.
        self.patient = self.create_patient()
        # sample_id matches the leading numero in 'LW-220197-39592918-SIRI,FRANCO.pdf'
        self.dashed_study = Study.objects.create(
            patient=self.patient,
            protocol_number="LW-220197",
            status="completed",
            sample_id="220197",
            lab_client_id=1,
        )

    def test_legacy_filename_format_still_works(self):
        """`100001.pdf` → looks up sample_id='100001'."""
        # This is what the existing FetchFTPPDFsTests already verify; we add
        # an explicit case here to lock in backward compatibility.
        sync_labwin_results(lab_client_id=1, full_sync=True)  # creates LW-100001
        result = fetch_ftp_pdfs(lab_client_id=1)
        # 100001.pdf in mock should attach to LW-100001 created by sync above
        s = Study.objects.get(protocol_number="LW-100001")
        self.assertTrue(s.results_file)

    def test_dashed_filename_format_extracts_numero(self):
        """`220197-39592918-SIRI,FRANCO.pdf` → looks up sample_id='220197'."""
        # Inject a fake FTP connector that returns the dashed filename
        from apps.labwin_sync.ftp.mock import MockFTPConnector

        class DashedNamedFTP(MockFTPConnector):
            def list_pdf_files(self):
                return ["220197-39592918-SIRI,FRANCO.pdf"]

            def download_file(self, filename):
                return b"%PDF-1.4 fake content"

        with patch(
            "apps.labwin_sync.tasks.get_ftp_connector", return_value=DashedNamedFTP()
        ):
            result = fetch_ftp_pdfs(lab_client_id=1)

        self.assertEqual(result["files_matched"], 1)
        self.assertEqual(result["files_attached"], 1)
        self.dashed_study.refresh_from_db()
        self.assertTrue(self.dashed_study.results_file)

    def test_dashed_filename_with_no_match_skips_cleanly(self):
        """`999999-12345-NOBODY.pdf` for a non-existent study → counted as skipped, not error."""
        from apps.labwin_sync.ftp.mock import MockFTPConnector

        class UnmatchedFTP(MockFTPConnector):
            def list_pdf_files(self):
                return ["999999-12345-NOBODY.pdf"]

            def download_file(self, filename):
                return b"%PDF-1.4"

        with patch(
            "apps.labwin_sync.tasks.get_ftp_connector", return_value=UnmatchedFTP()
        ):
            result = fetch_ftp_pdfs(lab_client_id=1)

        self.assertEqual(result["files_skipped"], 1)
        self.assertEqual(result["files_attached"], 0)
        self.assertEqual(result["error_count"], 0)


# ======================
# is_pet_candidate / is_vet_practice / pet skipping
# ======================


class IsVetPracticeTests(BaseTestCase):
    """Tests for is_vet_practice keyword/code detection."""

    def test_code_starts_with_vet(self):
        self.assertTrue(is_vet_practice("VETAFO", "ACIDO FOLICO VETERINARIA"))
        self.assertTrue(is_vet_practice("VETBRH", "anything"))
        # Case-insensitive on code
        self.assertTrue(is_vet_practice("vetxxx", ""))

    def test_name_contains_veterinary_keyword(self):
        self.assertTrue(is_vet_practice("XYZ", "TIROXINA TOTAL veterinaria"))
        self.assertTrue(is_vet_practice("BBI-C", "BRUCELOSIS CANINA (IgG)"))
        self.assertTrue(is_vet_practice("CRE-F", "CREATININA EN FELINOS"))
        self.assertTrue(is_vet_practice("XYZ", "Ehrlichia canis PCR"))
        self.assertTrue(is_vet_practice("XYZ", "DIARREA VIRAL BOVINA"))

    def test_human_practice_is_not_vet(self):
        self.assertFalse(is_vet_practice("GLU", "Glucosa"))
        self.assertFalse(is_vet_practice("HEMC", "Hemograma Completo"))
        self.assertFalse(is_vet_practice("", ""))
        self.assertFalse(is_vet_practice(None, None))


class IsPetCandidateTests(BaseTestCase):
    """Tests for the combined pet-detection rule.

    Rule: dni == '' AND (last_name starts with '167' OR has_vet_practice).
    """

    # --- Signal 1: 167-prefix last_name ---
    def test_167_prefix_with_empty_dni_is_pet(self):
        self.assertTrue(is_pet_candidate("MIENDIETA", "167427", ""))
        self.assertTrue(is_pet_candidate("GINA", "167424", ""))
        self.assertTrue(is_pet_candidate("", "167023-CHINA", ""))  # dashed variant

    def test_167_prefix_but_has_dni_is_kept(self):
        # If patient has a DNI, treat as human even with 167 prefix
        self.assertFalse(is_pet_candidate("LUNA", "167000", "30123456"))

    # --- Signal 2: vet practice ---
    def test_vet_practice_with_empty_dni_is_pet(self):
        # Outside 167 range but has vet practice → pet
        self.assertTrue(is_pet_candidate("BIELA", "169154", "", has_vet_practice=True))
        self.assertTrue(is_pet_candidate("PAUL", "168685", "", has_vet_practice=True))

    def test_vet_practice_but_has_dni_is_kept(self):
        # DNI overrides — should never happen in real data, but guard anyway
        self.assertFalse(
            is_pet_candidate("LUNA", "200000", "30123456", has_vet_practice=True)
        )

    # --- Combined behavior ---
    def test_no_signals_is_kept(self):
        # Empty dni alone is NOT enough — needs a positive signal
        self.assertFalse(is_pet_candidate("LUNA", "200000", ""))
        self.assertFalse(is_pet_candidate("LUNA", "200000", "", has_vet_practice=False))

    def test_human_lastname_is_kept(self):
        self.assertFalse(is_pet_candidate("Maria", "Garcia", ""))
        self.assertFalse(
            is_pet_candidate("Maria", "Garcia", "", has_vet_practice=False)
        )

    def test_empty_inputs_are_kept(self):
        self.assertFalse(is_pet_candidate("", "", ""))
        self.assertFalse(is_pet_candidate(None, None, None))


class SyncSkipsPetsTests(BaseTestCase):
    """Sync should skip PACIENTES rows that match the combined pet rule."""

    def _inject_pet_fixtures(
        self, pet_numero, last_name="167400", abrev="GLU", practice_name=None
    ):
        """Helper: add a pet PACIENTES row + matching DETERS to mock fixtures.

        The default `last_name="167400"` triggers signal 1 (167-prefix).
        Override `abrev` + `practice_name` to also test signal 2 (vet practice).
        """
        from apps.labwin_sync.connectors.mock import (
            SAMPLE_DETERS,
            SAMPLE_NOMEN,
            SAMPLE_PACIENTES,
        )

        SAMPLE_PACIENTES[pet_numero] = {
            "NUMERO_FLD": pet_numero,
            "NOMBRE_FLD": f"{last_name},FALUCHO",  # parses to last={last_name} first=FALUCHO
            "HCLIN_FLD": "",  # no DNI
            "SEXO_FLD": 1,
            "FNACIM_FLD": "",
            "MUTUAL_FLD": 0,
            "MEDICO_FLD": "",
            "NUMMEDICO_FLD": 0,
            "CARNET_FLD": "",
            "TELEFONO_FLD": "",
            "CELULAR_FLD": "",
            "DIRECCION_FLD": "",
            "LOCALIDAD_FLD": "",
            "EMAIL_FLD": "",
            "DEBEBONO_FLD": "",
        }
        if practice_name and abrev not in SAMPLE_NOMEN:
            SAMPLE_NOMEN[abrev] = {
                "ABREV_FLD": abrev,
                "NOMBRE_FLD": practice_name,
                "SECCION_FLD": "",
                "DIASTARDA_FLD": 1,
                "MATERIAL_FLD": "",
            }
        SAMPLE_DETERS.append(
            {
                "NUMERO_FLD": pet_numero,
                "ABREV_FLD": abrev,
                "RESULT_FLD": "100",
                "RESULTREP_FLD": "100",
                "VALIDADO_FLD": "1",
                "FECHA_FLD": "20260415",
                "HORA_FLD": "10:00",
                "ORDEN_FLD": 1,
                "OPERADOR_FLD": "",
                "SUCURSAL_FLD": "",
            }
        )

    def _cleanup_pet_fixtures(self, pet_numero, abrev_added=None):
        from apps.labwin_sync.connectors.mock import (
            SAMPLE_DETERS,
            SAMPLE_NOMEN,
            SAMPLE_PACIENTES,
        )

        SAMPLE_PACIENTES.pop(pet_numero, None)
        SAMPLE_DETERS.pop()  # we just appended one
        if abrev_added:
            SAMPLE_NOMEN.pop(abrev_added, None)

    @override_settings(LABWIN_USE_MOCK=True)
    def test_pet_with_167_prefix_is_skipped(self):
        """Signal 1: last_name starts with '167' + empty DNI → skip."""
        pet_numero = 199001
        self._inject_pet_fixtures(pet_numero, last_name="167400")
        try:
            result = sync_labwin_results(lab_client_id=1, full_sync=True)
        finally:
            self._cleanup_pet_fixtures(pet_numero)

        self.assertFalse(
            User.objects.filter(first_name="FALUCHO", last_name="167400").exists(),
            "Pet with 167-prefix should have been skipped",
        )
        self.assertFalse(
            Study.objects.filter(protocol_number=f"LW-{pet_numero}").exists(),
            "Pet's study should not have been created",
        )
        self.assertEqual(result.get("pets_skipped", 0), 1)

    @override_settings(LABWIN_USE_MOCK=True)
    def test_pet_with_vet_practice_is_skipped(self):
        """Signal 2: last_name NOT 167-prefix but uses a vet practice → skip."""
        pet_numero = 199002
        # last_name='169500' is OUTSIDE the 167 range, but the practice is vet
        self._inject_pet_fixtures(
            pet_numero,
            last_name="169500",
            abrev="VETGLU",
            practice_name="GLUCOSA VETERINARIA",
        )
        try:
            result = sync_labwin_results(lab_client_id=1, full_sync=True)
        finally:
            self._cleanup_pet_fixtures(pet_numero, abrev_added="VETGLU")

        self.assertFalse(
            User.objects.filter(first_name="FALUCHO", last_name="169500").exists(),
            "Pet with vet practice should have been skipped",
        )
        self.assertFalse(
            Study.objects.filter(protocol_number=f"LW-{pet_numero}").exists(),
            "Pet's study should not have been created",
        )
        self.assertEqual(result.get("pets_skipped", 0), 1)

    @override_settings(LABWIN_USE_MOCK=True)
    def test_non_167_non_vet_no_dni_is_NOT_skipped(self):
        """Empty DNI alone is not enough: needs a positive signal."""
        pet_numero = 199003
        # last_name='180000' (not 167*) + practice GLU (not vet) + dni=''
        # → no pet signals → must be created (treated as a human with weird data)
        self._inject_pet_fixtures(pet_numero, last_name="180000")
        try:
            result = sync_labwin_results(lab_client_id=1, full_sync=True)
        finally:
            self._cleanup_pet_fixtures(pet_numero)

        self.assertTrue(
            User.objects.filter(first_name="FALUCHO", last_name="180000").exists(),
            "Patient with no pet signals should be created (no false positives)",
        )
        self.assertEqual(result.get("pets_skipped", 0), 0)

    @override_settings(LABWIN_USE_MOCK=True)
    def test_human_paciente_row_is_NOT_skipped(self):
        """A normal PACIENTES row (real human) should be imported normally."""
        # Mock fixtures already have 100001 (Garcia, Maria — clearly human).
        result = sync_labwin_results(lab_client_id=1, full_sync=True)

        self.assertTrue(
            User.objects.filter(first_name="Maria", last_name="Garcia").exists(),
            "Human patient should be created",
        )
        self.assertTrue(
            Study.objects.filter(protocol_number="LW-100001").exists(),
            "Human's study should be created",
        )
