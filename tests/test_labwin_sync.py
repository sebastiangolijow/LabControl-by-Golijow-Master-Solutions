"""
Tests for LabWin Firebird sync feature.

Tests cover:
- Data mappers (name parsing, date parsing, field mapping)
- Connector factory
- Mock connector behavior
- Sync task (creates records, idempotency, incremental sync, error handling)
- FTP PDF fetch (mock connector, study matching, file attachment)
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
from apps.labwin_sync.ftp import get_ftp_connector
from apps.labwin_sync.ftp.mock import MockFTPConnector
from apps.labwin_sync.mappers import (
    map_doctor,
    map_patient,
    map_practice,
    map_study,
    map_study_practice,
    parse_date,
    parse_datetime,
    parse_name,
)
from apps.labwin_sync.models import SyncedRecord, SyncLog
from apps.labwin_sync.tasks import cleanup_ftp_pdfs, fetch_ftp_pdfs, sync_labwin_results
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
