"""
Data mapping logic from LabWin rows to LabControl Django model fields.

Handles name parsing, date conversion, and field mapping for:
- PACIENTES -> User (role=patient)
- MEDICOS -> User (role=doctor)
- NOMEN -> Practice
- DETERS -> Study
"""

import logging
from datetime import date, datetime

from django.utils import timezone as django_tz

logger = logging.getLogger(__name__)


def parse_name(full_name):
    """Parse a LabWin name field into (first_name, last_name).

    Formats handled:
    - "Last, First"  -> first_name="First", last_name="Last"
    - "First Last"   -> first_name="First", last_name="Last"
    - "Single"       -> first_name="Single", last_name=""
    - "" or None      -> first_name="", last_name=""
    """
    if not full_name:
        return "", ""

    full_name = full_name.strip()
    if not full_name:
        return "", ""

    if "," in full_name:
        parts = full_name.split(",", 1)
        last_name = parts[0].strip()
        first_name = parts[1].strip() if len(parts) > 1 else ""
        return first_name, last_name

    if " " in full_name:
        parts = full_name.split(None, 1)
        first_name = parts[0].strip()
        last_name = parts[1].strip() if len(parts) > 1 else ""
        return first_name, last_name

    return full_name, ""


def parse_date(date_str):
    """Parse a LabWin YYYYMMDD string to a Python date.

    Returns None if the string is empty, None, or invalid.
    """
    if not date_str or not date_str.strip():
        return None
    date_str = date_str.strip()
    if len(date_str) != 8:
        return None
    try:
        return date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
    except (ValueError, TypeError):
        logger.warning("Invalid date string: %s", date_str)
        return None


def parse_datetime(date_str, time_str=None):
    """Parse LabWin YYYYMMDD + HH:MM strings to a Python datetime.

    Returns None if date_str is invalid.
    """
    d = parse_date(date_str)
    if d is None:
        return None
    if time_str and ":" in time_str:
        try:
            parts = time_str.strip().split(":")
            naive = datetime(d.year, d.month, d.day, int(parts[0]), int(parts[1]))
            return django_tz.make_aware(naive)
        except (ValueError, TypeError, IndexError):
            pass
    return django_tz.make_aware(datetime(d.year, d.month, d.day))


