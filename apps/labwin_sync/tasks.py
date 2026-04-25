"""
Celery tasks for syncing lab results from LabWin.

Tasks:
- sync_labwin_results: Nightly sync from LabWin Firebird database.
- fetch_ftp_pdfs: Fetch PDF result files from FTP server and attach to studies.
- cleanup_ftp_pdfs: Remove successfully processed PDFs from FTP server.
- import_uploaded_backup: Restore latest .fbk.gz backup and trigger sync (Phase B).
"""

import logging
import os
from collections import defaultdict

from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from . import mappers
from .connectors import get_connector
from .ftp import get_ftp_connector
from .models import SyncedRecord, SyncLog

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, time_limit=3600)
def sync_labwin_results(self, lab_client_id=None, full_sync=False):
    """Sync validated results from LabWin Firebird to LabControl.

    Args:
        lab_client_id: Lab client ID to assign to synced records.
            Defaults to LABWIN_DEFAULT_LAB_CLIENT_ID setting.
        full_sync: If True, sync all records. If False, resume from last cursor.

    Returns:
        dict: Summary with counts of created/updated records and errors.
    """
    from apps.studies.models import Practice, Study, StudyPractice
    from apps.users.models import User

    if lab_client_id is None:
        lab_client_id = getattr(settings, "LABWIN_DEFAULT_LAB_CLIENT_ID", 1)

    batch_size = getattr(settings, "LABWIN_SYNC_BATCH_SIZE", 500)

    # Create sync log
    task_id = ""
    try:
        task_id = self.request.id or ""
    except AttributeError:
        pass

    sync_log = SyncLog.objects.create(
        status="started",
        lab_client_id=lab_client_id,
        celery_task_id=task_id,
    )

    # Determine cursor from last successful sync
    since_fecha = None
    since_numero = None

    if not full_sync:
        last_sync = (
            SyncLog.objects.filter(
                lab_client_id=lab_client_id,
                status="completed",
                last_synced_fecha__gt="",
            )
            .order_by("-started_at")
            .first()
        )
        if last_sync:
            since_fecha = last_sync.last_synced_fecha
            since_numero = last_sync.last_synced_numero
            logger.info(
                "Incremental sync from fecha=%s, numero=%s",
                since_fecha,
                since_numero,
            )

    # Caches to avoid repeated DB lookups within this sync run
    practice_cache = {}  # ABREV_FLD -> Practice pk
    patient_cache = {}  # NUMERO_FLD -> User pk
    doctor_cache = {}  # NUMMEDICO_FLD -> User pk

    errors = []
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
    total_processed = 0
    max_numero = since_numero
    max_fecha = since_fecha or ""

    try:
        with get_connector() as connector:
            for batch in connector.fetch_validated_deters(
                since_fecha=since_fecha,
                since_numero=since_numero,
                batch_size=batch_size,
            ):
                if not batch:
                    continue

                # Collect unique IDs from this batch
                numero_flds = set()
                medico_flds = set()
                abrev_flds = set()

                for row in batch:
                    numero_flds.add(row["NUMERO_FLD"])
                    abrev_flds.add(row["ABREV_FLD"])

                # Fetch patient data for these orders
                pacientes = connector.fetch_pacientes(list(numero_flds))
                for pac in pacientes.values():
                    num_medico = pac.get("NUMMEDICO_FLD")
                    if num_medico:
                        medico_flds.add(num_medico)

                # Fetch doctor and practice data
                medicos = connector.fetch_medicos(list(medico_flds))
                nomens = connector.fetch_nomen(
                    [a for a in abrev_flds if a not in practice_cache]
                )

                # Process practices
                for abrev, nomen_row in nomens.items():
                    if abrev in practice_cache:
                        continue
                    try:
                        practice_pk = _get_or_create_practice(
                            nomen_row, lab_client_id, sync_log, counters
                        )
                        practice_cache[abrev] = practice_pk
                    except Exception as e:
                        logger.error("Error creating practice %s: %s", abrev, e)
                        errors.append(
                            {"type": "practice", "key": abrev, "error": str(e)}
                        )

                # Process doctors
                for num, medico_row in medicos.items():
                    if num in doctor_cache:
                        continue
                    try:
                        doctor_pk = _get_or_create_doctor(
                            medico_row, lab_client_id, sync_log, counters
                        )
                        doctor_cache[num] = doctor_pk
                    except Exception as e:
                        logger.error("Error creating doctor %s: %s", num, e)
                        errors.append(
                            {"type": "doctor", "key": str(num), "error": str(e)}
                        )

                # Group DETERS rows by NUMERO_FLD (protocol)
                grouped = defaultdict(list)
                for row in batch:
                    grouped[row["NUMERO_FLD"]].append(row)

                # Process each protocol group
                for numero, rows in grouped.items():
                    total_processed += len(rows)

                    try:
                        # Ensure patient exists
                        if numero not in patient_cache:
                            pac_row = pacientes.get(numero)
                            if pac_row:
                                # Skip veterinary patients per the
                                # name-based allowlist rule. See
                                # mappers.is_pet_candidate for the rule.
                                fields = mappers.map_patient(pac_row)
                                if mappers.is_pet_candidate(
                                    fields.get("first_name"),
                                    fields.get("last_name"),
                                    fields.get("dni"),
                                ):
                                    counters.setdefault("pets_skipped", 0)
                                    counters["pets_skipped"] += 1
                                    # Mark cache as None so we don't
                                    # re-evaluate this NUMERO if it shows
                                    # up in another batch
                                    patient_cache[numero] = None
                                    continue
                                patient_pk = _get_or_create_patient(
                                    pac_row, lab_client_id, sync_log, counters
                                )
                                patient_cache[numero] = patient_pk
                            else:
                                errors.append(
                                    {
                                        "type": "study",
                                        "key": str(numero),
                                        "error": "No PACIENTES data for this NUMERO_FLD",
                                    }
                                )
                                continue

                        patient_pk = patient_cache.get(numero)
                        if not patient_pk:
                            continue

                        # Find doctor for this order
                        pac_row = pacientes.get(numero)
                        doctor_pk = None
                        if pac_row:
                            num_medico = pac_row.get("NUMMEDICO_FLD")
                            if num_medico:
                                doctor_pk = doctor_cache.get(num_medico)

                        # Ensure all practices exist for this protocol
                        for row in rows:
                            abrev = row["ABREV_FLD"]
                            if abrev not in practice_cache:
                                practice_pk = _create_minimal_practice(
                                    abrev, lab_client_id, sync_log, counters
                                )
                                practice_cache[abrev] = practice_pk

                        # Per-study flags derived from PACIENTES row.
                        # is_validated=True because the connector only fetches
                        # validated DETERS (VALIDADO_FLD='1').
                        is_paid = mappers.map_is_paid(pac_row)

                        # Create/update study and its practices
                        _get_or_create_study_with_practices(
                            numero,
                            rows,
                            patient_pk,
                            doctor_pk,
                            practice_cache,
                            lab_client_id,
                            sync_log,
                            counters,
                            is_paid=is_paid,
                            is_validated=True,
                        )

                        # Track cursor (use max fecha/numero from this group)
                        for row in rows:
                            fecha = row.get("FECHA_FLD", "")
                            if fecha > max_fecha or (
                                fecha == max_fecha
                                and (max_numero is None or numero > max_numero)
                            ):
                                max_fecha = fecha
                                max_numero = numero

                    except Exception as e:
                        logger.error("Error processing protocol %s: %s", numero, e)
                        errors.append(
                            {
                                "type": "study",
                                "key": str(numero),
                                "error": str(e),
                            }
                        )

                # Update progress (skip if no task_id, e.g. synchronous call)
                if task_id:
                    self.update_state(
                        state="PROCESSING",
                        meta={
                            "processed": total_processed,
                            **counters,
                            "errors": len(errors),
                        },
                    )

        # Success
        sync_log.status = "completed" if not errors else "partial"
        sync_log.completed_at = timezone.now()
        sync_log.last_synced_numero = max_numero
        sync_log.last_synced_fecha = max_fecha
        sync_log.errors = errors[-100:]  # Keep last 100 errors
        sync_log.error_count = len(errors)
        for key, val in counters.items():
            if hasattr(sync_log, key):
                setattr(sync_log, key, val)
        sync_log.save()

        result = {
            "message": (
                f"Sync completed. Studies: {counters['studies_created']} created, "
                f"{counters['studies_updated']} updated. "
                f"StudyPractices: {counters['study_practices_created']} created. "
                f"Patients: {counters['patients_created']} created. "
                f"Errors: {len(errors)}."
            ),
            "total_processed": total_processed,
            **counters,
            "error_count": len(errors),
        }
        logger.info("LabWin sync completed: %s", result["message"])
        return result

    except Exception as e:
        logger.exception("LabWin sync failed: %s", e)
        sync_log.status = "failed"
        sync_log.completed_at = timezone.now()
        sync_log.errors = [{"type": "fatal", "error": str(e)}]
        sync_log.error_count = 1
        sync_log.save()

        # Retry via Celery if running as a task; re-raise if called directly
        if task_id:
            self.retry(exc=e, countdown=300 * (2**self.request.retries))
        raise


