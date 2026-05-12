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
    is_derivacion_doctor,
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
        # SEXO_FLD maps to biological_sex (NOT gender — sync must never
        # touch gender, which is patient-self-declared).
        self.assertEqual(result["biological_sex"], "F")
        self.assertNotIn("gender", result)
        self.assertEqual(result["birthday"], date(1985, 3, 15))
        self.assertEqual(result["mutual_code"], 1)
        self.assertEqual(result["carnet"], "ABC123")
        self.assertEqual(result["phone_number"], "11-2345-6789")
        self.assertEqual(result["direction"], "Av. Corrientes 1234")
        self.assertEqual(result["location"], "CABA")
        self.assertEqual(result["email"], "maria.garcia@test.com")
        self.assertEqual(result["role"], "patient")

    def test_male_biological_sex(self):
        row = SAMPLE_PACIENTES[100002]
        result = map_patient(row)
        self.assertEqual(result["biological_sex"], "M")
        self.assertNotIn("gender", result)

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

    def test_matricula_falls_back_to_matprov_when_matnac_empty(self):
        row = {
            "NUMERO_FLD": 1788,
            "NOMBRE_FLD": "Burre, Jorge E",
            "MATNAC_FLD": "",
            "MATPROV_FLD": "18305",
            "ESPECIALIDAD_FLD": "",
            "TELEFONO_FLD": "",
            "EMAIL_FLD": "",
        }
        result = map_doctor(row)
        self.assertEqual(result["matricula"], "18305")

    def test_matricula_falls_back_to_numero_when_both_empty(self):
        row = {
            "NUMERO_FLD": 1788,
            "NOMBRE_FLD": "Doe, Jane",
            "MATNAC_FLD": "",
            "MATPROV_FLD": "",
            "ESPECIALIDAD_FLD": "",
            "TELEFONO_FLD": "",
            "EMAIL_FLD": "",
        }
        result = map_doctor(row)
        self.assertEqual(result["matricula"], "1788")

    def test_matricula_prefers_matnac_over_matprov(self):
        row = {
            "NUMERO_FLD": 1788,
            "NOMBRE_FLD": "Doe, Jane",
            "MATNAC_FLD": "MN999",
            "MATPROV_FLD": "MP111",
            "ESPECIALIDAD_FLD": "",
            "TELEFONO_FLD": "",
            "EMAIL_FLD": "",
        }
        result = map_doctor(row)
        self.assertEqual(result["matricula"], "MN999")


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
            # As of 2026-05-08 the connector returns ALL DETERS rows
            # (validated + not). The sync layer decides per-protocol whether
            # to ingest based on is_protocol_fully_validated().
            self.assertEqual(len(all_rows), len(SAMPLE_DETERS))
            # And both flag values must be present in the dataset
            validado_values = {row["VALIDADO_FLD"] for row in all_rows}
            self.assertIn("1", validado_values)
            self.assertIn("0", validado_values)

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
# override this setting further.
@override_settings(LABWIN_SYNC_WINDOW_DAYS=10000)
class SyncTaskTests(BaseTestCase):
    """Integration tests for the sync_labwin_results task."""

    def test_sync_creates_records(self):
        """Full sync creates patients, doctors, practices, and studies."""
        from collections import defaultdict

        from apps.labwin_sync.connectors.mock import SAMPLE_PACIENTES
        from apps.labwin_sync.mappers import is_protocol_fully_validated, map_is_paid

        result = sync_labwin_results(lab_client_id=1, full_sync=True)

        self.assertGreater(result["studies_created"], 0)
        self.assertGreater(result["patients_created"], 0)
        self.assertGreater(result["practices_created"], 0)

        # Only protocols (NUMERO_FLD groups) where ALL rows are fully
        # validated AND loaded AND the patient does not owe a bono are
        # ingested. Compute the expected set the same way the sync does.
        rows_by_numero = defaultdict(list)
        for row in SAMPLE_DETERS:
            rows_by_numero[row["NUMERO_FLD"]].append(row)
        valid_numeros = {
            num
            for num, rows in rows_by_numero.items()
            if is_protocol_fully_validated(rows)
            and map_is_paid(SAMPLE_PACIENTES.get(num))
        }
        valid_rows = [r for r in SAMPLE_DETERS if r["NUMERO_FLD"] in valid_numeros]

        lw_studies = Study.objects.filter(protocol_number__startswith="LW-")
        self.assertEqual(lw_studies.count(), len(valid_numeros))

        # Verify StudyPractice records created (one per row in valid protocols)
        self.assertEqual(StudyPractice.objects.count(), len(valid_rows))

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
        # _get_or_create_patient now returns (pk, was_created); a falsy first
        # element makes the caller treat the patient as missing without raising.
        with patch(
            "apps.labwin_sync.tasks._get_or_create_patient",
            side_effect=[Exception("test error"), (None, False)],
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
        new_pk, needs_setup = _get_or_create_patient(pac_row, 1, sync_log, counters)

        self.assertIsNotNone(new_pk)
        # needs_password_setup=False because we couldn't save an email — no
        # password-setup link can be sent. The patient stays inactive,
        # waiting for DNI-revival or the QR/manual-claim flow.
        self.assertFalse(needs_setup)
        self.assertEqual(counters["patients_created"], 1)
        new_user = User.objects.get(pk=new_pk)
        self.assertIsNone(new_user.email)
        # Imported patients are inactive until they go through password setup.
        self.assertFalse(new_user.is_active)
        self.assertFalse(new_user.is_verified)
        # Names preserved in source casing (mapper doesn't titlecase)
        self.assertEqual(new_user.first_name.upper(), "MARIA")
        self.assertEqual(new_user.last_name.upper(), "GARCIA")


# ======================
# Sync Window Tests (rolling-window cursor behavior)
# ======================


class SyncWindowTests(BaseTestCase):
    """Tests for the date-window logic in sync_labwin_results.

    The task uses one setting: LABWIN_SYNC_WINDOW_DAYS. Every run (other
    than full_sync=True) re-imports DETERS where FECHA_FLD falls within
    today - LABWIN_SYNC_WINDOW_DAYS. This catches studies that were sampled
    weeks ago but only validated recently.
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

    @override_settings(LABWIN_SYNC_WINDOW_DAYS=90)
    def test_window_starts_n_days_ago(self):
        """Window cutoff is today - LABWIN_SYNC_WINDOW_DAYS."""
        captured, connector = self._capture_since_fecha()

        with patch("apps.labwin_sync.tasks.get_connector", return_value=connector):
            sync_labwin_results(lab_client_id=1, full_sync=False)

        expected = (date.today() - timedelta(days=90)).strftime("%Y%m%d")
        self.assertEqual(captured["since_fecha"], expected)
        self.assertEqual(captured["since_numero"], -1)

    @override_settings(LABWIN_SYNC_WINDOW_DAYS=30)
    def test_window_setting_is_honored(self):
        """Different LABWIN_SYNC_WINDOW_DAYS produces a different cutoff."""
        captured, connector = self._capture_since_fecha()

        with patch("apps.labwin_sync.tasks.get_connector", return_value=connector):
            sync_labwin_results(lab_client_id=1, full_sync=False)

        expected = (date.today() - timedelta(days=30)).strftime("%Y%m%d")
        self.assertEqual(captured["since_fecha"], expected)

    @override_settings(LABWIN_SYNC_WINDOW_DAYS=90)
    def test_window_independent_of_prior_sync(self):
        """The window is always 'today - N days', regardless of how far a
        prior sync got. last_synced_fecha is audit-only, not a cursor.

        This is the contract that makes late-validated studies (e.g. a
        2-month panel) get picked up: a sync today re-scans rows that the
        previous sync had already seen.
        """
        # Simulate an earlier successful sync that processed up to last week
        SyncLog.objects.create(
            status="completed",
            lab_client_id=1,
            last_synced_fecha=(date.today() - timedelta(days=7)).strftime("%Y%m%d"),
            last_synced_numero=999999,
        )

        captured, connector = self._capture_since_fecha()
        with patch("apps.labwin_sync.tasks.get_connector", return_value=connector):
            sync_labwin_results(lab_client_id=1, full_sync=False)

        # Window goes 90 days back, not 7 days back (previous cursor ignored)
        expected = (date.today() - timedelta(days=90)).strftime("%Y%m%d")
        self.assertEqual(captured["since_fecha"], expected)

    @override_settings(LABWIN_SYNC_WINDOW_DAYS=10000)
    def test_full_sync_bypasses_window(self):
        """full_sync=True skips the date filter entirely (since_fecha=None)."""
        captured, connector = self._capture_since_fecha()

        with patch("apps.labwin_sync.tasks.get_connector", return_value=connector):
            sync_labwin_results(lab_client_id=1, full_sync=True)

        self.assertIsNone(captured["since_fecha"])
        self.assertIsNone(captured["since_numero"])

    @override_settings(LABWIN_SYNC_WINDOW_DAYS=10000)
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
# Patient Notification Tests
# ======================


@override_settings(LABWIN_SYNC_WINDOW_DAYS=10000)
class SyncNotificationTests(BaseTestCase):
    """Patient notification dispatch from sync_labwin_results.

    Two flows:
      A. Existing User (matched by DNI or SyncedRecord) → studies-available email
      B. New User created from PACIENTES with email → password-setup email
      C. New User created from PACIENTES without email → no email, study stays
         unnotified (notification_sent_at=NULL) for a future retry.
    """

    def _patch_email_tasks(self):
        """Patch both email Celery tasks so we can assert on .delay calls
        without actually sending."""
        return (
            patch("apps.notifications.tasks.send_password_setup_email.delay"),
            patch("apps.notifications.tasks.send_studies_available_email.delay"),
        )

    def test_existing_user_gets_studies_available_email(self):
        """A patient who exists in Postgres before this sync (matched by DNI)
        receives a 'studies are available' email, not a password-setup one.

        The mock dataset has multiple patients; this asserts that THIS specific
        pre-existing patient ends up in the available-email branch, not the
        password-setup branch.
        """
        # Pre-existing patient with DNI matching SAMPLE_PACIENTES NUMERO=300001
        existing = self.create_patient(
            email="garcia@example.com",
            dni="30123456",
            lab_client_id=1,
        )

        password_patcher, available_patcher = self._patch_email_tasks()
        with password_patcher as mock_password, available_patcher as mock_available:
            sync_labwin_results(lab_client_id=1, full_sync=True)

        # Collect all user_ids each task was called with
        password_user_ids = {str(c.args[0]) for c in mock_password.call_args_list}
        available_user_ids = {str(c.args[0]) for c in mock_available.call_args_list}

        existing_pk = str(existing.pk)
        self.assertIn(
            existing_pk,
            available_user_ids,
            "Existing user should have received a studies-available email",
        )
        self.assertNotIn(
            existing_pk,
            password_user_ids,
            "Existing user should NOT have received a password-setup email",
        )

    def test_new_user_with_email_gets_password_setup(self):
        """A patient newly created from a PACIENTES row that has an email
        receives a password-setup email."""
        password_patcher, available_patcher = self._patch_email_tasks()
        with password_patcher as mock_password, available_patcher as mock_available:
            sync_labwin_results(lab_client_id=1, full_sync=True)

        # SAMPLE_PACIENTES has at least one row with EMAIL_FLD set; the new
        # user(s) created from those rows should get password setup.
        # mock_password is called per new user.
        self.assertGreater(
            mock_password.call_count,
            0,
            "Expected at least one password-setup email for new users with email",
        )

    def test_new_user_without_email_gets_nothing(self):
        """If a PACIENTES row has no email, no notification is queued AND
        the study's notification_sent_at stays NULL so we can retry later."""
        # Patch the mock connector to return a PACIENTES row with EMAIL_FLD=""
        # NUMMEDICO_FLD=501 ("Lopez, Juan") — a real doctor, so the derivación
        # filter doesn't preempt this test's emailless-patient path.
        emailless_pac = {
            "NUMERO_FLD": 999777,
            "NOMBRE_FLD": "SINMAIL, JUAN",
            "HCLIN_FLD": "11122233",
            "SEXO_FLD": 1,
            "FNACIM_FLD": "19800101",
            "MUTUAL_FLD": 0,
            "MEDICO_FLD": 0,
            "NUMMEDICO_FLD": 501,
            "CARNET_FLD": "",
            "TELEFONO_FLD": "",
            "CELULAR_FLD": "",
            "DIRECCION_FLD": "",
            "LOCALIDAD_FLD": "",
            "EMAIL_FLD": "",
            "DEBEBONO_FLD": "0",
        }
        emailless_deters = [
            {
                "NUMERO_FLD": 999777,
                "ABREV_FLD": "GLU-Bi",
                "RESULT_FLD": "100",
                "RESULTREP_FLD": "",
                "VALIDADO_FLD": "1",
                "CARGADO_FLD": "1",
                "FECHA_FLD": "20251028",
                "HORA_FLD": "10:00",
                "ORDEN_FLD": 1,
                "OPERADOR_FLD": "TEST",
                "SUCURSAL_FLD": 1,
            }
        ]

        with patch.object(
            MockLabWinConnector, "fetch_validated_deters"
        ) as mock_deters, patch.object(
            MockLabWinConnector, "fetch_pacientes"
        ) as mock_pac:
            mock_deters.return_value = iter([emailless_deters])
            mock_pac.return_value = {999777: emailless_pac}

            password_patcher, available_patcher = self._patch_email_tasks()
            with password_patcher as mock_password, available_patcher as mock_available:
                sync_labwin_results(lab_client_id=1, full_sync=True)

        # Patient has no email → neither task was called for this patient
        mock_password.assert_not_called()
        mock_available.assert_not_called()

        # Study was created but notification_sent_at stays NULL (will retry
        # next sync if the patient gets an email)
        study = Study.objects.filter(protocol_number="LW-999777").first()
        self.assertIsNotNone(study)
        self.assertIsNone(study.notification_sent_at)

    def test_resync_does_not_renotify(self):
        """The rolling 2-day window means we re-import yesterday's studies
        every night. notification_sent_at must prevent re-notifying the
        same patient about the same study."""
        password_patcher, available_patcher = self._patch_email_tasks()
        with password_patcher as mock_password_1, available_patcher as mock_available_1:
            sync_labwin_results(lab_client_id=1, full_sync=True)

        first_password_count = mock_password_1.call_count
        first_available_count = mock_available_1.call_count
        self.assertGreater(
            first_password_count + first_available_count,
            0,
            "First sync should have notified at least one patient",
        )

        # Re-sync — every study now has notification_sent_at set
        with password_patcher as mock_password_2, available_patcher as mock_available_2:
            sync_labwin_results(lab_client_id=1, full_sync=True)

        self.assertEqual(
            mock_password_2.call_count,
            0,
            "Re-sync should NOT re-send password-setup emails",
        )
        self.assertEqual(
            mock_available_2.call_count,
            0,
            "Re-sync should NOT re-send studies-available emails",
        )

    def test_batch_one_email_per_patient(self):
        """A patient with N new studies in one sync run gets ONE email,
        not N. The batched send_studies_available_email task is called
        once per user with all study_ids."""
        # Pre-existing patient who will match by DNI to multiple PACIENTES
        # rows. SAMPLE_DETERS has 3 NUMEROs (100001, 100002, 100003); the
        # PACIENTES rows for them have different DNIs by default. We need
        # to make all three resolve to one existing User.
        existing = self.create_patient(
            email="multi@example.com",
            dni="30123456",
            lab_client_id=1,
        )

        # Patch fetch_pacientes so that all NUMEROs map to the SAME DNI,
        # and force DEBEBONO_FLD='0' so the unpaid gate doesn't skip them
        # (100002 is unpaid in the fixture). Also flip 100003's DETERS rows
        # to fully-validated so the partial-validation gate doesn't skip it
        # — this test cares only about email batching.
        from apps.labwin_sync.connectors.mock import SAMPLE_DETERS

        deters_snapshot = []
        for row in SAMPLE_DETERS:
            if row["NUMERO_FLD"] == 100003:
                deters_snapshot.append(
                    (row["ABREV_FLD"], row["VALIDADO_FLD"], row["CARGADO_FLD"])
                )
                row["VALIDADO_FLD"] = "1"
                row["CARGADO_FLD"] = "1"

        try:
            with patch.object(MockLabWinConnector, "fetch_pacientes") as mock_pac:

                def _all_same_dni(numeros):
                    from apps.labwin_sync.connectors.mock import SAMPLE_PACIENTES as _SP

                    result = {}
                    for n in numeros:
                        base = _SP.get(n)
                        if base:
                            row = dict(base)
                            row["HCLIN_FLD"] = "30123456"
                            row["EMAIL_FLD"] = "multi@example.com"
                            row["DEBEBONO_FLD"] = "0"  # bypass unpaid gate
                            result[n] = row
                    return result

                mock_pac.side_effect = _all_same_dni

                password_patcher, available_patcher = self._patch_email_tasks()
                with password_patcher as mock_password, available_patcher as mock_available:
                    sync_labwin_results(lab_client_id=1, full_sync=True)
        finally:
            for abrev, validado, cargado in deters_snapshot:
                for row in SAMPLE_DETERS:
                    if row["NUMERO_FLD"] == 100003 and row["ABREV_FLD"] == abrev:
                        row["VALIDADO_FLD"] = validado
                        row["CARGADO_FLD"] = cargado

        # Existing user was already created; should get studies-available
        # called exactly once with N study_ids in the list.
        self.assertEqual(
            mock_available.call_count,
            1,
            f"Expected exactly 1 batched email for the patient, got {mock_available.call_count}",
        )
        args, _ = mock_available.call_args
        # args = (user_id_str, [study_id_str, ...])
        self.assertEqual(str(args[0]), str(existing.pk))
        self.assertGreater(len(args[1]), 1, "Expected multiple study_ids in the batch")


# ======================
# Patient Activation Tests
# ======================


@override_settings(LABWIN_SYNC_WINDOW_DAYS=10000)
class PatientActivationTests(BaseTestCase):
    """End-to-end activation contract for LabWin-imported patients.

    Imported patients start is_active=False, is_verified=False (and have
    no allauth EmailAddress row). They activate themselves via the
    password-setup endpoint (`/api/v1/users/set-password/`), which flips
    both flags and creates the EmailAddress.

    These tests cover the full lifecycle:
      1. Sync creates an inactive user
      2. SetPasswordView activates them + creates EmailAddress
      3. Login is gated correctly (works after, blocked before)
      4. DNI revival: existing email-less user gets an email via a later sync
    """

    def test_imported_patient_with_email_is_inactive(self):
        """Sync creates new patient with email — they should be is_active=False
        and is_verified=False until they set their password."""
        sync_labwin_results(lab_client_id=1, full_sync=True)

        # SAMPLE_PACIENTES has at least one row with EMAIL_FLD set; pick one
        # of the new users by checking SyncedRecord.
        synced_user = (
            User.objects.filter(role="patient", lab_client_id=1)
            .exclude(email__isnull=True)
            .first()
        )
        self.assertIsNotNone(synced_user)
        self.assertFalse(synced_user.is_active)
        self.assertFalse(synced_user.is_verified)

    def test_imported_patient_without_email_is_inactive(self):
        """Same contract for emailless patients — they're created inactive
        and stay that way until DNI revival or QR claim."""
        # Patch fetch_pacientes so the user mapped to NUMERO=100001 (which
        # has DETERS rows in the mock) has no email.
        emailless_pac = {
            100001: {
                "NUMERO_FLD": 100001,
                "NOMBRE_FLD": "TESTUSER, NOEMAIL",
                "HCLIN_FLD": "11122233",
                "SEXO_FLD": 1,
                "FNACIM_FLD": "19800101",
                "MUTUAL_FLD": 0,
                "MEDICO_FLD": 0,
                # 501 = "Lopez, Juan" in SAMPLE_MEDICOS — a real doctor, so the
                # derivación filter doesn't skip this protocol.
                "NUMMEDICO_FLD": 501,
                "CARNET_FLD": "",
                "TELEFONO_FLD": "",
                "CELULAR_FLD": "",
                "DIRECCION_FLD": "",
                "LOCALIDAD_FLD": "",
                "EMAIL_FLD": "",  # No email
                "DEBEBONO_FLD": "0",
            },
        }

        with patch.object(MockLabWinConnector, "fetch_pacientes") as mock_pac:
            mock_pac.return_value = emailless_pac
            sync_labwin_results(lab_client_id=1, full_sync=True)

        user = User.objects.filter(dni="11122233").first()
        self.assertIsNotNone(user)
        self.assertIsNone(user.email)
        self.assertFalse(user.is_active)
        self.assertFalse(user.is_verified)

    def test_set_password_activates_user_and_creates_emailaddress(self):
        """The set-password endpoint flips both flags AND writes the allauth
        EmailAddress row. Without that row, allauth can't authenticate even
        if User.email/password are set."""
        from allauth.account.models import EmailAddress
        from rest_framework.test import APIClient

        # Import a patient and verify they're inactive
        sync_labwin_results(lab_client_id=1, full_sync=True)
        user = (
            User.objects.filter(role="patient", lab_client_id=1)
            .exclude(email__isnull=True)
            .first()
        )
        self.assertFalse(user.is_active)
        self.assertFalse(EmailAddress.objects.filter(user=user).exists())

        # Generate a verification token (same flow as the email task)
        token = user.generate_verification_token()

        # Hit the set-password endpoint
        client = APIClient()
        response = client.post(
            "/api/v1/users/set-password/",
            {
                "email": user.email,
                "token": token,
                "password": "NewSecurePass123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)

        user.refresh_from_db()
        self.assertTrue(user.is_active, "user should be activated")
        self.assertTrue(user.is_verified, "user should be verified")
        self.assertTrue(
            EmailAddress.objects.filter(
                user=user, verified=True, primary=True
            ).exists(),
            "allauth EmailAddress row must exist after set-password",
        )
        # Token cleared
        self.assertIsNone(user.verification_token)

    def test_set_password_works_when_user_starts_unverified(self):
        """Confirm the endpoint doesn't gate on is_verified=True — that's
        the whole point of the flow for imported patients."""
        from rest_framework.test import APIClient

        # Manually create an inactive, unverified user
        user = User.objects.create_user(
            email="inactive@example.com",
            first_name="In",
            last_name="Active",
            role="patient",
            lab_client_id=1,
            is_active=False,
            is_verified=False,
        )
        token = user.generate_verification_token()

        client = APIClient()
        response = client.post(
            "/api/v1/users/set-password/",
            {"email": user.email, "token": token, "password": "Pass123456!"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_verified)

    def test_dni_revival_when_existing_emailless_user_gets_email(self):
        """If a user exists with the right DNI but no email, and a later
        PACIENTES row brings an email, the sync writes the email and routes
        them through password-setup (so they'll get an activation email)."""
        # Pre-create an inactive user with DNI but no email
        existing = self.create_patient(
            email=None,
            dni="30123456",
            lab_client_id=1,
            is_active=False,
            is_verified=False,
        )
        self.assertIsNone(existing.email)

        # Patch the mock connector so PACIENTES NUMERO=100001 (which has
        # DNI 30123456 in the sample data and DETERS rows referencing it)
        # brings an email.
        from apps.labwin_sync.connectors.mock import SAMPLE_PACIENTES as _SP

        revived_pac = dict(_SP[100001])
        revived_pac["EMAIL_FLD"] = "newly-arrived@example.com"

        with patch.object(MockLabWinConnector, "fetch_pacientes") as mock_pac:
            mock_pac.return_value = {100001: revived_pac}

            password_patcher = patch(
                "apps.notifications.tasks.send_password_setup_email.delay"
            )
            available_patcher = patch(
                "apps.notifications.tasks.send_studies_available_email.delay"
            )
            with password_patcher as mock_password, available_patcher as mock_available:
                sync_labwin_results(lab_client_id=1, full_sync=True)

        # The existing user's email was written
        existing.refresh_from_db()
        self.assertEqual(existing.email, "newly-arrived@example.com")
        # And they were routed through password-setup, not studies-available
        password_user_ids = {str(c.args[0]) for c in mock_password.call_args_list}
        available_user_ids = {str(c.args[0]) for c in mock_available.call_args_list}
        self.assertIn(str(existing.pk), password_user_ids)
        self.assertNotIn(str(existing.pk), available_user_ids)

    def test_login_blocked_before_set_password(self):
        """An imported, still-inactive patient cannot log in — Django auth
        rejects is_active=False users."""
        from rest_framework.test import APIClient

        user = User.objects.create_user(
            email="blocked@example.com",
            first_name="Blocked",
            last_name="User",
            role="patient",
            lab_client_id=1,
            is_active=False,
            is_verified=False,
            password="SomePass123!",
        )
        # Manually create an EmailAddress so we're testing is_active gate
        # in isolation (not the missing-EmailAddress one)
        from allauth.account.models import EmailAddress

        EmailAddress.objects.create(
            user=user, email=user.email, primary=True, verified=False
        )

        client = APIClient()
        response = client.post(
            "/api/v1/auth/login/",
            {"email": user.email, "password": "SomePass123!"},
            format="json",
        )
        # Should fail; exact code is 400 or 401 depending on the auth backend
        self.assertIn(response.status_code, (400, 401, 403))


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


class CleanupFTPPDFsFilenameParsingTests(BaseTestCase):
    """Regression tests for cleanup_ftp_pdfs filename parsing.

    Pre-2026-05-11 the task passed `os.path.splitext(filename)[0]` directly
    to `Study.objects.filter(sample_id=...)`. For dashed filenames like
    `220197-39592918-SIRI,FRANCO.pdf` that meant looking up
    `sample_id="220197-39592918-SIRI,FRANCO"` — never matched, so
    files_deleted was 0 every Sunday and PDFs accumulated forever on FTP
    (4,057 files seen in prod on 2026-05-11). The fix mirrors the parser
    used in fetch_ftp_pdfs: take the first dash-separated segment.
    """

    def setUp(self):
        super().setUp()
        self.patient = self.create_patient()

    def _make_study_with_pdf(self, sample_id):
        """Create a study whose results_file is a real (tiny) file on disk.

        The cleanup task checks `if study and study.results_file:`, which
        on a FileField evaluates to True only when the descriptor has a
        non-empty `.name`. Assigning a bare string path via
        `study.results_file = "..."` does NOT set this reliably across
        Django versions, hence the explicit ContentFile.save() below.
        """
        from django.core.files.base import ContentFile

        study = self.create_study(self.patient, practice=self.create_practice())
        study.sample_id = sample_id
        study.lab_client_id = 1
        study.results_file.save(
            f"{sample_id}.pdf",
            ContentFile(b"%PDF-1.4 test"),
            save=True,
        )
        return study

    def _make_study_without_pdf(self, sample_id):
        study = self.create_study(self.patient, practice=self.create_practice())
        study.sample_id = sample_id
        study.lab_client_id = 1
        study.save()
        return study

    def test_dashed_filename_is_deleted_when_study_has_results_file(self):
        """Cleanup parses NUMERO from `{NUMERO}-{DNI}-{NAME}.pdf` and deletes it."""
        self._make_study_with_pdf("220197")

        # Inject the dashed file into the mock's `files` dict so that
        # MockFTPConnector.delete_file (which checks membership) actually
        # finds it. Overriding list_pdf_files alone isn't enough — the
        # base class's delete_file raises FileNotFoundError otherwise.
        mock_ftp = MockFTPConnector(
            files={"220197-39592918-SIRI,FRANCO.pdf": b"%PDF-1.4 mock"}
        )
        with patch(
            "apps.labwin_sync.tasks.get_ftp_connector",
            return_value=mock_ftp,
        ):
            result = cleanup_ftp_pdfs(lab_client_id=1)

        self.assertEqual(result["files_deleted"], 1)
        self.assertEqual(result["files_kept"], 0)
        self.assertIn("220197-39592918-SIRI,FRANCO.pdf", mock_ftp._deleted)

    def test_dashed_filename_is_kept_when_study_has_no_results_file(self):
        """A dashed filename whose Study exists but lacks results_file is kept."""
        self._make_study_without_pdf("220197")

        mock_ftp = MockFTPConnector(
            files={"220197-39592918-SIRI,FRANCO.pdf": b"%PDF-1.4 mock"}
        )
        with patch(
            "apps.labwin_sync.tasks.get_ftp_connector",
            return_value=mock_ftp,
        ):
            result = cleanup_ftp_pdfs(lab_client_id=1)

        self.assertEqual(result["files_deleted"], 0)
        self.assertEqual(result["files_kept"], 1)

    def test_legacy_filename_format_still_works(self):
        """`100001.pdf` (no dashes) still parses as NUMERO=100001."""
        self._make_study_with_pdf("100001")

        mock_ftp = MockFTPConnector(files={"100001.pdf": b"%PDF-1.4 mock"})
        with patch(
            "apps.labwin_sync.tasks.get_ftp_connector",
            return_value=mock_ftp,
        ):
            result = cleanup_ftp_pdfs(lab_client_id=1)

        self.assertEqual(result["files_deleted"], 1)
        self.assertIn("100001.pdf", mock_ftp._deleted)

    def test_dashed_filename_with_no_matching_study_is_kept(self):
        """Unknown NUMERO in a dashed filename is counted as kept, not error."""
        mock_ftp = MockFTPConnector(files={"999999-12345-NOBODY.pdf": b"%PDF-1.4 mock"})
        with patch(
            "apps.labwin_sync.tasks.get_ftp_connector",
            return_value=mock_ftp,
        ):
            result = cleanup_ftp_pdfs(lab_client_id=1)

        self.assertEqual(result["files_deleted"], 0)
        self.assertEqual(result["files_kept"], 1)
        self.assertEqual(result["error_count"], 0)


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

    @patch("apps.labwin_sync.services.backup_import.BackupImporter.trigger_sync")
    @patch("apps.labwin_sync.services.backup_import.BackupImporter.restore_to_firebird")
    def test_run_persists_backup_filename_to_synclog(self, mock_restore, mock_sync):
        backup = _make_fake_backup(self.incoming)
        mock_sync.return_value = {"message": "Sync OK"}

        self._importer().run()

        log = SyncLog.objects.latest("started_at")
        self.assertEqual(log.backup_filename, backup.name)

    @patch("apps.labwin_sync.services.backup_import.BackupImporter.trigger_sync")
    @patch("apps.labwin_sync.services.backup_import.BackupImporter.restore_to_firebird")
    def test_dedup_skips_already_imported_backup(self, mock_restore, mock_sync):
        """A second run against the same filename returns 'skipped' without
        calling restore or sync."""
        backup = _make_fake_backup(self.incoming)
        mock_sync.return_value = {"message": "Sync OK"}

        # First run — should succeed normally
        result1 = self._importer().run()
        self.assertEqual(result1.status, "completed")
        mock_restore.assert_called_once()
        mock_sync.assert_called_once()

        # Re-create the same-named file in incoming/ (simulating the lab
        # uploading the same backup twice)
        _make_fake_backup(self.incoming, name=backup.name)
        mock_restore.reset_mock()
        mock_sync.reset_mock()

        # Second run — must skip
        result2 = self._importer().run()

        self.assertEqual(result2.status, "skipped")
        self.assertIn("already imported", result2.error)
        mock_restore.assert_not_called()
        mock_sync.assert_not_called()
        # File still moved out of incoming/ so we don't keep re-checking
        self.assertEqual(len(list(self.incoming.glob("*.fbk.gz"))), 0)

    @patch("apps.labwin_sync.services.backup_import.BackupImporter.trigger_sync")
    @patch("apps.labwin_sync.services.backup_import.BackupImporter.restore_to_firebird")
    def test_dedup_does_not_skip_when_prior_run_failed(self, mock_restore, mock_sync):
        """A previous FAILED SyncLog with the same filename shouldn't block a
        retry — the lab's upload may have been corrupt and re-uploaded."""
        # Pre-seed a failed SyncLog for this filename
        SyncLog.objects.create(
            status="failed",
            backup_filename="BASEDAT_20260424.fbk.gz",
            lab_client_id=1,
            error_count=1,
        )
        _make_fake_backup(self.incoming)
        mock_sync.return_value = {"message": "Sync OK"}

        result = self._importer().run()

        self.assertEqual(result.status, "completed")
        mock_restore.assert_called_once()

    @patch("apps.labwin_sync.services.backup_import.BackupImporter.trigger_sync")
    @patch("apps.labwin_sync.services.backup_import.BackupImporter.restore_to_firebird")
    def test_dedup_skipped_synclog_is_completed_not_failed(
        self, mock_restore, mock_sync
    ):
        """The SyncLog row created during a 'skipped' run should have
        status=completed (it's a successful no-op, not a failure)."""
        backup = _make_fake_backup(self.incoming)
        mock_sync.return_value = {"message": "Sync OK"}
        self._importer().run()  # First run → completed

        _make_fake_backup(self.incoming, name=backup.name)
        before = SyncLog.objects.count()
        self._importer().run()  # Second run → skipped
        after = SyncLog.objects.count()

        self.assertEqual(after, before + 1)
        latest = SyncLog.objects.latest("started_at")
        self.assertEqual(latest.status, "completed")
        self.assertEqual(latest.error_count, 0)


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


class SyncIsValidatedTests(BaseTestCase):
    """End-to-end: every sync-ingested Study is is_validated=True.

    Note: there is no equivalent test for is_paid because the sync gate
    skips DEBEBONO_FLD='1' protocols at import time (see
    SyncSkipsUnpaidProtocolsTests). Every sync-ingested Study is therefore
    is_paid=True by construction, so a fixture-based assertion would be
    tautological. The model-level mapping is covered by MapIsPaidTests.
    """

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


class IsDerivacionDoctorTests(BaseTestCase):
    """Unit tests for the no-doctor / Sin Consigna sentinel filter."""

    def test_zero_is_derivacion(self):
        self.assertTrue(is_derivacion_doctor(0))

    def test_none_is_derivacion(self):
        self.assertTrue(is_derivacion_doctor(None))

    def test_empty_string_is_derivacion(self):
        self.assertTrue(is_derivacion_doctor(""))
        self.assertTrue(is_derivacion_doctor("0"))

    def test_sentinel_id_175_is_derivacion(self):
        # 175 is the current "No Consigna" row in MEDICOS (verified against prod)
        self.assertTrue(is_derivacion_doctor(175))

    def test_sentinel_by_name_no_consigna(self):
        # Defense-in-depth: even if the ID changes, name-match should catch it
        medico = {"NUMERO_FLD": 999, "NOMBRE_FLD": "No Consigna", "MATNAC_FLD": ""}
        self.assertTrue(is_derivacion_doctor(999, medico))

    def test_sentinel_by_name_sin_consigna(self):
        medico = {"NUMERO_FLD": 999, "NOMBRE_FLD": "Sin Consigna", "MATNAC_FLD": ""}
        self.assertTrue(is_derivacion_doctor(999, medico))

    def test_sentinel_by_name_case_insensitive(self):
        medico = {"NUMERO_FLD": 999, "NOMBRE_FLD": "NO CONSIGNA", "MATNAC_FLD": ""}
        self.assertTrue(is_derivacion_doctor(999, medico))

    def test_real_doctor_id_is_kept(self):
        self.assertFalse(is_derivacion_doctor(501))
        self.assertFalse(is_derivacion_doctor(2))
        self.assertFalse(is_derivacion_doctor(128))

    def test_real_doctor_with_row_is_kept(self):
        medico = {"NUMERO_FLD": 501, "NOMBRE_FLD": "Lopez, Juan", "MATNAC_FLD": "MN1"}
        self.assertFalse(is_derivacion_doctor(501, medico))


class SyncSkipsDerivacionTests(BaseTestCase):
    """Integration: sync should skip protocols whose patient has no real doctor."""

    def _inject_derivacion_fixtures(self, numero, num_medico):
        """Helper: add a PACIENTES row pointing at a no-doctor sentinel."""
        from apps.labwin_sync.connectors.mock import (
            SAMPLE_DETERS,
            SAMPLE_MEDICOS,
            SAMPLE_PACIENTES,
        )

        # If we're using NUMMEDICO=175 (the sentinel), inject a matching
        # MEDICOS row so the lookup resolves (mirrors prod behavior).
        if num_medico == 175 and 175 not in SAMPLE_MEDICOS:
            SAMPLE_MEDICOS[175] = {
                "NUMERO_FLD": 175,
                "NOMBRE_FLD": "No Consigna",
                "MATNAC_FLD": "",
                "MATPROV_FLD": "",
                "ESPECIALIDAD_FLD": "",
                "TELEFONO_FLD": "",
                "EMAIL_FLD": "",
            }

        SAMPLE_PACIENTES[numero] = {
            "NUMERO_FLD": numero,
            "NOMBRE_FLD": "Walkin,Juan",
            "HCLIN_FLD": "30123456",  # has DNI — definitely human
            "SEXO_FLD": 1,
            "FNACIM_FLD": "",
            "MUTUAL_FLD": 0,
            "MEDICO_FLD": "",
            "NUMMEDICO_FLD": num_medico,
            "CARNET_FLD": "",
            "TELEFONO_FLD": "",
            "CELULAR_FLD": "",
            "DIRECCION_FLD": "",
            "LOCALIDAD_FLD": "",
            "EMAIL_FLD": "",
            "DEBEBONO_FLD": "",
        }
        SAMPLE_DETERS.append(
            {
                "NUMERO_FLD": numero,
                "ABREV_FLD": "GLU-Bi",  # human practice, fixture exists
                "RESULT_FLD": "100",
                "RESULTREP_FLD": "100",
                "VALIDADO_FLD": "1",
                "CARGADO_FLD": "1",
                "FECHA_FLD": "20260415",
                "HORA_FLD": "10:00",
                "ORDEN_FLD": 1,
                "OPERADOR_FLD": "",
                "SUCURSAL_FLD": "",
            }
        )

    def _cleanup(self, numero, cleanup_175=False):
        from apps.labwin_sync.connectors.mock import (
            SAMPLE_DETERS,
            SAMPLE_MEDICOS,
            SAMPLE_PACIENTES,
        )

        SAMPLE_PACIENTES.pop(numero, None)
        SAMPLE_DETERS.pop()
        if cleanup_175:
            SAMPLE_MEDICOS.pop(175, None)

    @override_settings(LABWIN_USE_MOCK=True)
    def test_protocol_with_nummedico_zero_is_skipped(self):
        protocol = 199101
        self._inject_derivacion_fixtures(protocol, num_medico=0)
        try:
            result = sync_labwin_results(lab_client_id=1, full_sync=True)
        finally:
            self._cleanup(protocol)

        self.assertFalse(
            Study.objects.filter(protocol_number=f"LW-{protocol}").exists(),
            "Protocol with NUMMEDICO_FLD=0 should be skipped",
        )
        self.assertFalse(
            User.objects.filter(first_name="Juan", last_name="Walkin").exists(),
            "Patient for a derivación-only protocol should not be created",
        )
        self.assertEqual(result.get("derivacion_skipped", 0), 1)

    @override_settings(LABWIN_USE_MOCK=True)
    def test_protocol_with_no_consigna_sentinel_id_is_skipped(self):
        protocol = 199102
        self._inject_derivacion_fixtures(protocol, num_medico=175)
        try:
            result = sync_labwin_results(lab_client_id=1, full_sync=True)
        finally:
            self._cleanup(protocol, cleanup_175=True)

        self.assertFalse(
            Study.objects.filter(protocol_number=f"LW-{protocol}").exists(),
            "Protocol pointing at NUMERO=175 (No Consigna) should be skipped",
        )
        self.assertEqual(result.get("derivacion_skipped", 0), 1)

    @override_settings(LABWIN_USE_MOCK=True)
    def test_protocol_with_real_doctor_is_kept(self):
        """Sanity: a normal patient with NUMMEDICO_FLD=501 (Lopez, Juan) still imports."""
        protocol = 199103
        self._inject_derivacion_fixtures(protocol, num_medico=501)
        try:
            result = sync_labwin_results(lab_client_id=1, full_sync=True)
        finally:
            self._cleanup(protocol)

        self.assertTrue(
            Study.objects.filter(protocol_number=f"LW-{protocol}").exists(),
            "Protocol with a real doctor should be created normally",
        )
        self.assertEqual(result.get("derivacion_skipped", 0), 0)

    @override_settings(LABWIN_USE_MOCK=True)
    def test_derivacion_skipped_counter_persists_to_synclog(self):
        protocol = 199104
        self._inject_derivacion_fixtures(protocol, num_medico=0)
        try:
            sync_labwin_results(lab_client_id=1, full_sync=True)
        finally:
            self._cleanup(protocol)

        latest = SyncLog.objects.order_by("-started_at").first()
        self.assertIsNotNone(latest)
        self.assertGreaterEqual(latest.derivacion_skipped, 1)


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
            # Use a real doctor (501) so this fixture exercises the
            # pet-detection path specifically. Without a real doctor the
            # derivación filter catches the protocol first and these tests
            # would be testing the wrong thing.
            "NUMMEDICO_FLD": 501,
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
                "CARGADO_FLD": "1",
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


# ======================
# DISABLE_PATIENT_EMAILS kill-switch
# ======================


class DisablePatientEmailsTests(BaseTestCase):
    """Test-mode kill switch for patient-facing emails.

    When DISABLE_PATIENT_EMAILS=True the sync still marks studies as
    notified (so they don't re-queue every run) but neither
    send_password_setup_email nor send_studies_available_email is called.
    """

    def _patch_email_tasks(self):
        return (
            patch("apps.notifications.tasks.send_password_setup_email.delay"),
            patch("apps.notifications.tasks.send_studies_available_email.delay"),
        )

    @override_settings(DISABLE_PATIENT_EMAILS=True)
    def test_no_emails_sent_when_flag_on(self):
        # Pre-existing patient that would normally trigger
        # studies_available, plus the mock dataset has emailful new patients
        # that would normally trigger password_setup. Both must be silenced.
        self.create_patient(
            email="garcia@example.com",
            dni="30123456",
            lab_client_id=1,
        )

        password_patcher, available_patcher = self._patch_email_tasks()
        with password_patcher as mock_password, available_patcher as mock_available:
            sync_labwin_results(lab_client_id=1, full_sync=True)

        mock_password.assert_not_called()
        mock_available.assert_not_called()

    @override_settings(DISABLE_PATIENT_EMAILS=True)
    def test_studies_still_marked_notified(self):
        # Without the notification_sent_at update the rolling window would
        # re-queue these forever. The flag preserves that mark so test runs
        # don't accumulate phantom backlog.
        self.create_patient(
            email="garcia@example.com",
            dni="30123456",
            lab_client_id=1,
        )

        password_patcher, available_patcher = self._patch_email_tasks()
        with password_patcher, available_patcher:
            sync_labwin_results(lab_client_id=1, full_sync=True)

        # Studies belonging to patients that had an email should have
        # notification_sent_at set even though no email was queued.
        any_marked = Study.objects.filter(notification_sent_at__isnull=False).exists()
        self.assertTrue(
            any_marked,
            "DISABLE_PATIENT_EMAILS must still mark studies as notified",
        )

    @override_settings(DISABLE_PATIENT_EMAILS=True)
    def test_emails_skipped_counter_persists_to_synclog(self):
        self.create_patient(
            email="garcia@example.com",
            dni="30123456",
            lab_client_id=1,
        )

        password_patcher, available_patcher = self._patch_email_tasks()
        with password_patcher, available_patcher:
            sync_labwin_results(lab_client_id=1, full_sync=True)

        log = SyncLog.objects.order_by("-started_at").first()
        self.assertIsNotNone(log)
        self.assertGreater(
            log.emails_skipped,
            0,
            "emails_skipped counter must reflect the kill-switch skips",
        )
        self.assertEqual(
            log.notifications_queued,
            0,
            "Nothing should have been queued when the flag is on",
        )


class PatientEmailAllowlistTests(BaseTestCase):
    """PATIENT_EMAIL_ALLOWLIST_DOMAINS bypasses DISABLE_PATIENT_EMAILS.

    Used to let lab staff test the patient-facing flow with their own
    @labmolecular.com.ar accounts while real patients stay paused.
    """

    def _build_inputs(self, email):
        """Create a patient + a study and return the dict shape that
        _dispatch_patient_notifications consumes. Avoids running a full
        sync_labwin_results so the test is focused on the dispatcher."""
        patient = self.create_patient(
            email=email,
            dni="30123456",
            lab_client_id=1,
        )
        practice = self.create_practice()
        study = self.create_study(patient, practice=practice)
        return {patient.pk: [study.pk]}, set()

    @override_settings(
        DISABLE_PATIENT_EMAILS=True,
        PATIENT_EMAIL_ALLOWLIST_DOMAINS=["labmolecular.com.ar"],
    )
    def test_allowlisted_domain_bypasses_kill_switch(self):
        """Lab @labmolecular.com.ar account: email is queued despite the kill switch."""
        from apps.labwin_sync.tasks import _dispatch_patient_notifications

        studies, password_users = self._build_inputs("staff@labmolecular.com.ar")

        with patch(
            "apps.notifications.tasks.send_studies_available_email.delay"
        ) as mock_available:
            queued, skipped = _dispatch_patient_notifications(studies, password_users)

        mock_available.assert_called_once()
        self.assertEqual(queued, 1)
        self.assertEqual(skipped, 0)

    @override_settings(
        DISABLE_PATIENT_EMAILS=True,
        PATIENT_EMAIL_ALLOWLIST_DOMAINS=["labmolecular.com.ar"],
    )
    def test_non_allowlisted_domain_still_skipped(self):
        """Real patient on gmail: still respects the kill switch."""
        from apps.labwin_sync.tasks import _dispatch_patient_notifications

        studies, password_users = self._build_inputs("juan@gmail.com")

        with patch(
            "apps.notifications.tasks.send_studies_available_email.delay"
        ) as mock_available:
            queued, skipped = _dispatch_patient_notifications(studies, password_users)

        mock_available.assert_not_called()
        self.assertEqual(queued, 0)
        self.assertEqual(skipped, 1)

    @override_settings(
        DISABLE_PATIENT_EMAILS=True,
        PATIENT_EMAIL_ALLOWLIST_DOMAINS=["labmolecular.com.ar"],
    )
    def test_allowlist_match_is_case_insensitive(self):
        """Mixed-case email in the user record still hits the allowlist."""
        from apps.labwin_sync.tasks import _dispatch_patient_notifications

        studies, password_users = self._build_inputs("Staff@LabMolecular.COM.AR")

        with patch(
            "apps.notifications.tasks.send_studies_available_email.delay"
        ) as mock_available:
            queued, skipped = _dispatch_patient_notifications(studies, password_users)

        mock_available.assert_called_once()
        self.assertEqual(queued, 1)

    @override_settings(
        DISABLE_PATIENT_EMAILS=True,
        PATIENT_EMAIL_ALLOWLIST_DOMAINS=[],
    )
    def test_empty_allowlist_preserves_existing_kill_switch_behaviour(self):
        """Empty list = the original behaviour. Even @labmolecular.com.ar gets skipped."""
        from apps.labwin_sync.tasks import _dispatch_patient_notifications

        studies, password_users = self._build_inputs("staff@labmolecular.com.ar")

        with patch(
            "apps.notifications.tasks.send_studies_available_email.delay"
        ) as mock_available:
            queued, skipped = _dispatch_patient_notifications(studies, password_users)

        mock_available.assert_not_called()
        self.assertEqual(queued, 0)
        self.assertEqual(skipped, 1)

    @override_settings(
        DISABLE_PATIENT_EMAILS=False,
        PATIENT_EMAIL_ALLOWLIST_DOMAINS=["labmolecular.com.ar"],
    )
    def test_non_allowlisted_emails_unaffected_when_kill_switch_off(self):
        """When the kill switch is OFF, the allowlist is a no-op — everyone gets emails."""
        from apps.labwin_sync.tasks import _dispatch_patient_notifications

        studies, password_users = self._build_inputs("juan@gmail.com")

        with patch(
            "apps.notifications.tasks.send_studies_available_email.delay"
        ) as mock_available:
            queued, skipped = _dispatch_patient_notifications(studies, password_users)

        mock_available.assert_called_once()
        self.assertEqual(queued, 1)


# ======================
# Patient-creation logger
# ======================


class SyncLoggerTests(BaseTestCase):
    """Loggers added to _get_or_create_patient and _get_or_create_study_with_practices."""

    def test_warning_logged_for_emailless_patient(self):
        """When sync creates a patient without an email, a WARNING fires
        with the user_pk + dni so the lab can see how many patients are
        in the QR/manual-claim-only state."""
        # NUMMEDICO_FLD=501 ("Lopez, Juan") — a real doctor, so the derivación
        # filter doesn't preempt this test's emailless-patient warning path.
        emailless_pac = {
            "NUMERO_FLD": 999666,
            "NOMBRE_FLD": "NOEMAIL, JUAN",
            "HCLIN_FLD": "11122299",
            "SEXO_FLD": 1,
            "FNACIM_FLD": "19800101",
            "MUTUAL_FLD": 0,
            "MEDICO_FLD": 0,
            "NUMMEDICO_FLD": 501,
            "CARNET_FLD": "",
            "TELEFONO_FLD": "",
            "CELULAR_FLD": "",
            "DIRECCION_FLD": "",
            "LOCALIDAD_FLD": "",
            "EMAIL_FLD": "",
            "DEBEBONO_FLD": "0",
        }
        emailless_deters = [
            {
                "NUMERO_FLD": 999666,
                "ABREV_FLD": "GLU-Bi",
                "RESULT_FLD": "100",
                "RESULTREP_FLD": "",
                "VALIDADO_FLD": "1",
                "CARGADO_FLD": "1",
                "FECHA_FLD": "20251028",
                "HORA_FLD": "10:00",
                "ORDEN_FLD": 1,
                "OPERADOR_FLD": "TEST",
                "SUCURSAL_FLD": 1,
            }
        ]

        with patch.object(
            MockLabWinConnector, "fetch_validated_deters"
        ) as mock_deters, patch.object(
            MockLabWinConnector, "fetch_pacientes"
        ) as mock_pac:
            mock_deters.return_value = iter([emailless_deters])
            mock_pac.return_value = {999666: emailless_pac}

            with self.assertLogs("apps.labwin_sync.tasks", level="WARNING") as captured:
                sync_labwin_results(lab_client_id=1, full_sync=True)

        joined = "\n".join(captured.output)
        self.assertIn(
            "patient created without email",
            joined,
            "Expected the emailless-patient WARNING log line",
        )

    def test_summary_line_logged_at_end(self):
        """sync_labwin_results emits a SUMMARY line with all counters
        suitable for grepping in production logs."""
        with self.assertLogs("apps.labwin_sync.tasks", level="INFO") as captured:
            sync_labwin_results(lab_client_id=1, full_sync=True)

        joined = "\n".join(captured.output)
        self.assertIn("sync_labwin_results SUMMARY", joined)
        # Field labels we promise to keep stable for log-tail tooling
        for field in (
            "patients_created=",
            "studies_created=",
            "study_practices_created=",
            "notifications_queued=",
            "emails_skipped=",
        ):
            self.assertIn(field, joined, f"SUMMARY missing {field}")


# ======================
# Reference range population (CSV path)
# ======================


class ReferenceRangePopulationTests(BaseTestCase):
    """import_labwin_practices now writes Practice.reference_range from
    the cleaned RESULTS_FLD, not just the raw result_template."""

    def test_extract_and_save_reference_range(self):
        import csv as _csv

        with tempfile.TemporaryDirectory() as tmp:
            practices_path = Path(tmp) / "practicas.csv"
            references_path = Path(tmp) / "referencias.csv"

            # practices.csv — minimal CODIGO,DETERMINACION
            with open(practices_path, "w", newline="") as f:
                w = _csv.writer(f)
                w.writerow(["CODIGO", "DETERMINACION"])
                w.writerow(["TEST-RR", "Test Practice With Range"])

            # references.csv — RESULTS_FLD with LabWin formatting tags around
            # the actual range text. extract_reference_range should clean it
            # down to readable English.
            with open(references_path, "w", newline="") as f:
                w = _csv.writer(f)
                w.writerow(["ABREV_FLD", "RESULTS_FLD"])
                w.writerow(["TEST-RR", "{L=2}Reference: 70-110 mg/dL{CrLf}{FB=1}"])

            call_command(
                "import_labwin_practices",
                f"--practices={practices_path}",
                f"--references={references_path}",
            )

        practice = Practice.objects.get(code="TEST-RR")
        # The cleaned form should contain the range text without the tags
        self.assertIn("70-110", practice.reference_range)
        self.assertIn("mg/dL", practice.reference_range)
        # Raw template should also be persisted (separate field)
        self.assertIn("{L=2}", practice.result_template)


# ======================
# cleanup_misplaced_fdb command
# ======================


class CleanupMisplacedFDBTests(BaseTestCase):
    """The cleanup command deletes stray .FDB-likes and moves orphan PDFs
    to /results/. We mock the FTP connector entirely so no network is
    required."""

    def test_deletes_fdb_files_and_moves_orphan_pdfs(self):
        from apps.labwin_sync.management.commands.cleanup_misplaced_fdb import (
            cleanup_misplaced_uploads,
        )

        # Build a fake ftplib.FTP object that records calls. The connector's
        # `connect()` sets `self._ftp` to the real ftplib.FTP. We replace
        # the whole connector path through get_ftp_connector + monkey-patch.
        fake_ftp = MagicMock()

        # /results listing: one stray .FDB and one normal .pdf
        results_entries = [
            (".", {"type": "cdir"}),
            ("..", {"type": "pdir"}),
            (
                "BASEDAT_20260501_0200.FDB",
                {"type": "file", "size": "2400000000"},
            ),
            ("100123-12345-LEGIT,PATIENT.pdf", {"type": "file", "size": "200000"}),
        ]
        # / listing: one stray .FDB and one orphan .pdf
        root_entries = [
            (".", {"type": "cdir"}),
            ("..", {"type": "pdir"}),
            ("BASEDAT_old.fbk.gz", {"type": "file", "size": "70000000"}),
            ("999000-99999-ORPHAN,PDF.pdf", {"type": "file", "size": "100000"}),
        ]

        # mlsd is called twice: once in /results, once in /. Side-effect
        # in order.
        fake_ftp.mlsd.side_effect = [iter(results_entries), iter(root_entries)]

        # Patch get_ftp_connector → return a mock connector wrapping fake_ftp
        from apps.labwin_sync.management.commands import (
            cleanup_misplaced_fdb as cmd_mod,
        )

        mock_connector = MagicMock()
        mock_connector._ftp = fake_ftp

        with patch.object(cmd_mod, "get_ftp_connector", return_value=mock_connector):
            result = cleanup_misplaced_uploads(dry_run=False)

        # Two .FDB-like files deleted (/results/BASEDAT_..FDB + /BASEDAT_old.fbk.gz)
        self.assertEqual(len(result["deleted"]), 2)
        self.assertTrue(
            any("BASEDAT_20260501_0200.FDB" in d for d in result["deleted"])
        )
        self.assertTrue(any("BASEDAT_old.fbk.gz" in d for d in result["deleted"]))

        # One PDF moved from / to /results/
        self.assertEqual(len(result["moved"]), 1)
        src, dst = result["moved"][0]
        self.assertEqual(src, "/999000-99999-ORPHAN,PDF.pdf")
        self.assertEqual(dst, "/results/999000-99999-ORPHAN,PDF.pdf")

        # The legitimate PDF in /results/ was not touched
        legit_touched = any("LEGIT,PATIENT" in d for d in result["deleted"]) or any(
            "LEGIT,PATIENT" in src for src, _ in result["moved"]
        )
        self.assertFalse(legit_touched, "Legitimate PDFs must not be touched")

        # Bytes freed reflects both deleted files
        self.assertEqual(result["bytes_freed"], 2400000000 + 70000000)

    def test_dry_run_makes_no_ftp_changes(self):
        from apps.labwin_sync.management.commands import (
            cleanup_misplaced_fdb as cmd_mod,
        )
        from apps.labwin_sync.management.commands.cleanup_misplaced_fdb import (
            cleanup_misplaced_uploads,
        )

        fake_ftp = MagicMock()
        fake_ftp.mlsd.side_effect = [
            iter(
                [
                    (
                        "BASEDAT_test.FDB",
                        {"type": "file", "size": "100"},
                    ),
                ]
            ),
            iter([]),
        ]
        mock_connector = MagicMock()
        mock_connector._ftp = fake_ftp

        with patch.object(cmd_mod, "get_ftp_connector", return_value=mock_connector):
            result = cleanup_misplaced_uploads(dry_run=True)

        self.assertEqual(len(result["deleted"]), 1)
        # delete() / rename() must NOT have been called in dry-run
        fake_ftp.delete.assert_not_called()
        fake_ftp.rename.assert_not_called()


# ======================
# Connector Query Filter Regression
# ======================


class ConnectorPRVDeletedFilterTests(BaseTestCase):
    """Guards against re-introducing the `PRV_DELETEDRECORD_FLD = '0'` filter.

    Why: in the live LabWin DB, ~80–93% of rows on DETERS / MEDICOS / NOMEN /
    PACIENTES have this column NULL and the rest are '0' — no row is ever
    actually marked deleted. The previous filter `WHERE PRV_DELETEDRECORD_FLD = '0'`
    silently dropped every NULL row, which meant ~87% of MEDICOS rows never
    reached the sync — that's why most synced studies ended up with
    `ordered_by=NULL` (the referring doctor's MEDICOS row had been filtered
    out before `_get_or_create_doctor` ever saw it). Bug shipped 2026-04-?,
    fixed 2026-05-07.

    If this column ever starts being used to denote deletion, switch to
    `(PRV_DELETEDRECORD_FLD IS NULL OR PRV_DELETEDRECORD_FLD <> '<sentinel>')`
    after confirming what value the lab uses to flag a deleted row.
    """

    def test_no_query_filters_on_prv_deletedrecord_fld(self):
        from apps.labwin_sync.connectors import firebird

        for query_name in (
            "DETERS_QUERY",
            "DETERS_QUERY_FULL",
            "MEDICOS_QUERY",
            "NOMEN_QUERY",
            "PACIENTES_QUERY",
        ):
            sql = getattr(firebird, query_name)
            self.assertNotIn(
                "PRV_DELETEDRECORD_FLD",
                sql,
                f"{query_name} must not filter on PRV_DELETEDRECORD_FLD — "
                "see ConnectorPRVDeletedFilterTests docstring for context.",
            )


# ======================
# Backfill ordered_by on existing studies
# ======================


@override_settings(LABWIN_SYNC_WINDOW_DAYS=10000)
class SyncBackfillsOrderedByTests(BaseTestCase):
    """Re-syncs must backfill `ordered_by` on studies that were imported
    without a doctor (e.g. when the connector previously dropped the MEDICOS
    row via the buggy PRV_DELETEDRECORD_FLD filter). But never overwrite a
    doctor that's already linked — manual corrections take precedence."""

    def test_resync_backfills_when_ordered_by_is_null(self):
        # First sync — creates the study with the doctor linked.
        sync_labwin_results(lab_client_id=1, full_sync=True)
        study = Study.objects.filter(protocol_number="LW-100001").first()
        self.assertIsNotNone(study)
        self.assertIsNotNone(study.ordered_by_id)

        # Simulate the historical bug: the doctor link was lost (e.g. the
        # connector silently filtered out the MEDICOS row, so the sync
        # created the study with ordered_by=NULL).
        original_doctor_pk = study.ordered_by_id
        study.ordered_by = None
        study.save(update_fields=["ordered_by", "updated_at"])
        study.refresh_from_db()
        self.assertIsNone(study.ordered_by_id)

        # Re-sync — connector now returns the MEDICOS row, so the doctor_pk
        # is available again. The existing-study branch should backfill it.
        sync_labwin_results(lab_client_id=1, full_sync=True)

        study.refresh_from_db()
        self.assertEqual(study.ordered_by_id, original_doctor_pk)

    def test_resync_does_not_overwrite_existing_ordered_by(self):
        """If a study already has a doctor linked (possibly manually corrected
        by an admin), the sync must leave it alone."""
        # First sync — creates the study with the mock connector's doctor.
        sync_labwin_results(lab_client_id=1, full_sync=True)
        study = Study.objects.filter(protocol_number="LW-100001").first()
        self.assertIsNotNone(study)

        # Manual correction: an admin re-linked the study to a different
        # doctor (representing a real-world fix).
        manual_doctor = self.create_doctor(
            email="manual-correct@example.com",
            first_name="Manual",
            last_name="Correction",
            matricula="ZZZ-999",
        )
        study.ordered_by = manual_doctor
        study.save(update_fields=["ordered_by", "updated_at"])

        # Re-sync — must NOT clobber the manually-set doctor.
        sync_labwin_results(lab_client_id=1, full_sync=True)

        study.refresh_from_db()
        self.assertEqual(study.ordered_by_id, manual_doctor.pk)


# ----------------------------------------------------------------------------
# Practice layout (RESULTS + VALNOR → result_layout JSON) — added 2026-05-08
# ----------------------------------------------------------------------------


class BuildLayoutTests(BaseTestCase):
    """build_layout(): turn raw RESULTS+VALNOR rows into result_layout JSON."""

    def _hemc_results_rows(self):
        """Realistic subset of HEMC RESULTS rows from the live DB."""
        from datetime import datetime as dt

        return [
            # pos=1 has a "Valor calculado Nº 1" template row that must be skipped
            {
                "ABREV_FLD": "HEMC",
                "POSICION_FLD": 1,
                "INRESUL_FLD": "Valor calculado Nº 1",
                "UNIDADES_FLD": "por mm3",
                "FORMATO_FLD": 1,
                "DECIMALES_FLD": 0,
                "FACTOR_FLD": 1.0,
                "LIMINFIM_FLD": "",
                "LIMINFMB_FLD": "",
                "LIMINFBA_FLD": "",
                "LIMSUPAL_FLD": "",
                "LIMSUPMA_FLD": "",
                "LIMSUPIM_FLD": "",
                "PRV_TIMESTAMP_FLD": dt(2010, 1, 1),
            },
            # pos=1 real row — Leucocitos
            {
                "ABREV_FLD": "HEMC",
                "POSICION_FLD": 1,
                "INRESUL_FLD": "Leucocitos",
                "UNIDADES_FLD": "/mm3",
                "FORMATO_FLD": 1,
                "DECIMALES_FLD": 0,
                "FACTOR_FLD": 100.0,
                "LIMINFIM_FLD": "",
                "LIMINFMB_FLD": "",
                "LIMINFBA_FLD": "",
                "LIMSUPAL_FLD": "",
                "LIMSUPMA_FLD": "",
                "LIMSUPIM_FLD": "",
                "PRV_TIMESTAMP_FLD": dt(2026, 4, 23),
            },
            # pos=2 real row — Hematíes (with abnormal limits)
            {
                "ABREV_FLD": "HEMC",
                "POSICION_FLD": 2,
                "INRESUL_FLD": "Hematies",
                "UNIDADES_FLD": "/mm3",
                "FORMATO_FLD": 1,
                "DECIMALES_FLD": 0,
                "FACTOR_FLD": 1000.0,
                "LIMINFIM_FLD": "600",
                "LIMINFMB_FLD": "*",
                "LIMINFBA_FLD": "*",
                "LIMSUPAL_FLD": "*",
                "LIMSUPMA_FLD": "*",
                "LIMSUPIM_FLD": "20000",
                "PRV_TIMESTAMP_FLD": dt(2024, 10, 10),
            },
            # pos=3 real row — Hemoglobina (decimals=1, factor=0)
            {
                "ABREV_FLD": "HEMC",
                "POSICION_FLD": 3,
                "INRESUL_FLD": "Hemoglobina",
                "UNIDADES_FLD": "gr%",
                "FORMATO_FLD": 1,
                "DECIMALES_FLD": 1,
                "FACTOR_FLD": 0.0,
                "LIMINFIM_FLD": "20",
                "LIMINFMB_FLD": "*",
                "LIMINFBA_FLD": "6",
                "LIMSUPAL_FLD": "*",
                "LIMSUPMA_FLD": "200",
                "LIMSUPIM_FLD": "*",
                "PRV_TIMESTAMP_FLD": dt(2024, 10, 10),
            },
        ]

    def _hemc_valnor_rows(self):
        return [
            {
                "ABREV_FLD": "HEMC",
                "POSICION_FLD": 1,
                "SEXO_FLD": 0,
                "EDADINFV_FLD": 10,
                "EDADINFL_FLD": "A",
                "EDADSUPV_FLD": 99,
                "EDADSUPL_FLD": "A",
                "TEXTO_FLD": "4.000-10.000",
            },
            {
                "ABREV_FLD": "HEMC",
                "POSICION_FLD": 2,
                "SEXO_FLD": 2,
                "EDADINFV_FLD": 18,
                "EDADINFL_FLD": "A",
                "EDADSUPV_FLD": 99,
                "EDADSUPL_FLD": "A",
                "TEXTO_FLD": "4.000.000-5.000.000",
            },
            {
                "ABREV_FLD": "HEMC",
                "POSICION_FLD": 2,
                "SEXO_FLD": 1,
                "EDADINFV_FLD": 18,
                "EDADINFL_FLD": "A",
                "EDADSUPV_FLD": 99,
                "EDADSUPL_FLD": "A",
                "TEXTO_FLD": "4.500.000-5.500.000",
            },
            {
                "ABREV_FLD": "HEMC",
                "POSICION_FLD": 3,
                "SEXO_FLD": 2,
                "EDADINFV_FLD": 18,
                "EDADINFL_FLD": "A",
                "EDADSUPV_FLD": 99,
                "EDADSUPL_FLD": "A",
                "TEXTO_FLD": "12,0-15,0",
            },
            {
                "ABREV_FLD": "HEMC",
                "POSICION_FLD": 3,
                "SEXO_FLD": 1,
                "EDADINFV_FLD": 18,
                "EDADINFL_FLD": "A",
                "EDADSUPV_FLD": 99,
                "EDADSUPL_FLD": "A",
                "TEXTO_FLD": "13,5-18,0",
            },
        ]

    def test_build_layout_skips_template_rows(self):
        from apps.labwin_sync.services.practice_layout import build_layout

        layout = build_layout(
            "HEMC", self._hemc_results_rows(), self._hemc_valnor_rows()
        )
        # 3 positions, not 4 — the "Valor calculado Nº 1" row is dropped.
        self.assertEqual(len(layout["items"]), 3)
        labels = [i["label"] for i in layout["items"]]
        self.assertEqual(labels, ["Leucocitos", "Hematies", "Hemoglobina"])

    def test_build_layout_picks_newest_per_position(self):
        from datetime import datetime as dt

        from apps.labwin_sync.services.practice_layout import build_layout

        rows = self._hemc_results_rows()
        rows.append(
            {
                "ABREV_FLD": "HEMC",
                "POSICION_FLD": 1,
                "INRESUL_FLD": "Old Leucocitos label",
                "UNIDADES_FLD": "/L",
                "FORMATO_FLD": 1,
                "DECIMALES_FLD": 0,
                "FACTOR_FLD": 999.0,
                "LIMINFIM_FLD": "",
                "LIMINFMB_FLD": "",
                "LIMINFBA_FLD": "",
                "LIMSUPAL_FLD": "",
                "LIMSUPMA_FLD": "",
                "LIMSUPIM_FLD": "",
                "PRV_TIMESTAMP_FLD": dt(2015, 1, 1),
            }
        )
        layout = build_layout("HEMC", rows, self._hemc_valnor_rows())
        item1 = next(i for i in layout["items"] if i["position"] == 1)
        # The 2026 row wins over the 2015 row.
        self.assertEqual(item1["label"], "Leucocitos")
        self.assertEqual(item1["unit"], "/mm3")
        self.assertEqual(item1["factor"], 100.0)

    def test_build_layout_attaches_valnor_per_position(self):
        from apps.labwin_sync.services.practice_layout import build_layout

        layout = build_layout(
            "HEMC", self._hemc_results_rows(), self._hemc_valnor_rows()
        )
        pos2 = next(i for i in layout["items"] if i["position"] == 2)
        self.assertEqual(len(pos2["valnor"]), 2)  # M + F adult rows
        sexes = sorted(v["sex"] for v in pos2["valnor"])
        self.assertEqual(sexes, [1, 2])

    def test_build_layout_normalizes_abnormal_limits(self):
        from apps.labwin_sync.services.practice_layout import build_layout

        layout = build_layout(
            "HEMC", self._hemc_results_rows(), self._hemc_valnor_rows()
        )
        pos1 = next(i for i in layout["items"] if i["position"] == 1)
        self.assertIsNone(pos1["abnormal_limits"])  # all '*'/'' cleaned to None
        pos2 = next(i for i in layout["items"] if i["position"] == 2)
        self.assertEqual(pos2["abnormal_limits"]["min_imposible"], "600")
        self.assertEqual(pos2["abnormal_limits"]["max_imposible"], "20000")
        # '*' values must round-trip as None
        self.assertIsNone(pos2["abnormal_limits"]["min_critical"])

    def test_build_layout_returns_none_when_only_template_rows(self):
        from datetime import datetime as dt

        from apps.labwin_sync.services.practice_layout import build_layout

        rows = [
            {
                "ABREV_FLD": "FOO",
                "POSICION_FLD": 1,
                "INRESUL_FLD": "Valor calculado Nº 1",
                "UNIDADES_FLD": "",
                "FORMATO_FLD": 1,
                "DECIMALES_FLD": 0,
                "FACTOR_FLD": 1.0,
                "LIMINFIM_FLD": "",
                "LIMINFMB_FLD": "",
                "LIMINFBA_FLD": "",
                "LIMSUPAL_FLD": "",
                "LIMSUPMA_FLD": "",
                "LIMSUPIM_FLD": "",
                "PRV_TIMESTAMP_FLD": dt(2020, 1, 1),
            }
        ]
        self.assertIsNone(build_layout("FOO", rows, []))


class ResolveValnorForPatientTests(BaseTestCase):
    """resolve_valnor_for_patient(): pick the right V.R. for a patient."""

    def _layout(self):
        return {
            "items": [
                {
                    "position": 1,
                    "label": "Leucocitos",
                    "valnor": [
                        {
                            "sex": 0,
                            "age_min_value": 10,
                            "age_min_unit": "A",
                            "age_max_value": 99,
                            "age_max_unit": "A",
                            "text": "4.000-10.000",
                        }
                    ],
                },
                {
                    "position": 2,
                    "label": "Hematies",
                    "valnor": [
                        {
                            "sex": 1,
                            "age_min_value": 18,
                            "age_min_unit": "A",
                            "age_max_value": 99,
                            "age_max_unit": "A",
                            "text": "4.500.000-5.500.000",
                        },
                        {
                            "sex": 2,
                            "age_min_value": 18,
                            "age_min_unit": "A",
                            "age_max_value": 99,
                            "age_max_unit": "A",
                            "text": "4.000.000-5.000.000",
                        },
                    ],
                },
            ]
        }

    def test_resolves_male_adult(self):
        from apps.labwin_sync.services.practice_layout import resolve_valnor_for_patient

        resolved = resolve_valnor_for_patient(
            self._layout(), patient_sex=1, patient_age_days=30 * 365
        )
        self.assertEqual(resolved["1"], "4.000-10.000")  # sex=0 (any) match
        self.assertEqual(resolved["2"], "4.500.000-5.500.000")  # sex=M match

    def test_resolves_female_adult(self):
        from apps.labwin_sync.services.practice_layout import resolve_valnor_for_patient

        resolved = resolve_valnor_for_patient(
            self._layout(), patient_sex=2, patient_age_days=30 * 365
        )
        self.assertEqual(resolved["2"], "4.000.000-5.000.000")  # sex=F match

    def test_skips_position_with_no_match(self):
        from apps.labwin_sync.services.practice_layout import resolve_valnor_for_patient

        # Child — neither pos=2 row matches (both require 18+).
        resolved = resolve_valnor_for_patient(
            self._layout(), patient_sex=1, patient_age_days=5 * 365
        )
        self.assertNotIn("2", resolved)

    def test_returns_empty_dict_for_none_layout(self):
        from apps.labwin_sync.services.practice_layout import resolve_valnor_for_patient

        self.assertEqual(
            resolve_valnor_for_patient(None, patient_sex=1, patient_age_days=10000),
            {},
        )

    def test_skips_vet_rows_for_human_patients(self):
        from apps.labwin_sync.services.practice_layout import resolve_valnor_for_patient

        layout = {
            "items": [
                {
                    "position": 1,
                    "label": "X",
                    "valnor": [
                        {
                            "sex": 8,
                            "age_min_value": 1,
                            "age_min_unit": "M",
                            "age_max_value": 99,
                            "age_max_unit": "A",
                            "text": "VET-RANGE",
                        }
                    ],
                }
            ]
        }
        resolved = resolve_valnor_for_patient(
            layout, patient_sex=1, patient_age_days=30 * 365
        )
        self.assertNotIn("1", resolved)


class PatientAgeDaysForSyncTests(BaseTestCase):
    """_patient_age_days_for_sync(): YYYYMMDD strings → days at sample."""

    def test_basic(self):
        from apps.labwin_sync.tasks import _patient_age_days_for_sync

        # 2020-01-01 → 2026-05-07 ≈ 2317 days
        days = _patient_age_days_for_sync("20200101", "20260507")
        self.assertGreater(days, 2300)
        self.assertLess(days, 2330)

    def test_returns_none_for_missing_dob(self):
        from apps.labwin_sync.tasks import _patient_age_days_for_sync

        self.assertIsNone(_patient_age_days_for_sync(None, "20260507"))
        self.assertIsNone(_patient_age_days_for_sync("", "20260507"))

    def test_returns_none_for_unparseable(self):
        from apps.labwin_sync.tasks import _patient_age_days_for_sync

        self.assertIsNone(_patient_age_days_for_sync("not-a-date", "20260507"))
        self.assertIsNone(_patient_age_days_for_sync("20200230", "20260507"))

    def test_returns_none_for_negative_age(self):
        from apps.labwin_sync.tasks import _patient_age_days_for_sync

        self.assertIsNone(_patient_age_days_for_sync("20300101", "20260507"))


# ----------------------------------------------------------------------------
# Protocol-level validation gate (added 2026-05-08)
# ----------------------------------------------------------------------------


class IsProtocolFullyValidatedTests(BaseTestCase):
    """is_protocol_fully_validated(): protocol-level validation gate."""

    def test_all_validated_and_loaded_returns_true(self):
        from apps.labwin_sync.mappers import is_protocol_fully_validated

        rows = [
            {"VALIDADO_FLD": "1", "CARGADO_FLD": "1"},
            {"VALIDADO_FLD": "1", "CARGADO_FLD": "1"},
        ]
        self.assertTrue(is_protocol_fully_validated(rows))

    def test_one_not_validated_returns_false(self):
        from apps.labwin_sync.mappers import is_protocol_fully_validated

        rows = [
            {"VALIDADO_FLD": "1", "CARGADO_FLD": "1"},
            {"VALIDADO_FLD": "0", "CARGADO_FLD": "0"},
        ]
        self.assertFalse(is_protocol_fully_validated(rows))

    def test_validated_but_not_loaded_returns_false(self):
        from apps.labwin_sync.mappers import is_protocol_fully_validated

        rows = [
            {"VALIDADO_FLD": "1", "CARGADO_FLD": "1"},
            {"VALIDADO_FLD": "1", "CARGADO_FLD": "0"},
        ]
        self.assertFalse(is_protocol_fully_validated(rows))

    def test_empty_returns_false(self):
        from apps.labwin_sync.mappers import is_protocol_fully_validated

        self.assertFalse(is_protocol_fully_validated([]))


class SyncSkipsPartiallyValidatedProtocolsTests(BaseTestCase):
    """Sync must NOT ingest a protocol where any DETERS is unvalidated.

    Uses the mock connector. SAMPLE_DETERS includes order 100003 with one
    row VALIDADO_FLD='1' (TSH) and one row VALIDADO_FLD='0' (GLU-Bi).
    The whole order must be skipped — no Study, no StudyPractice rows.
    """

    def test_skips_order_with_one_unvalidated_row(self):
        from apps.labwin_sync.tasks import sync_labwin_results
        from apps.studies.models import Study

        result = sync_labwin_results(lab_client_id=1, full_sync=True)

        self.assertEqual(result["error_count"], 0)
        # Order 100001 (fully validated, paid) is ingested
        self.assertTrue(Study.objects.filter(protocol_number="LW-100001").exists())
        # Order 100002 (fully validated but DEBEBONO='1') is skipped by the
        # unpaid gate, not the partial-validation gate. Covered separately
        # in SyncSkipsUnpaidProtocolsTests.
        self.assertFalse(Study.objects.filter(protocol_number="LW-100002").exists())
        # Order 100003 (partially validated) is NOT ingested
        self.assertFalse(Study.objects.filter(protocol_number="LW-100003").exists())

    def test_deletes_existing_study_when_protocol_becomes_partially_validated(
        self,
    ):
        """If a Study was previously fully validated and the lab unvalidates one
        of its rows, the next sync must delete the Study from our DB."""
        from apps.labwin_sync.connectors.mock import SAMPLE_DETERS, SAMPLE_PACIENTES
        from apps.labwin_sync.tasks import sync_labwin_results
        from apps.studies.models import Study, StudyPractice

        # Snapshot original mock state so we can restore it.
        snapshot = []
        for row in SAMPLE_DETERS:
            if row["NUMERO_FLD"] == 100003:
                snapshot.append(
                    (row["ABREV_FLD"], row["VALIDADO_FLD"], row["CARGADO_FLD"])
                )
        # 100003 has DEBEBONO_FLD='1' in the fixture, which would trip the
        # unpaid gate before the partial-validation gate has anything to
        # delete. This test cares only about the partial-validation flow,
        # so flip 100003 to paid for the duration of the test.
        original_debebono = SAMPLE_PACIENTES[100003]["DEBEBONO_FLD"]
        SAMPLE_PACIENTES[100003]["DEBEBONO_FLD"] = "0"

        try:
            # Step 1: simulate the lab validating the missing row →
            # 100003 becomes fully validated
            for row in SAMPLE_DETERS:
                if row["NUMERO_FLD"] == 100003 and row["ABREV_FLD"] == "GLU-Bi":
                    row["VALIDADO_FLD"] = "1"
                    row["CARGADO_FLD"] = "1"

            sync_labwin_results(lab_client_id=1, full_sync=True)
            self.assertTrue(Study.objects.filter(protocol_number="LW-100003").exists())
            study = Study.objects.get(protocol_number="LW-100003")
            self.assertEqual(StudyPractice.objects.filter(study_id=study.id).count(), 2)
            study_id = study.id  # capture for the cascade-out check below

            # Step 2: simulate the lab unvalidating GLU-Bi again
            for row in SAMPLE_DETERS:
                if row["NUMERO_FLD"] == 100003 and row["ABREV_FLD"] == "GLU-Bi":
                    row["VALIDADO_FLD"] = "0"
                    row["CARGADO_FLD"] = "0"

            sync_labwin_results(lab_client_id=1, full_sync=True)
            # The previously-ingested Study must be deleted
            self.assertFalse(Study.objects.filter(protocol_number="LW-100003").exists())
            self.assertEqual(StudyPractice.objects.filter(study_id=study_id).count(), 0)
        finally:
            # Restore mock state regardless of test outcome
            SAMPLE_PACIENTES[100003]["DEBEBONO_FLD"] = original_debebono
            for abrev, validado, cargado in snapshot:
                for row in SAMPLE_DETERS:
                    if row["NUMERO_FLD"] == 100003 and row["ABREV_FLD"] == abrev:
                        row["VALIDADO_FLD"] = validado
                        row["CARGADO_FLD"] = cargado


class SyncSkipsUnpaidProtocolsTests(BaseTestCase):
    """Sync must NOT ingest a protocol whose patient owes the bono.

    Mock fixture has order 100002 with DEBEBONO_FLD='1'. The whole order
    must be skipped — no Study, no StudyPractice rows — because the lab
    never produces a PDF for these and the row would just clutter the
    patient's results list.
    """

    @override_settings(LABWIN_USE_MOCK=True)
    def test_skips_protocol_when_patient_owes_bono(self):
        from apps.labwin_sync.tasks import sync_labwin_results
        from apps.studies.models import Study

        result = sync_labwin_results(lab_client_id=1, full_sync=True)

        self.assertEqual(result["error_count"], 0)
        # 100002 (DEBEBONO='1') must not exist after sync
        self.assertFalse(Study.objects.filter(protocol_number="LW-100002").exists())
        # And the counter records exactly one skip
        self.assertEqual(result.get("unpaid_skipped", 0), 1)
        # Nothing was deleted (no prior study existed)
        self.assertEqual(result.get("unpaid_deleted", 0), 0)

    @override_settings(LABWIN_USE_MOCK=True)
    def test_deletes_existing_study_when_protocol_becomes_unpaid(self):
        """If a Study was previously paid+ingested and the lab flips
        DEBEBONO_FLD to '1', the next sync must delete the Study from
        our DB (mirrors the partial-validation deletion behaviour)."""
        from apps.labwin_sync.connectors.mock import SAMPLE_PACIENTES
        from apps.labwin_sync.tasks import sync_labwin_results
        from apps.studies.models import Study, StudyPractice

        original_debebono = SAMPLE_PACIENTES[100002]["DEBEBONO_FLD"]
        try:
            # Step 1: simulate the lab marking 100002 as paid → it ingests
            SAMPLE_PACIENTES[100002]["DEBEBONO_FLD"] = "0"
            sync_labwin_results(lab_client_id=1, full_sync=True)
            self.assertTrue(Study.objects.filter(protocol_number="LW-100002").exists())
            study = Study.objects.get(protocol_number="LW-100002")
            study_id = study.id
            self.assertGreater(
                StudyPractice.objects.filter(study_id=study_id).count(), 0
            )

            # Step 2: lab flips DEBEBONO back to '1' (e.g. payment reversed)
            SAMPLE_PACIENTES[100002]["DEBEBONO_FLD"] = "1"
            result = sync_labwin_results(lab_client_id=1, full_sync=True)

            self.assertFalse(Study.objects.filter(protocol_number="LW-100002").exists())
            self.assertEqual(StudyPractice.objects.filter(study_id=study_id).count(), 0)
            self.assertEqual(result.get("unpaid_skipped", 0), 1)
            self.assertEqual(result.get("unpaid_deleted", 0), 1)
        finally:
            SAMPLE_PACIENTES[100002]["DEBEBONO_FLD"] = original_debebono


# ======================
# DETERS SQL — partial-validation guard (patch 1)
# ======================


class DETERSQueryPartialValidationFilterTests(BaseTestCase):
    """Regression tests for the SQL-level partial-validation guard.

    Pre-2026-05-11 the Firebird connector returned ALL DETERS rows and
    relied on Python (`is_protocol_fully_validated`) to skip partial
    protocols. But `cursor.fetchmany(500)` splits a single NUMERO across
    batches, and the per-batch grouping in `tasks.py` evaluated the gate
    on a partial slice — so a NUMERO with 12 validated + 3 unvalidated
    rows could end up imported with only the validated subset (real
    failure: LW-257008 on 2026-05-11). The fix is at the SQL level: the
    connector excludes any NUMERO that has at least one row with
    VALIDADO_FLD<>'1' OR CARGADO_FLD<>'1' OR NULL on either flag.
    """

    def test_deters_query_contains_partial_numero_filter(self):
        """Incremental DETERS_QUERY excludes NUMEROs with any non-validated row."""
        from apps.labwin_sync.connectors import firebird as fb

        sql = fb.DETERS_QUERY
        self.assertIn("NUMERO_FLD NOT IN", sql)
        self.assertIn("VALIDADO_FLD", sql)
        self.assertIn("CARGADO_FLD", sql)
        # Both NULL and non-'1' must be excluded (Firebird treats NULL
        # differently from <> in a way that silently drops rows otherwise).
        self.assertIn("VALIDADO_FLD IS NULL", sql)
        self.assertIn("CARGADO_FLD IS NULL", sql)

    def test_deters_query_full_contains_partial_numero_filter(self):
        """Full-scan DETERS_QUERY_FULL has the same guard as the incremental form."""
        from apps.labwin_sync.connectors import firebird as fb

        sql = fb.DETERS_QUERY_FULL
        self.assertIn("NUMERO_FLD NOT IN", sql)
        self.assertIn("VALIDADO_FLD", sql)
        self.assertIn("CARGADO_FLD", sql)
        self.assertIn("VALIDADO_FLD IS NULL", sql)
        self.assertIn("CARGADO_FLD IS NULL", sql)

    def test_fetch_validated_deters_executes_guarded_sql(self):
        """fetch_validated_deters fires the SQL string with the partial-NUMERO guard."""
        from apps.labwin_sync.connectors.firebird import (
            DETERS_QUERY,
            DETERS_QUERY_FULL,
            FirebirdLabWinConnector,
        )

        captured = {}

        class FakeCursor:
            def execute(self, sql, params=None):
                captured["sql"] = sql
                captured["params"] = params

            def fetchmany(self, n):
                return []

            def close(self):
                pass

        class FakeConn:
            def cursor(self):
                return FakeCursor()

        connector = FirebirdLabWinConnector()
        connector.connection = FakeConn()

        # Full-scan path
        captured.clear()
        list(connector.fetch_validated_deters())
        self.assertEqual(captured["sql"], DETERS_QUERY_FULL)
        self.assertIn("NUMERO_FLD NOT IN", captured["sql"])

        # Incremental path
        captured.clear()
        list(connector.fetch_validated_deters(since_fecha="20260101", since_numero=0))
        self.assertEqual(captured["sql"], DETERS_QUERY)
        self.assertIn("NUMERO_FLD NOT IN", captured["sql"])
        self.assertEqual(captured["params"], ("20260101", "20260101", 0))


# ======================
# biological_sex split (PR 2 — UAT feedback 2026-05-12)
# ======================


class SyncBiologicalSexNeverTouchesGenderTests(BaseTestCase):
    """Sync writes biological_sex from SEXO_FLD and never overwrites gender.

    The lab needs biological_sex on file for clinical reference ranges,
    sourced from LabWin's SEXO_FLD. Patients can self-declare a different
    gender through the profile/registration flows, and sync MUST NOT
    overwrite that.
    """

    def test_sync_writes_biological_sex_on_create(self):
        """First sync of a new patient populates biological_sex from SEXO_FLD."""
        # Sample data has SEXO_FLD=2 for patient 100001 (= Female).
        sync_labwin_results(lab_client_id=1, full_sync=True)

        from apps.users.models import User

        user = User.objects.filter(dni="30123456").first()
        self.assertIsNotNone(user, "sample patient should have been created")
        self.assertEqual(user.biological_sex, "F")
        # gender should be empty — sync never sets it.
        self.assertEqual(user.gender, "")

    def test_sync_does_not_overwrite_self_declared_gender(self):
        """Patient sets gender='O', sync runs, gender stays 'O'."""
        from apps.users.models import User

        # Pre-create the user that mock data will match by DNI.
        existing = self.create_patient(
            email="maria.garcia@test.com",
            dni="30123456",
            lab_client_id=1,
        )
        existing.gender = "O"
        existing.biological_sex = ""
        existing.save()

        sync_labwin_results(lab_client_id=1, full_sync=True)

        existing.refresh_from_db()
        self.assertEqual(
            existing.gender, "O", "sync must not touch self-declared gender"
        )
        self.assertEqual(
            existing.biological_sex,
            "F",
            "sync should populate biological_sex from SEXO_FLD",
        )

    def test_sync_refreshes_biological_sex_when_source_changes(self):
        """If LabWin's SEXO_FLD changes (e.g. data correction), the
        next sync updates biological_sex but still leaves gender alone."""
        from apps.users.models import User

        # User starts with biological_sex='M' (wrong) and gender='F'
        # (their self-declaration).
        existing = self.create_patient(
            email="maria.garcia@test.com",
            dni="30123456",
            lab_client_id=1,
        )
        existing.biological_sex = "M"
        existing.gender = "F"
        existing.save()

        # Mock data SEXO_FLD=2 for this patient = "F", so sync should
        # correct biological_sex from M -> F.
        sync_labwin_results(lab_client_id=1, full_sync=True)

        existing.refresh_from_db()
        self.assertEqual(
            existing.biological_sex, "F", "sync should refresh biological_sex"
        )
        self.assertEqual(existing.gender, "F", "self-declared gender stays put")


class PatientRegistrationBiologicalSexRequiredTests(BaseTestCase):
    """biological_sex is REQUIRED on patient self-registration.

    The lab's whole point: every new patient needs a biological_sex on
    file. Optional gender is fine — but biological_sex blocks the form
    if missing.
    """

    def _payload(self, **overrides):
        base = {
            "email": "newpatient@example.com",
            "password": "SecurePass123!",
            "password_confirm": "SecurePass123!",
            "first_name": "Test",
            "last_name": "Patient",
            "phone_number": "1122334455",
            "dni": "99887766",
            "birthday": "1990-05-15",
            "biological_sex": "F",
            "lab_client_id": 1,
        }
        base.update(overrides)
        return base

    def test_register_with_biological_sex_succeeds(self):
        from rest_framework.test import APIClient

        client = APIClient()
        response = client.post(
            "/api/v1/users/register/", self._payload(), format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)

        from apps.users.models import User

        user = User.objects.get(email="newpatient@example.com")
        self.assertEqual(user.biological_sex, "F")

    def test_register_without_biological_sex_fails(self):
        from rest_framework.test import APIClient

        payload = self._payload()
        payload.pop("biological_sex")

        client = APIClient()
        response = client.post("/api/v1/users/register/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("biological_sex", response.data)

    def test_register_with_blank_biological_sex_fails(self):
        from rest_framework.test import APIClient

        client = APIClient()
        response = client.post(
            "/api/v1/users/register/",
            self._payload(biological_sex=""),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("biological_sex", response.data)


class UserSerializerBiologicalSexReadOnlyTests(BaseTestCase):
    """biological_sex is exposed by UserSerializer but is read-only.

    A patient PATCHing their profile cannot change their biological_sex
    even by passing it in the body — the serializer silently ignores it.
    """

    def test_biological_sex_in_serialized_output(self):
        patient = self.create_patient(lab_client_id=1)
        patient.biological_sex = "M"
        patient.save()

        client = self.authenticate(patient)
        response = client.get("/api/v1/auth/user/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get("biological_sex"), "M")

    def test_patient_cannot_patch_biological_sex(self):
        patient = self.create_patient(lab_client_id=1)
        patient.biological_sex = "M"
        patient.save()

        client = self.authenticate(patient)
        response = client.patch(
            "/api/v1/auth/user/",
            {"biological_sex": "F"},
            format="json",
        )
        # PATCH succeeds (other fields could change), but biological_sex
        # is silently ignored because it's in read_only_fields.
        self.assertIn(response.status_code, (200, 202))
        patient.refresh_from_db()
        self.assertEqual(
            patient.biological_sex,
            "M",
            "PATCH must not be able to change biological_sex",
        )

    def test_patient_can_still_patch_gender(self):
        """Sanity check: gender is still patient-editable."""
        patient = self.create_patient(lab_client_id=1)
        patient.gender = ""
        patient.save()

        client = self.authenticate(patient)
        response = client.patch(
            "/api/v1/auth/user/",
            {"gender": "O"},
            format="json",
        )
        self.assertIn(response.status_code, (200, 202))
        patient.refresh_from_db()
        self.assertEqual(patient.gender, "O")