def _clean_str(value):
    """Strip and return a string, or empty string if None."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value)


def map_patient(paciente_row):
    """Map a PACIENTES row to User model fields.

    Args:
        paciente_row: Dict with LabWin PACIENTES columns.

    Returns:
        Dict of User model fields suitable for create/update.
    """
    first_name, last_name = parse_name(paciente_row.get("NOMBRE_FLD"))

    sexo = paciente_row.get("SEXO_FLD")
    if sexo == 1:
        gender = "M"
    elif sexo == 2:
        gender = "F"
    else:
        gender = ""

    email = _clean_str(paciente_row.get("EMAIL_FLD")) or None
    phone = _clean_str(paciente_row.get("CELULAR_FLD")) or _clean_str(
        paciente_row.get("TELEFONO_FLD")
    )

    mutual_code = paciente_row.get("MUTUAL_FLD")

    return {
        "first_name": first_name,
        "last_name": last_name,
        "dni": _clean_str(paciente_row.get("HCLIN_FLD")),
        "gender": gender,
        "birthday": parse_date(paciente_row.get("FNACIM_FLD")),
        "mutual_code": mutual_code if mutual_code else None,
        "carnet": _clean_str(paciente_row.get("CARNET_FLD")),
        "phone_number": phone,
        "direction": _clean_str(paciente_row.get("DIRECCION_FLD")),
        "location": _clean_str(paciente_row.get("LOCALIDAD_FLD")),
        "email": email,
        "role": "patient",
        "is_active": True,
        "is_verified": True,
    }


def map_doctor(medico_row):
    """Map a MEDICOS row to User model fields.

    Args:
        medico_row: Dict with LabWin MEDICOS columns.

    Returns:
        Dict of User model fields suitable for create/update.
    """
    first_name, last_name = parse_name(medico_row.get("NOMBRE_FLD"))
    email = _clean_str(medico_row.get("EMAIL_FLD")) or None

    return {
        "first_name": first_name,
        "last_name": last_name,
        "matricula": _clean_str(medico_row.get("MATNAC_FLD")),
        "phone_number": _clean_str(medico_row.get("TELEFONO_FLD")),
        "email": email,
        "role": "doctor",
        "is_active": True,
        "is_verified": True,
    }


def map_practice(nomen_row):
    """Map a NOMEN row to Practice model fields.

    Args:
        nomen_row: Dict with LabWin NOMEN columns.

    Returns:
        Dict of Practice model fields suitable for create/update.
    """
    return {
        "code": _clean_str(nomen_row.get("ABREV_FLD")),
        "name": _clean_str(nomen_row.get("NOMBRE_FLD")),
        "delay_days": nomen_row.get("DIASTARDA_FLD") or 0,
        "is_active": True,
    }


# --- Pet/veterinary detection ---
#
# The lab serves veterinary patients alongside humans, but PACIENTES has
# no schema-level discriminator. We identify pets via two combined signals:
#
#   1. STRUCTURAL: last_name (parsed from NOMBRE_FLD) starts with "167" —
#      the lab uses HCLIN/protocol numbers in the 167xxx range as a pet
#      identifier (and the source NOMBRE_FLD format '{HCLIN},{PETNAME}'
#      makes that number end up in our last_name field).
#
#   2. PRACTICE-BASED: the protocol uses at least one veterinary-named
#      practice (Practice.code starts with "VET" or Practice.name contains
#      veterinary keywords like "veterinari", "canin", "felin", "canis",
#      "bovin", "porcin", "equin", "caprin", "aves").
#
# A PACIENTES row is a pet IF dni == '' AND (signal 1 OR signal 2).
#
# This catches pets whose protocol# falls outside the 167 range (signal 2)
# AND pets the lab created without attaching a study (signal 1).
# The dni='' guard prevents false positives — verified against real data,
# 0 patients with a DNI matched this rule.
#
# If the lab adds an explicit pet/vet flag to LabWin in the future, replace
# both signals with that single source of truth.

VET_NAME_KEYWORDS = (
    "veterinari",
    "canin",
    "felin",
    "canis",
    "bovin",
    "porcin",
    "equin",
    "caprin",
    "aves",
)

PET_LAST_NAME_PREFIX = "167"


def is_vet_practice(practice_code, practice_name):
    """Return True if a Practice (by code + name) is a veterinary practice."""
    code = (practice_code or "").strip().upper()
    if code.startswith("VET"):
        return True
    name = (practice_name or "").strip().lower()
    return any(kw in name for kw in VET_NAME_KEYWORDS)


def is_pet_candidate(first_name, last_name, dni, has_vet_practice=False):
    """Return True if a patient record looks like a veterinary patient.

    Combined rule: dni == '' AND (last_name starts with '167' OR
    has_vet_practice).

    Args:
        first_name, last_name: parsed from PACIENTES.NOMBRE_FLD via
            parse_name(). last_name typically contains the HCLIN/protocol
            number for pet records (e.g. '167427').
        dni: parsed from PACIENTES.HCLIN_FLD. Real human patients in
            this lab always have a DNI; pets never do.
        has_vet_practice: True if any of this protocol's DETERS rows maps
            to a Practice with code starting with 'VET' or name containing
            a veterinary keyword. Caller computes this from practice_cache.

    Verified against real lab data: 0 patients with a DNI match either
    signal, so dni='' is a safe necessary condition.
    """
    if (dni or "").strip():
        return False
    last = (last_name or "").strip()
    if last.startswith(PET_LAST_NAME_PREFIX):
        return True
    return bool(has_vet_practice)


def map_is_paid(paciente_row):
    """Derive Study.is_paid from a PACIENTES row's DEBEBONO_FLD.

    DEBEBONO_FLD distribution observed in real lab DB:
      '1'  -> patient owes a bono (must pay)            -> is_paid=False
      '0'  -> patient does not owe a bono (already paid) -> is_paid=True
      ''   -> not applicable (insurance-covered)         -> is_paid=True

    The lab confirmed this mapping. Empty/None defaults to is_paid=True so
    insurance patients (the majority) aren't accidentally hidden.
    """
    if paciente_row is None:
        return True
    debebono = paciente_row.get("DEBEBONO_FLD")
    return debebono != "1"


def map_study(
    numero,
    patient_pk,
    doctor_pk=None,
    fecha=None,
    hora=None,
    is_paid=True,
    is_validated=True,
):
    """Map a LabWin protocol (NUMERO_FLD) to Study model fields.

    Args:
        numero: LabWin NUMERO_FLD (order/protocol ID).
        patient_pk: UUID of the patient User.
        doctor_pk: Optional UUID of the ordering doctor User.
        fecha: YYYYMMDD date string for service_date.
        hora: HH:MM time string for service_date.
        is_paid: Whether the patient has settled the bono. Compute via
                 map_is_paid(pac_row). Default True (insurance-covered).
        is_validated: Whether all of this study's DETERS are validated.
                      Default True since the connector only fetches
                      VALIDADO_FLD='1' rows today.

    Returns:
        Dict of Study model fields suitable for create/update.
    """
    protocol_number = f"LW-{numero}"

    service_date = parse_datetime(fecha, hora) if fecha else None

    return {
        "protocol_number": protocol_number,
        "patient_id": patient_pk,
        "ordered_by_id": doctor_pk,
        "status": "completed",
        "service_date": service_date,
        "completed_at": service_date,
        "sample_id": str(numero),
        "is_paid": is_paid,
        "is_validated": is_validated,
    }


def map_study_practice(deters_row, practice_pk):
    """Map a DETERS row to StudyPractice model fields.

    Args:
        deters_row: Dict with LabWin DETERS columns.
        practice_pk: UUID of the Practice.

    Returns:
        Dict of StudyPractice model fields suitable for create/update.
    """
    return {
        "practice_id": practice_pk,
        "result": _clean_str(deters_row.get("RESULT_FLD")),
        "code": _clean_str(deters_row.get("ABREV_FLD")),
        "order": deters_row.get("ORDEN_FLD", 0) or 0,
    }