def _get_or_create_patient(pac_row, lab_client_id, sync_log, counters):
    """Get or create a patient User from a PACIENTES row. Returns User pk."""
    from apps.users.models import User

    source_key = str(pac_row["NUMERO_FLD"])
    fields = mappers.map_patient(pac_row)

    # Check SyncedRecord first
    existing = SyncedRecord.objects.filter(
        source_table="PACIENTES",
        source_key=source_key,
        lab_client_id=lab_client_id,
    ).first()

    if existing:
        # Update existing patient
        user = User.objects.filter(pk=existing.target_uuid).first()
        if user:
            update_fields = []
            for field_name in ["phone_number", "direction", "location", "carnet"]:
                new_val = fields.get(field_name)
                if new_val and new_val != getattr(user, field_name, ""):
                    setattr(user, field_name, new_val)
                    update_fields.append(field_name)
            if update_fields:
                user.save(update_fields=update_fields)
                counters["patients_updated"] += 1
            return user.pk
        # SyncedRecord exists but user was deleted, fall through to create

    # Try to match by DNI
    dni = fields.get("dni")
    if dni:
        user = User.objects.filter(
            dni=dni, role="patient", lab_client_id=lab_client_id
        ).first()
        if user:
            _ensure_synced_record(
                "PACIENTES",
                source_key,
                "User",
                user.pk,
                lab_client_id,
                sync_log,
            )
            counters["patients_updated"] += 1
            return user.pk

    # Create new patient.
    # Email is unique on User; if another patient already has this email
    # (common: spouses, family members sharing one address), drop the email
    # for the new row instead of failing the whole study import.
    email = fields.get("email")
    if email and User.objects.filter(email=email).exists():
        logger.info(
            "Patient email %s already taken — creating new patient with email=None",
            email,
        )
        email = None

    with transaction.atomic():
        user = User.objects.create_user(
            email=email,
            first_name=fields.get("first_name", ""),
            last_name=fields.get("last_name", ""),
            dni=fields.get("dni", ""),
            gender=fields.get("gender", ""),
            birthday=fields.get("birthday"),
            mutual_code=fields.get("mutual_code"),
            carnet=fields.get("carnet", ""),
            phone_number=fields.get("phone_number", ""),
            direction=fields.get("direction", ""),
            location=fields.get("location", ""),
            role="patient",
            is_active=True,
            is_verified=True,
            lab_client_id=lab_client_id,
        )
        _ensure_synced_record(
            "PACIENTES",
            source_key,
            "User",
            user.pk,
            lab_client_id,
            sync_log,
        )
        counters["patients_created"] += 1
        return user.pk


