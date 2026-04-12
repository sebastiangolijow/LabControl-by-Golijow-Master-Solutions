"""
Celery task for syncing lab results from LabWin Firebird database.

Runs nightly via Celery Beat. Fetches validated DETERS rows incrementally,
maps them to LabControl models (User, Practice, Study), and tracks progress
in SyncLog/SyncedRecord for idempotency.
"""

import logging

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import mappers
from .connectors import get_connector
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
    from apps.studies.models import Practice, Study
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

                # Process each DETERS row
                for row in batch:
                    total_processed += 1
                    numero = row["NUMERO_FLD"]
                    abrev = row["ABREV_FLD"]

                    try:
                        # Ensure patient exists
                        if numero not in patient_cache:
                            pac_row = pacientes.get(numero)
                            if pac_row:
                                patient_pk = _get_or_create_patient(
                                    pac_row, lab_client_id, sync_log, counters
                                )
                                patient_cache[numero] = patient_pk
                            else:
                                # No patient data available, skip
                                errors.append(
                                    {
                                        "type": "study",
                                        "key": f"{numero}:{abrev}",
                                        "error": "No PACIENTES data for this NUMERO_FLD",
                                    }
                                )
                                continue

                        patient_pk = patient_cache.get(numero)
                        if not patient_pk:
                            continue

                        practice_pk = practice_cache.get(abrev)
                        if not practice_pk:
                            # Practice not in NOMEN, create a minimal one
                            practice_pk = _create_minimal_practice(
                                abrev, lab_client_id, sync_log, counters
                            )
                            practice_cache[abrev] = practice_pk

                        # Find doctor for this order
                        pac_row = pacientes.get(numero)
                        doctor_pk = None
                        if pac_row:
                            num_medico = pac_row.get("NUMMEDICO_FLD")
                            if num_medico:
                                doctor_pk = doctor_cache.get(num_medico)

                        # Create/update study
                        _get_or_create_study(
                            row,
                            patient_pk,
                            practice_pk,
                            doctor_pk,
                            lab_client_id,
                            sync_log,
                            counters,
                        )

                        # Track cursor
                        fecha = row.get("FECHA_FLD", "")
                        if fecha > max_fecha or (
                            fecha == max_fecha
                            and (max_numero is None or numero > max_numero)
                        ):
                            max_fecha = fecha
                            max_numero = numero

                    except Exception as e:
                        logger.error(
                            "Error processing DETERS %s:%s: %s", numero, abrev, e
                        )
                        errors.append(
                            {
                                "type": "study",
                                "key": f"{numero}:{abrev}",
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
            setattr(sync_log, key, val)
        sync_log.save()

        result = {
            "message": (
                f"Sync completed. Studies: {counters['studies_created']} created, "
                f"{counters['studies_updated']} updated. "
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

    # Create new patient
    with transaction.atomic():
        user = User.objects.create_user(
            email=fields.get("email"),
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


def _get_or_create_study(
    deters_row,
    patient_pk,
    practice_pk,
    doctor_pk,
    lab_client_id,
    sync_log,
    counters,
):
    """Get or create a Study from a DETERS row. Returns Study pk."""
    from apps.studies.models import Study

    fields = mappers.map_study(deters_row, patient_pk, practice_pk, doctor_pk)
    protocol_number = fields["protocol_number"]

    # Check by protocol_number (unique)
    study = Study.objects.filter(protocol_number=protocol_number).first()
    if study:
        # Update results if changed
        new_results = fields.get("results", "")
        if new_results and new_results != study.results:
            study.results = new_results
            study.save(update_fields=["results", "updated_at"])
            counters["studies_updated"] += 1
        return study.pk

    # Create new study
    source_key = f"{deters_row['NUMERO_FLD']}:{deters_row['ABREV_FLD']}"

    with transaction.atomic():
        study = Study(
            protocol_number=protocol_number,
            patient_id=patient_pk,
            practice_id=practice_pk,
            ordered_by_id=doctor_pk,
            status="completed",
            results=fields.get("results", ""),
            service_date=fields.get("service_date"),
            completed_at=fields.get("completed_at"),
            sample_id=fields.get("sample_id", ""),
            lab_client_id=lab_client_id,
        )
        study.save()

        _ensure_synced_record(
            "DETERS",
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
