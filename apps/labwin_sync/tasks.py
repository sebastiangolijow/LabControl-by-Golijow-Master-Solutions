"""
Celery tasks for syncing lab results from LabWin.

Tasks:
- sync_labwin_results: Nightly sync from LabWin Firebird database.
- fetch_ftp_pdfs: Fetch PDF result files from FTP server and attach to studies.
- cleanup_ftp_pdfs: Remove successfully processed PDFs from FTP server.
- import_uploaded_backup: Restore latest .fbk.gz backup and trigger sync (Phase B).
- cleanup_misplaced_uploads: Scrub stray .FDB / orphan PDF uploads on FTP.
  REMOVE-ONCE-LAB-FIXES-DUPLICATE-UPLOAD (see CLAUDE.md TODO).
"""

import logging
import os
from collections import defaultdict
from datetime import date, timedelta

from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.core.logging_utils import memory_summary

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

    # Drop any practice-layout cache from a previous run so we pick up
    # changes from sync_practice_layouts within the same worker process.
    _reset_practice_layout_cache()

    # Create sync log
    task_id = ""
    try:
        task_id = self.request.id or ""
    except AttributeError:
        pass

    logger.info(
        "sync_labwin_results START — lab_client_id=%s full_sync=%s batch_size=%s task_id=%s mock=%s | %s",
        lab_client_id,
        full_sync,
        batch_size,
        task_id or "<sync>",
        getattr(settings, "LABWIN_USE_MOCK", False),
        memory_summary(),
    )

    sync_log = SyncLog.objects.create(
        status="started",
        lab_client_id=lab_client_id,
        celery_task_id=task_id,
    )

    # Determine the date window for this sync.
    #
    # Single rolling window: every run re-imports DETERS where FECHA_FLD falls
    # within today - LABWIN_SYNC_WINDOW_DAYS (default 90, = the lab's max
    # study turnaround). The connector filters on FECHA_FLD (sample date),
    # not validation date — so a study that was sampled 60 days ago but only
    # validated yesterday gets picked up by today's sync. Re-imports are
    # idempotent (_get_or_create_study_with_practices updates is_paid,
    # is_validated, RESULT_FLD, and adds new StudyPractices).
    #
    # full_sync=True bypasses the window for one-off re-imports of all history.
    since_fecha = None
    since_numero = None

    if not full_sync:
        window_days = getattr(settings, "LABWIN_SYNC_WINDOW_DAYS", 90)
        window_start = date.today() - timedelta(days=window_days)
        since_fecha = window_start.strftime("%Y%m%d")
        # NUMERO_FLD is positive in real data; -1 makes the connector's
        # `FECHA_FLD = ? AND NUMERO_FLD > ?` comparison include every row on
        # the window-start date.
        since_numero = -1
        logger.info(
            "Sync window: fecha >= %s (last %d days)",
            since_fecha,
            window_days,
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
        "notifications_queued": 0,
        "emails_skipped": 0,
        "derivacion_skipped": 0,
        # Protocols where some DETERS rows are not yet VALIDADO_FLD='1' and
        # CARGADO_FLD='1'. We refuse to ingest until ALL rows are validated.
        # *_deleted counts protocols where we ALSO had to remove a stale
        # previously-fully-validated Study from our DB.
        "partial_validation_skipped": 0,
        "partial_validation_deleted": 0,
        # Protocols where the patient owes a bono (PACIENTES.DEBEBONO_FLD='1').
        # We refuse to ingest until the lab marks them paid, since the lab
        # also doesn't generate a PDF for unpaid protocols — they'd just
        # clutter the patient's results list with no usable artifact.
        # *_deleted counts protocols where we ALSO had to remove a stale
        # previously-paid Study from our DB.
        "unpaid_skipped": 0,
        "unpaid_deleted": 0,
    }

    # Notification batching state. We accumulate per-user lists during the sync
    # loop and dispatch one email per user at the end (so a patient with 5 new
    # studies gets 1 email, not 5). See _dispatch_patient_notifications.
    #
    # users_needing_password_setup: User pks that need the password-setup email
    #     this run — either created fresh from PACIENTES, or "DNI-revived"
    #     (user existed but email-less, and this sync brought their email).
    # studies_to_notify: {user_pk: [study_pk, ...]} for studies whose
    #     notification_sent_at is currently NULL (i.e. patient hasn't been
    #     emailed yet about this study). Includes both fresh-create and re-sync
    #     cases — the timestamp is the source of truth, not "did we create the
    #     study just now".
    users_needing_password_setup = set()
    studies_to_notify = defaultdict(list)

    total_processed = 0
    max_numero = since_numero
    max_fecha = since_fecha or ""

    batch_index = 0
    try:
        with get_connector() as connector:
            for batch in connector.fetch_validated_deters(
                since_fecha=since_fecha,
                since_numero=since_numero,
                batch_size=batch_size,
            ):
                if not batch:
                    continue
                batch_index += 1
                logger.info(
                    "sync_labwin batch #%d — %d DETERS rows (running total processed=%d, errors=%d)",
                    batch_index,
                    len(batch),
                    total_processed,
                    len(errors),
                )

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
                        logger.exception(
                            "sync_labwin: error creating practice abrev=%s (batch #%d)",
                            abrev,
                            batch_index,
                        )
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
                        logger.exception(
                            "sync_labwin: error creating doctor numero=%s (batch #%d)",
                            num,
                            batch_index,
                        )
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

                    # Skip partially-validated protocols. We only ingest a
                    # protocol once ALL of its practices are validated AND
                    # loaded in LabWin. If a protocol that previously WAS
                    # fully validated now has unvalidated rows (e.g. the
                    # lab unvalidated one of its practices), delete the
                    # existing Study from our DB so the patient stops
                    # seeing stale partial data.
                    if not mappers.is_protocol_fully_validated(rows):
                        counters["partial_validation_skipped"] = (
                            counters.get("partial_validation_skipped", 0) + 1
                        )
                        protocol_number = f"LW-{numero}"
                        deleted_count, _ = Study.objects.filter(
                            protocol_number=protocol_number
                        ).delete()
                        if deleted_count:
                            counters["partial_validation_deleted"] = (
                                counters.get("partial_validation_deleted", 0) + 1
                            )
                            logger.info(
                                "sync_labwin: deleted %s — became partially "
                                "validated in LabWin (%d rows in this batch)",
                                protocol_number,
                                len(rows),
                            )
                        continue

                    # Skip protocols where the patient owes the bono. The lab
                    # never produces a PDF for unpaid protocols, so importing
                    # them would just create an unfulfillable row in the
                    # patient's results list. If a previously-paid Study
                    # flipped to unpaid, delete it from our DB.
                    pac_row = pacientes.get(numero)
                    if not mappers.map_is_paid(pac_row):
                        counters["unpaid_skipped"] += 1
                        protocol_number = f"LW-{numero}"
                        deleted_count, _ = Study.objects.filter(
                            protocol_number=protocol_number
                        ).delete()
                        if deleted_count:
                            counters["unpaid_deleted"] += 1
                            logger.info(
                                "sync_labwin: deleted %s — patient owes bono "
                                "(DEBEBONO_FLD='1')",
                                protocol_number,
                            )
                        continue

                    try:
                        # Ensure patient exists
                        if numero not in patient_cache:
                            pac_row = pacientes.get(numero)
                            if pac_row:
                                # Skip "derivación" / "Sin Consigna" protocols.
                                # Per the lab, every patient with a real
                                # referring doctor has NUMMEDICO_FLD pointing
                                # at a real MEDICOS row; walk-ins / vet /
                                # internal studies are pointed at the "Sin
                                # Consigna" sentinel (NUMERO=175) or have
                                # NUMMEDICO_FLD=0. Both are not portal-
                                # eligible.
                                num_medico = pac_row.get("NUMMEDICO_FLD")
                                medico_row = (
                                    medicos.get(num_medico) if num_medico else None
                                )
                                if mappers.is_derivacion_doctor(num_medico, medico_row):
                                    counters["derivacion_skipped"] += 1
                                    # Cache as None so other batches that
                                    # reference the same NUMERO short-circuit.
                                    patient_cache[numero] = None
                                    continue
                                # Skip veterinary patients. Combined rule:
                                # dni='' AND (last_name starts with '167'
                                # OR any practice in this protocol is a
                                # vet practice). See mappers.is_pet_candidate.
                                # Kept as defense-in-depth — most vets are
                                # already caught by the derivación filter
                                # above (NUMMEDICO_FLD=0).
                                fields = mappers.map_patient(pac_row)
                                # Check if any DETERS row in this protocol
                                # maps to a vet practice (via NOMEN cache).
                                has_vet = False
                                for row in rows:
                                    abrev = row.get("ABREV_FLD", "").strip()
                                    nomen_row = nomens.get(abrev) if abrev else None
                                    if nomen_row and mappers.is_vet_practice(
                                        nomen_row.get("ABREV_FLD"),
                                        nomen_row.get("NOMBRE_FLD"),
                                    ):
                                        has_vet = True
                                        break
                                if mappers.is_pet_candidate(
                                    fields.get("first_name"),
                                    fields.get("last_name"),
                                    fields.get("dni"),
                                    has_vet_practice=has_vet,
                                ):
                                    counters.setdefault("pets_skipped", 0)
                                    counters["pets_skipped"] += 1
                                    # Mark cache as None so we don't
                                    # re-evaluate this NUMERO if it shows
                                    # up in another batch
                                    patient_cache[numero] = None
                                    continue
                                patient_pk, needs_password_setup = (
                                    _get_or_create_patient(
                                        pac_row, lab_client_id, sync_log, counters
                                    )
                                )
                                patient_cache[numero] = patient_pk
                                if needs_password_setup:
                                    users_needing_password_setup.add(patient_pk)
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
                        # is_validated=True because we only reach this code path
                        # for protocols where ALL DETERS rows have
                        # VALIDADO_FLD='1' AND CARGADO_FLD='1' (gate above —
                        # see is_protocol_fully_validated).
                        is_paid = mappers.map_is_paid(pac_row)

                        # Patient sex + DOB feed per-study VALNOR resolution
                        # (each StudyPractice gets its own resolved reference
                        # ranges based on patient demographics).
                        patient_sex = pac_row.get("SEXO_FLD")
                        patient_dob_raw = pac_row.get("FNACIM_FLD")

                        # Create/update study and its practices
                        study_pk = _get_or_create_study_with_practices(
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
                            patient_sex=patient_sex,
                            patient_dob_raw=patient_dob_raw,
                            # Fallback for protocols where DETERS rows
                            # have FECHA_FLD=None (older data — see
                            # _get_or_create_study_with_practices).
                            paciente_fecha=pac_row.get("FECHA_FLD") if pac_row else None,
                            paciente_hora=pac_row.get("HORA_FLD") if pac_row else None,
                        )

                        # Queue this study for patient notification if we
                        # haven't notified them yet about it. The DB flag
                        # (Study.notification_sent_at) is the source of truth,
                        # so re-syncs (rolling 2-day window) don't re-notify.
                        if study_pk and patient_pk:
                            from apps.studies.models import Study as _Study

                            already_notified = (
                                _Study.objects.filter(pk=study_pk)
                                .exclude(notification_sent_at=None)
                                .exists()
                            )
                            if not already_notified:
                                studies_to_notify[patient_pk].append(study_pk)

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
                        logger.exception(
                            "sync_labwin: error processing protocol numero=%s "
                            "(batch #%d, %d DETERS rows in this protocol)",
                            numero,
                            batch_index,
                            len(rows),
                        )
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

        # Dispatch patient notifications. One email per patient (batched even
        # if they have N new studies in this run). Marks Study.notification_sent_at
        # so the rolling-window re-sync tomorrow won't re-notify.
        if studies_to_notify:
            queued, skipped = _dispatch_patient_notifications(
                studies_to_notify=studies_to_notify,
                users_needing_password_setup=users_needing_password_setup,
            )
            counters["notifications_queued"] = queued
            counters["emails_skipped"] = skipped
            logger.info(
                "sync_labwin: queued %d patient notifications, "
                "skipped %d (DISABLE_PATIENT_EMAILS or no email) "
                "(%d total studies across %d patients)",
                queued,
                skipped,
                sum(len(v) for v in studies_to_notify.values()),
                len(studies_to_notify),
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
        logger.info(
            "sync_labwin_results SUMMARY — "
            "patients_created=%d patients_updated=%d "
            "studies_created=%d studies_updated=%d study_practices_created=%d "
            "doctors_created=%d practices_created=%d "
            "notifications_queued=%d emails_skipped=%d "
            "derivacion_skipped=%d "
            "partial_validation_skipped=%d partial_validation_deleted=%d "
            "unpaid_skipped=%d unpaid_deleted=%d "
            "errors=%d batches=%d | %s",
            counters.get("patients_created", 0),
            counters.get("patients_updated", 0),
            counters.get("studies_created", 0),
            counters.get("studies_updated", 0),
            counters.get("study_practices_created", 0),
            counters.get("doctors_created", 0),
            counters.get("practices_created", 0),
            counters.get("notifications_queued", 0),
            counters.get("emails_skipped", 0),
            counters.get("derivacion_skipped", 0),
            counters.get("partial_validation_skipped", 0),
            counters.get("partial_validation_deleted", 0),
            counters.get("unpaid_skipped", 0),
            counters.get("unpaid_deleted", 0),
            len(errors),
            batch_index,
            memory_summary(),
        )
        logger.info(
            "sync_labwin_results END — %s | batches=%d | %s",
            result["message"],
            batch_index,
            memory_summary(),
        )
        return result

    except Exception as e:
        logger.exception(
            "sync_labwin_results FAILED at batch #%d (processed=%d, errors=%d) — %s",
            batch_index,
            total_processed,
            len(errors),
            memory_summary(),
        )
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
    """Get or create a patient User from a PACIENTES row.

    Patients imported from LabWin are always created INACTIVE
    (is_active=False, is_verified=False). They activate themselves by
    clicking the password-setup link in the email we send (handled by
    SetPasswordView, which flips both flags and creates the allauth
    EmailAddress row).

    Patients without email at import time stay inactive indefinitely; if a
    later sync brings an email for that DNI, the "DNI revival" branch below
    writes it and the caller treats them like a fresh-create so they get
    the password-setup email.

    Returns:
        (user_pk, needs_password_setup): Tuple of the User's pk and a flag
        indicating whether to send the password-setup email this run.
            needs_password_setup=False → "your study is now available" email
                (the user already has a working portal account)
            needs_password_setup=True  → "set up your password" email
                (only sent if the user has an email at this point)
    """
    from apps.users.models import User

    source_key = str(pac_row["NUMERO_FLD"])
    fields = mappers.map_patient(pac_row)
    new_email = fields.get("email")

    # Check SyncedRecord first — we previously imported this PACIENTES row.
    existing = SyncedRecord.objects.filter(
        source_table="PACIENTES",
        source_key=source_key,
        lab_client_id=lab_client_id,
    ).first()

    if existing:
        user = User.objects.filter(pk=existing.target_uuid).first()
        if user:
            return _refresh_existing_patient(user, fields, new_email, counters)
        # SyncedRecord exists but user was deleted — fall through to create

    # Try to match by DNI — User may exist from manual signup or earlier sync
    # (where we didn't yet have a SyncedRecord — e.g. user signed up first,
    # then their PACIENTES row landed in a sync).
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
            return _refresh_existing_patient(user, fields, new_email, counters)

    # Create new patient. ALWAYS inactive — the user proves email control by
    # clicking the password-setup link.
    #
    # Email collision: another patient already has this email (common for
    # family members sharing an address). Drop it; they stay imported but
    # without an email, awaiting the QR/manual-claim flow.
    email = new_email
    if email and User.objects.filter(email=email).exists():
        logger.warning(
            "patient email collision — creating new patient with email=None: "
            "email=%s dni=%s lab_client_id=%s",
            email,
            fields.get("dni") or "<none>",
            lab_client_id,
        )
        email = None

    with transaction.atomic():
        user = User.objects.create_user(
            email=email,
            first_name=fields.get("first_name", ""),
            last_name=fields.get("last_name", ""),
            dni=fields.get("dni", ""),
            # Sync sets biological_sex (sourced from SEXO_FLD via the
            # mapper). User.gender stays empty — that's the patient's
            # self-declared identity, only set via registration / profile.
            biological_sex=fields.get("biological_sex", ""),
            birthday=fields.get("birthday"),
            mutual_code=fields.get("mutual_code"),
            carnet=fields.get("carnet", ""),
            phone_number=fields.get("phone_number", ""),
            direction=fields.get("direction", ""),
            location=fields.get("location", ""),
            role="patient",
            is_active=False,
            is_verified=False,
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

        if email:
            logger.info(
                "patient created: user_pk=%s dni=%s email=%s lab_client_id=%s",
                user.pk,
                user.dni or "<none>",
                email,
                lab_client_id,
            )
        else:
            # Hot data-quality signal — surfaces in `make logs-prod-errors`
            # so the lab can see how many PACIENTES rows are emailless.
            logger.warning(
                "patient created without email — cannot send activation: "
                "user_pk=%s dni=%s name=%s lab_client_id=%s",
                user.pk,
                user.dni or "<none>",
                f"{user.first_name} {user.last_name}".strip() or "<none>",
                lab_client_id,
            )

        # Only send password-setup if we actually saved an email. Patients
        # without email wait for a future sync that brings one (DNI revival)
        # OR for the QR/manual-claim flow.
        needs_setup = bool(email)
        return user.pk, needs_setup


def _refresh_existing_patient(user, fields, new_email, counters):
    """Update mutable fields on a patient that already exists in Postgres.

    Returns:
        (user_pk, needs_password_setup) tuple, same contract as
        _get_or_create_patient.

    The needs_password_setup flag is True only in the DNI-revival case:
    the existing user has no email AND PACIENTES is now bringing one. In
    that case we write the email, leave is_active=False (still hasn't
    proven control), and route them through the password-setup flow.
    """
    update_fields = []

    # DNI revival: existing user is email-less and PACIENTES has an email
    # this time around. Write it (if it's not taken by someone else) and
    # treat the user like a fresh-create for notification purposes.
    needs_setup = False
    if not user.email and new_email:
        from apps.users.models import User

        if User.objects.filter(email=new_email).exclude(pk=user.pk).exists():
            logger.info(
                "DNI revival skipped: email %s for user pk=%s already taken by another user",
                new_email,
                user.pk,
            )
        else:
            user.email = new_email
            update_fields.append("email")
            needs_setup = True
            logger.info(
                "DNI revival: writing email for user pk=%s — will queue password-setup",
                user.pk,
            )

    # Routine field refresh from the latest PACIENTES snapshot.
    # NOTE: `gender` is deliberately NOT in this list — it's the patient's
    # self-declared identity and sync must never overwrite it. Biological
    # sex (sourced from SEXO_FLD) is a separate, sync-owned field.
    for field_name in [
        "phone_number",
        "direction",
        "location",
        "carnet",
        "biological_sex",
    ]:
        new_val = fields.get(field_name)
        if new_val and new_val != getattr(user, field_name, ""):
            setattr(user, field_name, new_val)
            update_fields.append(field_name)

    if update_fields:
        user.save(update_fields=update_fields)
        counters["patients_updated"] += 1

    return user.pk, needs_setup


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

    # Fallback: match by case-insensitive first+last name. Catches doctors
    # imported via the doctor-CSV bootstrap (where matricula was set to
    # NUMERO_FLD) when MEDICOS row exposes a different matricula source.
    first_name = fields.get("first_name", "")
    last_name = fields.get("last_name", "")
    if first_name and last_name:
        user = User.objects.filter(
            first_name__iexact=first_name,
            last_name__iexact=last_name,
            role="doctor",
        ).first()
        if user:
            # Backfill matricula if the existing row is missing it.
            if matricula and not user.matricula:
                user.matricula = matricula
                user.save(update_fields=["matricula", "updated_at"])
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


# ---------------------------------------------------------------------------
# Per-study VALNOR resolution helpers
# ---------------------------------------------------------------------------

# Lazy cache from Practice pk -> result_layout dict, populated on demand
# during a single sync run. Cleared at the start of each task invocation
# (see _reset_practice_layout_cache, called by sync_labwin_results).
_PRACTICE_LAYOUT_CACHE: dict[str, object] = {}


def _reset_practice_layout_cache():
    """Drop cached layouts. Call at the start of each sync run so a long-lived
    Celery worker doesn't keep stale data after Practice.result_layout changes."""
    _PRACTICE_LAYOUT_CACHE.clear()


def _practice_layout_cache_get(practice_pk):
    """Return Practice.result_layout for a given pk, caching the lookup."""
    if practice_pk in _PRACTICE_LAYOUT_CACHE:
        return _PRACTICE_LAYOUT_CACHE[practice_pk]
    from apps.studies.models import Practice

    layout = (
        Practice.objects.filter(pk=practice_pk)
        .values_list("result_layout", flat=True)
        .first()
    )
    _PRACTICE_LAYOUT_CACHE[practice_pk] = layout
    return layout


def _patient_age_days_for_sync(dob_raw, fecha_raw):
    """Convert LabWin FNACIM_FLD + FECHA_FLD into age-at-sample in days.

    Both fields are YYYYMMDD strings (or ints) in the LabWin DB. Returns None
    if either is missing or unparseable — the valnor resolver then falls back
    to age-agnostic matching.
    """
    from datetime import date

    def _parse(raw):
        if raw is None:
            return None
        s = str(raw).strip()
        if not s or len(s) != 8 or not s.isdigit():
            return None
        try:
            return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        except ValueError:
            return None

    dob = _parse(dob_raw)
    fecha = _parse(fecha_raw)
    if not dob or not fecha:
        return None
    delta = (fecha - dob).days
    return delta if delta >= 0 else None


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
    patient_sex=None,
    patient_dob_raw=None,
    paciente_fecha=None,
    paciente_hora=None,
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
        is_validated: True for sync-imported studies (caller has already
                      verified via is_protocol_fully_validated() that ALL
                      DETERS rows for this NUMERO have VALIDADO_FLD='1'
                      AND CARGADO_FLD='1').
        patient_sex: LabWin SEXO_FLD (1=M, 2=F, 0=any). Used for VALNOR
                     resolution on each StudyPractice.
        patient_dob_raw: LabWin FNACIM_FLD (YYYYMMDD string or int). Used to
                         compute age-at-sample for VALNOR resolution.

    Returns:
        Study pk.
    """
    from apps.labwin_sync.services.practice_layout import resolve_valnor_for_patient
    from apps.studies.models import Practice, Study, StudyPractice

    # Use first DETERS row for dates (all rows in a protocol share the
    # same date in modern data). For OLD protocols the lab didn't
    # always backfill DETERS.FECHA_FLD — those rows have None, and the
    # source of truth becomes PACIENTES.FECHA_FLD which the caller
    # passes via paciente_fecha. UAT 2026-05-12 found LW-198689 from
    # 2022 with NULL DETERS.FECHA_FLD; without this fallback the Study
    # landed with solicited_date=NULL and the frontend rendered
    # "1 de enero de 1970" (Date(undefined)).
    first_row = deters_rows[0]
    fecha = first_row.get("FECHA_FLD") or paciente_fecha
    hora = first_row.get("HORA_FLD") or paciente_hora
    study_fields = mappers.map_study(
        numero,
        patient_pk,
        doctor_pk,
        fecha=fecha,
        hora=hora,
        is_paid=is_paid,
        is_validated=is_validated,
    )
    protocol_number = study_fields["protocol_number"]

    # Resolve patient age once, used by every StudyPractice's VALNOR pick.
    # We use the sample date (study service_date) as the reference, not "today",
    # so historical re-syncs reproduce the same V.R. as on the original day.
    patient_age_days = _patient_age_days_for_sync(
        patient_dob_raw, first_row.get("FECHA_FLD")
    )

    def _resolve_valnor(practice_pk):
        """Compute resolved_valnor JSON for a (practice, this patient) pair."""
        if practice_pk is None:
            return None
        layout = _practice_layout_cache_get(practice_pk)
        if layout is None:
            return None
        resolved = resolve_valnor_for_patient(layout, patient_sex, patient_age_days)
        return resolved or None  # Drop empty dict so Postgres stores NULL

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
        # Backfill ordered_by ONLY when currently NULL. We never overwrite an
        # already-linked doctor (which may have been corrected manually).
        # This catches the historical case where the connector silently dropped
        # most MEDICOS rows via the buggy PRV_DELETEDRECORD_FLD filter — once
        # that filter is gone, re-syncs link the doctor on previously orphaned
        # studies.
        if doctor_pk and study.ordered_by_id is None:
            study.ordered_by_id = doctor_pk
            flag_updates.append("ordered_by")
        # Backfill solicited_date from the latest mapper output. Previously
        # this field was never written; the frontend was inferring it from
        # Study.created_at (= sync ingest time) which produced impossible
        # "completed before solicited" rows. Always trust the FECHA_FLD-
        # derived value from the mapper since LabWin is the source of truth.
        new_solicited = study_fields.get("solicited_date")
        if new_solicited and study.solicited_date != new_solicited:
            study.solicited_date = new_solicited
            flag_updates.append("solicited_date")
        # Clear completed_at if it was previously written from FECHA_FLD
        # (pre-2026-05-08 behavior). LabWin doesn't expose a real validation
        # timestamp on DETERS, so we leave this null and the frontend reads
        # Study.created_at for "Completado".
        if study.completed_at is not None:
            study.completed_at = None
            flag_updates.append("completed_at")
        if flag_updates:
            flag_updates.append("updated_at")
            study.save(update_fields=flag_updates)
            counters["studies_updated"] += 1

        existing_codes = set(study.study_practices.values_list("code", flat=True))
        for row in deters_rows:
            abrev = row["ABREV_FLD"].strip()
            if abrev in existing_codes:
                # Update result + resolved_valnor if either changed
                sp = study.study_practices.filter(code=abrev).first()
                if sp:
                    update_fields = []
                    new_result = (row.get("RESULT_FLD") or "").strip()
                    if new_result and new_result != sp.result:
                        sp.result = new_result
                        update_fields.append("result")
                    new_valnor = _resolve_valnor(sp.practice_id)
                    if new_valnor != sp.resolved_valnor:
                        sp.resolved_valnor = new_valnor
                        update_fields.append("resolved_valnor")
                    if update_fields:
                        update_fields.append("updated_at")
                        sp.save(update_fields=update_fields)
                        counters["studies_updated"] += 1
                continue

            practice_pk = practice_cache.get(abrev)
            if practice_pk:
                sp_fields = mappers.map_study_practice(row, practice_pk)
                sp_fields["resolved_valnor"] = _resolve_valnor(practice_pk)
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
            solicited_date=study_fields.get("solicited_date"),
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
                sp_fields["resolved_valnor"] = _resolve_valnor(practice_pk)
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
        logger.info(
            "study created: pk=%s protocol=%s patient_pk=%s practices=%d "
            "is_paid=%s is_validated=%s",
            study.pk,
            study.protocol_number,
            patient_pk,
            len(deters_rows),
            study.is_paid,
            study.is_validated,
        )
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


def _dispatch_patient_notifications(studies_to_notify, users_needing_password_setup):
    """Queue patient notification emails for studies imported in this sync.

    One email per patient, batched across all their new studies. Updates
    Study.notification_sent_at so re-imports under the rolling window won't
    re-notify.

    Two routes:
      A. Patient is in users_needing_password_setup (fresh-create or
         DNI-revival) AND has an email → "set up your password" email.
         Their account is is_active=False until they click the link.
      B. Patient is already active (existed before, or set up password
         on a previous run) AND has an email → batched "your N studies
         are available" email.

    Patients without email get nothing — their studies stay
    notification_sent_at=NULL so a future sync that brings an email
    (DNI-revival branch in _refresh_existing_patient) catches them.

    Kill switch: when settings.DISABLE_PATIENT_EMAILS is True the .delay()
    calls are short-circuited but Study.notification_sent_at is still set
    so the same studies aren't queued forever during test runs.

    Args:
        studies_to_notify: dict {user_pk: [study_pk, ...]}
        users_needing_password_setup: set of user_pks that should get the
            password-setup email this run

    Returns:
        (queued, skipped) — counts of emails actually queued vs skipped
        (skipped covers both the no-email case and DISABLE_PATIENT_EMAILS).
    """
    from apps.notifications.tasks import (
        send_password_setup_email,
        send_studies_available_email,
    )
    from apps.studies.models import Study
    from apps.users.models import User

    queued = 0
    skipped = 0
    now = timezone.now()
    user_ids = list(studies_to_notify.keys())
    disable_emails = getattr(settings, "DISABLE_PATIENT_EMAILS", False)
    allowlist_domains = getattr(settings, "PATIENT_EMAIL_ALLOWLIST_DOMAINS", [])

    # Single query to get email for all candidate users
    users = {u.pk: u for u in User.objects.filter(pk__in=user_ids).only("pk", "email")}

    for user_pk, study_pks in studies_to_notify.items():
        user = users.get(user_pk)
        if user is None or not user.email:
            # No email → can't notify. Leave Study.notification_sent_at NULL
            # so a future sync (after PACIENTES brings an email via the
            # DNI-revival branch) can re-attempt.
            logger.info(
                "skip notify user pk=%s: no email (studies pending=%d)",
                user_pk,
                len(study_pks),
            )
            skipped += 1
            continue

        kind = (
            "password_setup"
            if user_pk in users_needing_password_setup
            else "studies_available"
        )

        # Allowlist bypass: when DISABLE_PATIENT_EMAILS is on but the
        # user's email domain is whitelisted (e.g. lab staff testing the
        # patient UX with @labmolecular.com.ar accounts), still queue the
        # email. Falls through to the normal queue path below.
        domain = user.email.rsplit("@", 1)[-1].lower() if "@" in user.email else ""
        is_allowlisted = bool(allowlist_domains) and domain in allowlist_domains

        if disable_emails and not is_allowlisted:
            # Mark studies as notified anyway so the rolling window doesn't
            # re-queue them every run during test mode.
            Study.objects.filter(pk__in=study_pks).update(
                notification_sent_at=now,
                updated_at=now,
            )
            skipped += 1
            logger.info(
                "DISABLE_PATIENT_EMAILS=True — skipped %s for user pk=%s (studies=%d)",
                kind,
                user_pk,
                len(study_pks),
            )
            continue

        try:
            if kind == "password_setup":
                # Fresh-create or DNI-revival — send password-setup invite.
                # User is is_active=False until they click the link.
                send_password_setup_email.delay(str(user_pk))
                logger.info(
                    "queued password_setup email for user pk=%s (studies=%d)",
                    user_pk,
                    len(study_pks),
                )
            else:
                # Already-active user — batched "you have N new studies".
                send_studies_available_email.delay(
                    str(user_pk), [str(pk) for pk in study_pks]
                )
                logger.info(
                    "queued studies_available email for user pk=%s (studies=%d)",
                    user_pk,
                    len(study_pks),
                )

            # Mark these studies as notified. Done in bulk per user to keep
            # the SQL footprint small even when one patient has many studies.
            Study.objects.filter(pk__in=study_pks).update(
                notification_sent_at=now,
                updated_at=now,
            )
            queued += 1
        except Exception:
            # Email dispatch failure shouldn't fail the whole sync. The
            # studies stay un-notified (notification_sent_at=NULL) so the
            # next sync retries.
            logger.exception(
                "failed to queue notification for user pk=%s "
                "(studies=%d) — will retry on next sync",
                user_pk,
                len(study_pks),
            )

    return queued, skipped


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

    logger.info(
        "fetch_ftp_pdfs START — lab_client_id=%s delete_after_download=%s task_id=%s mock=%s | %s",
        lab_client_id,
        delete_after_download,
        task_id or "<sync>",
        getattr(settings, "LABWIN_FTP_USE_MOCK", False),
        memory_summary(),
    )

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
                    logger.exception(
                        "fetch_ftp_pdfs: error processing FTP file %s", filename
                    )
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
        logger.info("fetch_ftp_pdfs END — %s | %s", result["message"], memory_summary())
        return result

    except Exception as e:
        logger.exception(
            "fetch_ftp_pdfs FAILED (counters=%s errors=%d) — %s",
            counters,
            len(errors),
            memory_summary(),
        )
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
                    # Filenames are {NUMERO}-{DNI}-{NAME}.pdf — the protocol
                    # number is the first dash-separated segment. Must match
                    # the parser used in fetch_ftp_pdfs above; otherwise
                    # this task matches nothing and PDFs accumulate on FTP
                    # forever (was the bug pre-2026-05-11 — files_deleted
                    # was 0 every Sunday because we passed the full
                    # basename to sample_id=).
                    name_without_ext = os.path.splitext(filename)[0]
                    protocol_numero = name_without_ext.split("-", 1)[0]

                    # Check if study exists and has results_file
                    study = Study.objects.filter(
                        sample_id=protocol_numero,
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
                    logger.exception(
                        "cleanup_ftp_pdfs: error cleaning up file %s", filename
                    )
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

    task_id = ""
    try:
        task_id = self.request.id or ""
    except AttributeError:
        pass

    logger.info(
        "import_uploaded_backup START — lab_client_id=%s explicit_file=%s task_id=%s | %s",
        lab_client_id,
        explicit_file,
        task_id or "<sync>",
        memory_summary(),
    )

    importer = BackupImporter(lab_client_id=lab_client_id)
    file_arg = Path(explicit_file) if explicit_file else None
    try:
        result = importer.run(explicit_file=file_arg)
    except Exception:
        # BackupImporter handles its own errors and returns a result, but
        # an unexpected raise here means something exploded outside its
        # try/finally — make sure the traceback ends up in docker logs.
        logger.exception(
            "import_uploaded_backup: unexpected error escaped BackupImporter | %s",
            memory_summary(),
        )
        raise

    payload = result.as_dict()
    logger.info(
        "import_uploaded_backup END — status=%s backup=%s error=%s | %s",
        payload.get("status"),
        payload.get("backup_filename"),
        payload.get("error"),
        memory_summary(),
    )
    return payload


# REMOVE-ONCE-LAB-FIXES-DUPLICATE-UPLOAD: see CLAUDE.md TODO. Defends against
# the lab pushing nightly .FDB files via FTP into /results/ and orphan PDFs
# into the chroot root. Beat schedule runs at 03:50 (10 min before the
# expected fetch_ftp_pdfs slot).
@shared_task(bind=True, max_retries=2)
def cleanup_misplaced_uploads(self):
    """Scrub stray .FDB / orphan PDF uploads from the LabWin FTP."""
    from apps.labwin_sync.management.commands.cleanup_misplaced_fdb import (
        cleanup_misplaced_uploads as _run,
    )

    logger.info("cleanup_misplaced_uploads START | %s", memory_summary())
    try:
        result = _run(dry_run=False)
    except Exception:
        logger.exception("cleanup_misplaced_uploads FAILED | %s", memory_summary())
        raise

    logger.info(
        "cleanup_misplaced_uploads END — deleted=%d moved=%d bytes_freed=%d "
        "errors=%d | %s",
        len(result["deleted"]),
        len(result["moved"]),
        result["bytes_freed"],
        len(result["errors"]),
        memory_summary(),
    )
    return result


# ---------------------------------------------------------------------------
# On-demand protocol import (admin types a NUMERO into the UI)
# ---------------------------------------------------------------------------


# Outcome enum the task returns. The frontend ImportProtocolModal branches
# on these to render distinct messages — keep the strings in sync with the
# `results.import_modal.outcomes.*` i18n keys in es.yaml.
IMPORT_OUTCOME_IMPORTED = "imported"
IMPORT_OUTCOME_ALREADY_IMPORTED = "already_imported"
IMPORT_OUTCOME_NOT_FOUND = "not_found"
IMPORT_OUTCOME_PARTIAL = "partial_validation"
IMPORT_OUTCOME_UNPAID = "unpaid_skipped"
IMPORT_OUTCOME_DERIVACION = "derivacion_skipped"
IMPORT_OUTCOME_PET = "pet_skipped"
IMPORT_OUTCOME_LOCKED = "already_importing"


@shared_task(bind=True, max_retries=0, time_limit=120)
def import_protocol_by_numero(self, numero, lab_client_id=None, force=False):
    """Fetch ONE protocol from Firebird by NUMERO_FLD and ingest it.

    Used when an admin needs to import an old study (older than the
    nightly 90-day window) — patient calls in asking for a study from
    8 months ago, admin types the protocol number into the UI, this
    task pulls it from the local Firebird container and runs it through
    the same mappers and skip-filters as the nightly sync. Patient
    notification fires on success (same _dispatch_patient_notifications
    path, so DISABLE_PATIENT_EMAILS / PATIENT_EMAIL_ALLOWLIST_DOMAINS
    apply unchanged).

    The local Firebird container holds the lab's full DB since 2011,
    so any historical NUMERO is reachable. `not_found` always means
    "typo / wrong number," never "older than backup."

    max_retries=0: outcome-driven failures are non-transient (re-firing
    would duplicate emails / work). Connection-level failures bubble.

    Args:
        numero: LabWin NUMERO_FLD (positive integer).
        lab_client_id: Defaults to LABWIN_DEFAULT_LAB_CLIENT_ID.
        force: When True, BYPASS the derivacion_skipped filter only.
            UAT 2026-05-12: lab needs to import old studies whose
            NUMMEDICO_FLD is the "Sin Consigna" sentinel (175) — those
            are walk-in patients who still want their results. The
            study lands without an ordered_by doctor (doctor_pk=None,
            same as a doctor-less nightly-sync row). Other filters
            (partial_validation / unpaid / pet / already_imported)
            still apply — those have data-quality reasons behind them.

    Returns:
        Dict with `outcome` field plus outcome-specific fields. The API
        layer / management command pretty-print the dict; the frontend
        modal switches on `outcome` to render a result card. Possible
        outcomes (constants above):

          - imported           — Study created, see study_uuid + names
          - already_imported   — Study already in DB, see study_uuid
          - not_found          — NUMERO doesn't exist in Firebird
          - partial_validation — see pending_practices list
          - unpaid_skipped     — patient owes the bono
          - derivacion_skipped — no real referring doctor (try force=True)
          - pet_skipped        — vet patient
          - already_importing  — concurrency lock held by another task
    """
    from django.core.cache import cache

    from apps.studies.models import Study

    if lab_client_id is None:
        lab_client_id = getattr(settings, "LABWIN_DEFAULT_LAB_CLIENT_ID", 1)

    try:
        numero = int(numero)
    except (TypeError, ValueError):
        return {"outcome": IMPORT_OUTCOME_NOT_FOUND, "numero": numero}

    task_id = self.request.id if hasattr(self, "request") else None
    logger.info(
        "import_protocol_by_numero START — numero=%s lab_client_id=%s task_id=%s | %s",
        numero,
        lab_client_id,
        task_id or "<sync>",
        memory_summary(),
    )

    # SyncLog: tag with backup_filename = "on-demand:LW-{numero}" so it's
    # filterable in admin (no migration; field is a CharField on the
    # existing model).
    sync_log = SyncLog.objects.create(
        status="started",
        lab_client_id=lab_client_id,
        celery_task_id=task_id,
        backup_filename=f"on-demand:LW-{numero}",
    )

    # Concurrency lock — two admins clicking submit simultaneously, or a
    # rage-clicked button. cache.add returns False if the key already
    # exists. 180s TTL covers worst-case task time (limit is 120s).
    lock_key = f"labwin:on-demand:{numero}"
    if not cache.add(lock_key, task_id or "sync", timeout=180):
        sync_log.status = "failed"
        sync_log.completed_at = timezone.now()
        sync_log.errors = [{"type": "lock", "error": "another import in progress"}]
        sync_log.error_count = 1
        sync_log.save()
        logger.info(
            "import_protocol_by_numero LOCKED — numero=%s (another task holds the lock)",
            numero,
        )
        return {"outcome": IMPORT_OUTCOME_LOCKED, "numero": numero}

    counters = {
        "patients_created": 0,
        "patients_updated": 0,
        "doctors_created": 0,
        "doctors_updated": 0,
        "practices_created": 0,
        "studies_created": 0,
        "studies_updated": 0,
        "study_practices_created": 0,
        "notifications_queued": 0,
        "emails_skipped": 0,
        "derivacion_skipped": 0,
        "partial_validation_skipped": 0,
        "partial_validation_deleted": 0,
        "unpaid_skipped": 0,
        "unpaid_deleted": 0,
        "pets_skipped": 0,
    }

    def _finalize(outcome, **extra):
        """Write SyncLog + release lock + return the result dict."""
        cache.delete(lock_key)
        sync_log.completed_at = timezone.now()
        if outcome == IMPORT_OUTCOME_IMPORTED:
            sync_log.status = "completed"
        elif outcome == IMPORT_OUTCOME_ALREADY_IMPORTED:
            sync_log.status = "completed"
        else:
            sync_log.status = "failed"
            sync_log.errors = [{"type": "outcome", "error": outcome}]
            sync_log.error_count = 1
        for key, val in counters.items():
            if hasattr(sync_log, key):
                setattr(sync_log, key, val)
        sync_log.save()
        result = {"outcome": outcome, "numero": numero, **extra}
        logger.info(
            "import_protocol_by_numero END — numero=%s outcome=%s | %s",
            numero,
            outcome,
            memory_summary(),
        )
        return result

    try:
        with get_connector() as connector:
            data = connector.fetch_one_protocol(numero)

        if data is None:
            return _finalize(IMPORT_OUTCOME_NOT_FOUND)

        deters = data["deters"]
        paciente = data["paciente"]
        medico = data["medico"]
        nomens = data["nomens"]

        # Already-imported: refuse, return existing UUID. Updates belong
        # to the nightly sync path (and the existing study's data is
        # likely fresher anyway since it was synced before this on-demand
        # request even fired).
        protocol_number = f"LW-{numero}"
        existing_study = (
            Study.objects.filter(protocol_number=protocol_number).only("uuid").first()
        )
        if existing_study:
            return _finalize(
                IMPORT_OUTCOME_ALREADY_IMPORTED,
                study_uuid=str(existing_study.uuid),
                study_protocol_number=protocol_number,
            )

        # Skip-filter: partial validation. Surface the pending ABREVs
        # back to the admin so they can tell the lab "you still owe me
        # GLU-Bi on this protocol."
        if not mappers.is_protocol_fully_validated(deters):
            counters["partial_validation_skipped"] = 1
            pending = sorted(
                {
                    row.get("ABREV_FLD", "").strip()
                    for row in deters
                    if row.get("VALIDADO_FLD") != "1" or row.get("CARGADO_FLD") != "1"
                }
                - {""}
            )
            return _finalize(IMPORT_OUTCOME_PARTIAL, pending_practices=pending)

        if not paciente:
            # Defensive: DETERS exists but no PACIENTES row. Real LabWin
            # data shouldn't see this, but treat as not_found rather than
            # crashing.
            return _finalize(IMPORT_OUTCOME_NOT_FOUND)

        # Skip-filter: unpaid bono.
        if not mappers.map_is_paid(paciente):
            counters["unpaid_skipped"] = 1
            return _finalize(IMPORT_OUTCOME_UNPAID)

        # Skip-filter: derivacion / no real doctor. force=True bypasses
        # this single filter (admin's explicit override for walk-in
        # patients) — and clears `medico` so the rest of the path
        # doesn't create a "No Consigna" User. The Study lands with
        # ordered_by=None.
        num_medico = paciente.get("NUMMEDICO_FLD")
        if mappers.is_derivacion_doctor(num_medico, medico):
            if not force:
                counters["derivacion_skipped"] = 1
                return _finalize(IMPORT_OUTCOME_DERIVACION)
            logger.info(
                "import_protocol_by_numero: force=True bypassing derivacion "
                "filter for numero=%s (NUMMEDICO_FLD=%r, MEDICO=%r)",
                numero,
                num_medico,
                medico.get("NOMBRE_FLD") if medico else None,
            )
            medico = None

        # Skip-filter: pet/vet patient.
        fields = mappers.map_patient(paciente)
        has_vet = any(
            mappers.is_vet_practice(
                nomens.get(row.get("ABREV_FLD", "").strip(), {}).get("ABREV_FLD"),
                nomens.get(row.get("ABREV_FLD", "").strip(), {}).get("NOMBRE_FLD"),
            )
            for row in deters
            if row.get("ABREV_FLD")
        )
        if mappers.is_pet_candidate(
            fields.get("first_name"),
            fields.get("last_name"),
            fields.get("dni"),
            has_vet_practice=has_vet,
        ):
            counters["pets_skipped"] = 1
            return _finalize(IMPORT_OUTCOME_PET)

        # ----- Happy path: create patient + doctor + practices + study -----

        practice_cache = {}
        for abrev, nomen_row in nomens.items():
            practice_pk = _get_or_create_practice(
                nomen_row, lab_client_id, sync_log, counters
            )
            practice_cache[abrev] = practice_pk

        doctor_pk = None
        if medico:
            doctor_pk = _get_or_create_doctor(medico, lab_client_id, sync_log, counters)

        patient_pk, needs_password_setup = _get_or_create_patient(
            paciente, lab_client_id, sync_log, counters
        )

        # Any DETERS row whose ABREV wasn't in NOMEN: create a minimal
        # Practice so the StudyPractice link doesn't fail.
        for row in deters:
            abrev = row["ABREV_FLD"]
            if abrev not in practice_cache:
                practice_cache[abrev] = _create_minimal_practice(
                    abrev, lab_client_id, sync_log, counters
                )

        study_pk = _get_or_create_study_with_practices(
            numero,
            deters,
            patient_pk,
            doctor_pk,
            practice_cache,
            lab_client_id,
            sync_log,
            counters,
            is_paid=True,
            is_validated=True,
            patient_sex=paciente.get("SEXO_FLD"),
            patient_dob_raw=paciente.get("FNACIM_FLD"),
            # Fallback for protocols where DETERS.FECHA_FLD is None
            # (older data — see _get_or_create_study_with_practices).
            paciente_fecha=paciente.get("FECHA_FLD"),
            paciente_hora=paciente.get("HORA_FLD"),
        )

        # On-demand-only fix (UAT 2026-05-12): the mapper deliberately
        # leaves Study.completed_at NULL because the frontend reads
        # `created_at` as the "Completado" date. For nightly sync the
        # gap between sample-taken and our-row-created is small enough
        # to not matter — but for an on-demand import of an old study,
        # `created_at = today` produces a misleading "Completado:
        # <today's date>" on a study sampled a year ago. Set it to
        # service_date here so the visible date is at least the sample
        # date (a lower bound; the real validation timestamp isn't
        # exposed by LabWin). Nightly sync stays untouched, so the
        # historical "completed before solicited" visual bug the mapper
        # comment warns about can't reappear there.
        if study_pk:
            from apps.studies.models import Study as _Study

            _study_obj = _Study.objects.only("completed_at", "service_date").get(
                pk=study_pk
            )
            if _study_obj.completed_at is None and _study_obj.service_date:
                _study_obj.completed_at = _study_obj.service_date
                _study_obj.save(update_fields=["completed_at", "updated_at"])

        # Notification: fire if the patient hasn't been emailed about
        # this study yet (Study.notification_sent_at flag).
        if study_pk and patient_pk:
            from apps.studies.models import Study as _Study

            already_notified = (
                _Study.objects.filter(pk=study_pk)
                .exclude(notification_sent_at=None)
                .exists()
            )
            if not already_notified:
                users_needing = {patient_pk} if needs_password_setup else set()
                queued, skipped = _dispatch_patient_notifications(
                    studies_to_notify={patient_pk: [study_pk]},
                    users_needing_password_setup=users_needing,
                )
                counters["notifications_queued"] = queued
                counters["emails_skipped"] = skipped

        # Pull the patient's name fields off the just-created/updated User
        # so the success card can show "Imported LW-257008 — María García,
        # DNI 30123456" without the frontend having to do another fetch.
        from apps.studies.models import Study as _Study
        from apps.users.models import User

        patient = User.objects.only("first_name", "last_name", "dni").get(pk=patient_pk)
        study = _Study.objects.only("uuid").get(pk=study_pk)

        return _finalize(
            IMPORT_OUTCOME_IMPORTED,
            study_uuid=str(study.uuid),
            study_protocol_number=protocol_number,
            patient_first_name=patient.first_name,
            patient_last_name=patient.last_name,
            patient_dni=patient.dni,
            is_new_patient=needs_password_setup,
            notifications_queued=counters["notifications_queued"],
        )

    except Exception as e:
        # Connection-level / unexpected failures land here. The lock
        # would otherwise stick for 180s — release it explicitly.
        cache.delete(lock_key)
        logger.exception(
            "import_protocol_by_numero FAILED — numero=%s | %s",
            numero,
            memory_summary(),
        )
        sync_log.status = "failed"
        sync_log.completed_at = timezone.now()
        sync_log.errors = [{"type": "fatal", "error": str(e)}]
        sync_log.error_count = 1
        sync_log.save()
        raise