def _get_or_create_doctor(medico_row, lab_client_id, sync_log, counters):
    """Get or create a doctor User from a MEDICOS row. Returns User pk."""
    from apps.users.models import User

    source_key = str(medico_row["NUMERO_FLD"])
    fields = mappers.map_doctor(medico_row)
    matricula = fields.get("matricula", "")

    # Check SyncedRecord first
    existing = SyncedRecord.objects.filter(
        source_table="MEDICOS",
        source_key=source_key,
        lab_client_id=lab_client_id,
    ).first()

    if existing:
        user = User.objects.filter(pk=existing.target_uuid).first()
        if user:
            return user.pk

    # Try to match by matricula
    if matricula:
        user = User.objects.filter(matricula=matricula, role="doctor").first()
        if user:
            _ensure_synced_record(
                "MEDICOS",
                source_key,
                "User",
                user.pk,
                lab_client_id,
                sync_log,
            )
            return user.pk

    # Create new doctor
    with transaction.atomic():
        user = User.objects.create_user(
            email=fields.get("email"),
            first_name=fields.get("first_name", ""),
            last_name=fields.get("last_name", ""),
            matricula=matricula,
            phone_number=fields.get("phone_number", ""),
            role="doctor",
            is_active=True,
            is_verified=True,
            lab_client_id=lab_client_id,
        )
        _ensure_synced_record(
            "MEDICOS",
            source_key,
            "User",
            user.pk,
            lab_client_id,
            sync_log,
        )
        counters["doctors_created"] += 1
        return user.pk


def _get_or_create_practice(nomen_row, lab_client_id, sync_log, counters):
    """Get or create a Practice from a NOMEN row. Returns Practice pk."""
    from apps.studies.models import Practice

    abrev = nomen_row["ABREV_FLD"].strip()
    fields = mappers.map_practice(nomen_row)

    # Check by code first
    practice = Practice.objects.filter(code=abrev).first()
    if practice:
        return practice.pk

    # Create new practice
    with transaction.atomic():
        practice = Practice.objects.create(
            code=fields["code"],
            name=fields["name"],
            delay_days=fields["delay_days"],
            is_active=True,
        )
        _ensure_synced_record(
            "NOMEN",
            abrev,
            "Practice",
            practice.pk,
            lab_client_id,
            sync_log,
        )
        counters["practices_created"] += 1
        return practice.pk


def _create_minimal_practice(abrev, lab_client_id, sync_log, counters):
    """Create a minimal Practice when NOMEN data is unavailable."""
    from apps.studies.models import Practice

    practice = Practice.objects.filter(code=abrev).first()
    if practice:
        return practice.pk

    with transaction.atomic():
        practice = Practice.objects.create(
            code=abrev,
            name=abrev,
            is_active=True,
        )
        _ensure_synced_record(
            "NOMEN",
            abrev,
            "Practice",
            practice.pk,
            lab_client_id,
            sync_log,
        )
        counters["practices_created"] += 1
        return practice.pk


def _get_or_create_study_with_practices(
    numero,
    deters_rows,
    patient_pk,
    doctor_pk,
    practice_cache,
    lab_client_id,
    sync_log,
    counters,
    is_paid=True,
    is_validated=True,
):
    """Get or create a Study and its StudyPractice records for a protocol.

    Args:
        numero: LabWin NUMERO_FLD (protocol/order ID).
        deters_rows: List of DETERS row dicts for this protocol.
        patient_pk: UUID of the patient.
        doctor_pk: UUID of the doctor (or None).
        practice_cache: Dict mapping ABREV_FLD -> Practice pk.
        lab_client_id: Lab client ID.
        sync_log: Current SyncLog instance.
        counters: Dict of counters to update.
        is_paid: Computed by caller via mappers.map_is_paid(pac_row). Updated
                 on existing studies if it changed.
        is_validated: True for sync-imported studies (connector pre-filters
                      to VALIDADO_FLD='1' DETERS rows).

    Returns:
        Study pk.
    """
    from apps.studies.models import Study, StudyPractice

    # Use first row for dates (all rows in a protocol share the same date)
    first_row = deters_rows[0]
    study_fields = mappers.map_study(
        numero,
        patient_pk,
        doctor_pk,
        fecha=first_row.get("FECHA_FLD"),
        hora=first_row.get("HORA_FLD"),
        is_paid=is_paid,
        is_validated=is_validated,
    )
    protocol_number = study_fields["protocol_number"]

    # Check if study already exists
    study = Study.objects.filter(protocol_number=protocol_number).first()
    if study:
        # Study exists — sync mutable per-study flags first, then handle practices.
        # Re-imports must reflect the latest source state (e.g. patient paid
        # their bono between yesterday's and today's backup).
        flag_updates = []
        if study.is_paid != is_paid:
            study.is_paid = is_paid
            flag_updates.append("is_paid")
        if study.is_validated != is_validated:
            study.is_validated = is_validated
            flag_updates.append("is_validated")
        if flag_updates:
            flag_updates.append("updated_at")
            study.save(update_fields=flag_updates)
            counters["studies_updated"] += 1

        existing_codes = set(study.study_practices.values_list("code", flat=True))
        for row in deters_rows:
            abrev = row["ABREV_FLD"].strip()
            if abrev in existing_codes:
                # Update result if changed
                sp = study.study_practices.filter(code=abrev).first()
                if sp:
                    new_result = (row.get("RESULT_FLD") or "").strip()
                    if new_result and new_result != sp.result:
                        sp.result = new_result
                        sp.save(update_fields=["result", "updated_at"])
                        counters["studies_updated"] += 1
                continue

            practice_pk = practice_cache.get(abrev)
            if practice_pk:
                sp_fields = mappers.map_study_practice(row, practice_pk)
                StudyPractice.objects.create(
                    study=study,
                    **sp_fields,
                )
                counters["study_practices_created"] += 1

        return study.pk

    # Create new study + practices
    source_key = str(numero)

    with transaction.atomic():
        study = Study(
            protocol_number=protocol_number,
            patient_id=patient_pk,
            ordered_by_id=doctor_pk,
            status="completed",
            service_date=study_fields.get("service_date"),
            completed_at=study_fields.get("completed_at"),
            sample_id=study_fields.get("sample_id", ""),
            is_paid=study_fields.get("is_paid", True),
            is_validated=study_fields.get("is_validated", False),
            lab_client_id=lab_client_id,
        )
        study.save()

        # Create StudyPractice for each DETERS row
        for row in deters_rows:
            abrev = row["ABREV_FLD"].strip()
            practice_pk = practice_cache.get(abrev)
            if practice_pk:
                sp_fields = mappers.map_study_practice(row, practice_pk)
                StudyPractice.objects.create(
                    study=study,
                    **sp_fields,
                )
                counters["study_practices_created"] += 1

        _ensure_synced_record(
            "PACIENTES",
            source_key,
            "Study",
            study.pk,
            lab_client_id,
            sync_log,
        )
        counters["studies_created"] += 1
        return study.pk


def _ensure_synced_record(
    source_table, source_key, target_model, target_uuid, lab_client_id, sync_log
):
    """Create or update a SyncedRecord for deduplication tracking."""
    SyncedRecord.objects.update_or_create(
        source_table=source_table,
        source_key=source_key,
        lab_client_id=lab_client_id,
        defaults={
            "target_model": target_model,
            "target_uuid": target_uuid,
            "sync_log": sync_log,
        },
    )


@shared_task(bind=True, max_retries=3, time_limit=1800)
def fetch_ftp_pdfs(self, lab_client_id=None, delete_after_download=False):
    """Fetch PDF result files from FTP server and attach to matching studies.

    PDF filenames on the FTP server follow the pattern {NUMERO_FLD}.pdf.
    This matches Study.sample_id (which stores the raw NUMERO_FLD value).

    Args:
        lab_client_id: Lab client ID to filter studies.
            Defaults to LABWIN_DEFAULT_LAB_CLIENT_ID setting.
        delete_after_download: If True, delete PDFs from FTP after successful
            attachment to a study.

    Returns:
        dict: Summary with counts of matched, skipped, and failed files.
    """
    from apps.studies.models import Study

    if lab_client_id is None:
        lab_client_id = getattr(settings, "LABWIN_DEFAULT_LAB_CLIENT_ID", 1)

    task_id = ""
    try:
        task_id = self.request.id or ""
    except AttributeError:
        pass

    counters = {
        "files_found": 0,
        "files_matched": 0,
        "files_attached": 0,
        "files_skipped": 0,
        "files_deleted": 0,
    }
    errors = []

    try:
        with get_ftp_connector() as ftp:
            pdf_files = ftp.list_pdf_files()
            counters["files_found"] = len(pdf_files)

            logger.info("FTP: Found %d PDF files", len(pdf_files))

            for filename in pdf_files:
                try:
                    # Extract the protocol NUMERO from filename. The lab uses
                    # two formats:
                    #   {NUMERO}.pdf                          (legacy)
                    #   {NUMERO}-{DNI}-{NOMBRE}.pdf          (current export
                    #     format observed 2026-04-22; e.g. "220197-39592918-SIRI,FRANCO.pdf")
                    # The protocol number is always the first dash-separated
                    # segment (NUMERO is purely numeric, no dashes inside it).
                    name_without_ext = os.path.splitext(filename)[0]
                    protocol_numero = name_without_ext.split("-", 1)[0]

                    # Find matching study by sample_id (which holds NUMERO_FLD)
                    study = Study.objects.filter(
                        sample_id=protocol_numero,
                        lab_client_id=lab_client_id,
                    ).first()

                    if not study:
                        counters["files_skipped"] += 1
                        continue

                    counters["files_matched"] += 1

                    # Skip if study already has a results file
                    if study.results_file:
                        counters["files_skipped"] += 1
                        logger.debug(
                            "Study %s already has results file, skipping",
                            study.protocol_number,
                        )
                        if delete_after_download:
                            ftp.delete_file(filename)
                            counters["files_deleted"] += 1
                        continue

                    # Download and attach
                    content = ftp.download_file(filename)
                    study.results_file.save(
                        f"{study.protocol_number}.pdf",
                        ContentFile(content),
                        save=True,
                    )
                    counters["files_attached"] += 1
                    logger.info(
                        "Attached PDF %s to study %s",
                        filename,
                        study.protocol_number,
                    )

                    # Delete from FTP if requested
                    if delete_after_download:
                        ftp.delete_file(filename)
                        counters["files_deleted"] += 1

                except Exception as e:
                    logger.error("Error processing FTP file %s: %s", filename, e)
                    errors.append({"file": filename, "error": str(e)})

                # Update progress
                if task_id:
                    self.update_state(
                        state="PROCESSING",
                        meta={**counters, "errors": len(errors)},
                    )

        result = {
            "message": (
                f"FTP PDF fetch completed. "
                f"Found: {counters['files_found']}, "
                f"Attached: {counters['files_attached']}, "
                f"Skipped: {counters['files_skipped']}, "
                f"Errors: {len(errors)}."
            ),
            **counters,
            "error_count": len(errors),
            "errors": errors[-50:],
        }
        logger.info("FTP PDF fetch completed: %s", result["message"])
        return result

    except Exception as e:
        logger.exception("FTP PDF fetch failed: %s", e)
        if task_id:
            self.retry(exc=e, countdown=300 * (2**self.request.retries))
        raise


@shared_task(bind=True, max_retries=3, time_limit=1800)
def cleanup_ftp_pdfs(self, lab_client_id=None):
    """Remove PDFs from FTP server for studies that already have results_file.

    Scans the FTP server for PDF files and deletes any whose corresponding
    study already has a results_file attached. This is useful when
    delete_after_download=False was used during fetch_ftp_pdfs.

    Args:
        lab_client_id: Lab client ID to filter studies.

    Returns:
        dict: Summary with counts of deleted and skipped files.
    """
    from apps.studies.models import Study

    if lab_client_id is None:
        lab_client_id = getattr(settings, "LABWIN_DEFAULT_LAB_CLIENT_ID", 1)

    counters = {
        "files_found": 0,
        "files_deleted": 0,
        "files_kept": 0,
    }
    errors = []

    try:
        with get_ftp_connector() as ftp:
            pdf_files = ftp.list_pdf_files()
            counters["files_found"] = len(pdf_files)

            for filename in pdf_files:
                try:
                    name_without_ext = os.path.splitext(filename)[0]

                    # Check if study exists and has results_file
                    study = Study.objects.filter(
                        sample_id=name_without_ext,
                        lab_client_id=lab_client_id,
                    ).first()

                    if study and study.results_file:
                        ftp.delete_file(filename)
                        counters["files_deleted"] += 1
                        logger.info(
                            "Cleaned up FTP file %s (study %s already has PDF)",
                            filename,
                            study.protocol_number,
                        )
                    else:
                        counters["files_kept"] += 1

                except Exception as e:
                    logger.error("Error cleaning up FTP file %s: %s", filename, e)
                    errors.append({"file": filename, "error": str(e)})

        result = {
            "message": (
                f"FTP cleanup completed. "
                f"Found: {counters['files_found']}, "
                f"Deleted: {counters['files_deleted']}, "
                f"Kept: {counters['files_kept']}, "
                f"Errors: {len(errors)}."
            ),
            **counters,
            "error_count": len(errors),
        }
        logger.info("FTP cleanup completed: %s", result["message"])
        return result

    except Exception as e:
        logger.exception("FTP cleanup failed: %s", e)
        task_id = ""
        try:
            task_id = self.request.id or ""
        except AttributeError:
            pass
        if task_id:
            self.retry(exc=e, countdown=300 * (2**self.request.retries))
        raise


@shared_task(bind=True, max_retries=2, time_limit=7200)
def import_uploaded_backup(self, lab_client_id=None, explicit_file=None):
    """Restore latest backup from /srv/labwin_backups/incoming and trigger sync.

    Phase B of the LabWin backup pipeline. See LABWIN_BACKUP_PIPELINE.md.

    Thin wrapper around BackupImporter so the bulk of the logic stays
    test-friendly (BackupImporter has no Celery decoration).

    Args:
        lab_client_id: Lab client ID for synced records.
        explicit_file: Override discovery; restore this specific path instead.

    Returns:
        dict: BackupImportResult.as_dict() — status, sync_result, error, etc.
    """
    from pathlib import Path

    from apps.labwin_sync.services.backup_import import BackupImporter

    importer = BackupImporter(lab_client_id=lab_client_id)
    file_arg = Path(explicit_file) if explicit_file else None
    result = importer.run(explicit_file=file_arg)
    return result.as_dict()
