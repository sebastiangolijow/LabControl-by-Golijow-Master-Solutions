"""
Build Practice.result_layout from LabWin's relational result-template tables.

LabWin's data model for practice results:

    NOMEN     — practice catalog (HEMC = "Hemograma")
    RESULTS   — per-position metadata for each practice. Multiple rows per
                (ABREV_FLD, POSICION_FLD) — older "Valor calculado Nº N"
                template rows coexist with the live label rows. We pick the
                newest non-template row per position.
    VALNOR    — reference ranges, stratified by sex (0=any, 1=M, 2=F, 8=vet)
                and age bracket (with EDADxxL_FLD = 'A' años / 'M' meses /
                'D' días).
    DETERS    — the actual values per study (RESULT_FLD = "57|4160|...|02")

This module turns RESULTS + VALNOR into a single JSON shape attached to
Practice.result_layout. The frontend zips it against StudyPractice.result
to render structured rows. The per-patient sex/age resolution of VALNOR
happens separately at sync time (see resolve_valnor_for_patient below).

Schema documented inline on the model in apps/studies/models.py.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Iterable

logger = logging.getLogger(__name__)


# RESULTS rows whose INRESUL_FLD starts with this string are layout
# templates from LabWin's old print engine, not real position labels.
LAYOUT_TEMPLATE_PREFIX = "Valor calculado"


# FORMATO_FLD values we know about. Numeric formats apply factor/decimals;
# text formats display the raw value as-is (with a leading "$" stripped).
NUMERIC_FORMATS = {1, 2}  # observed in HEMC numeric positions
# Format 156 was observed for the HEMC "Observaciones" free-text position.


def _is_real_label_row(row: dict) -> bool:
    """Skip rows that are layout artifacts, not real position labels.

    LabWin re-uses POSICION_FLD for layout sub-rows (section headers,
    "Valor calculado Nº N" template rows). We only keep rows that have a
    real INRESUL_FLD label that isn't a template.
    """
    label = (row.get("INRESUL_FLD") or "").strip()
    if not label:
        return False
    if label.startswith(LAYOUT_TEMPLATE_PREFIX):
        return False
    return True


def _pick_canonical_per_position(rows: Iterable[dict]) -> dict[int, dict]:
    """Per (ABREV, POSICION), keep the newest non-template row.

    LabWin's RESULTS table has 29 rows for HEMC across 14 positions —
    multiple historical templates per position. We collapse to one
    canonical row per position by:

      1. Filtering out template rows (see _is_real_label_row).
      2. Preferring the row with the newest PRV_TIMESTAMP_FLD.
    """
    by_pos: dict[int, dict] = {}
    for row in rows:
        if not _is_real_label_row(row):
            continue
        pos = row["POSICION_FLD"]
        existing = by_pos.get(pos)
        if existing is None:
            by_pos[pos] = row
            continue
        # Last-write-wins by PRV_TIMESTAMP_FLD (None sorts as oldest)
        new_ts = row.get("PRV_TIMESTAMP_FLD")
        old_ts = existing.get("PRV_TIMESTAMP_FLD")
        if new_ts and (not old_ts or new_ts > old_ts):
            by_pos[pos] = row
    return by_pos


def _abnormal_limits(row: dict) -> dict | None:
    """Pull the 6 LIMxxx_FLD values into a normalized dict.

    LabWin uses '*' for "no limit" and '' for "not configured". Returns
    None if no limits are set for this position.
    """

    def clean(v):
        if v is None:
            return None
        v = str(v).strip()
        if v in ("", "*"):
            return None
        return v

    limits = {
        "min_imposible": clean(row.get("LIMINFIM_FLD")),
        "min_critical": clean(row.get("LIMINFMB_FLD")),
        "min_low": clean(row.get("LIMINFBA_FLD")),
        "max_high": clean(row.get("LIMSUPAL_FLD")),
        "max_critical": clean(row.get("LIMSUPMA_FLD")),
        "max_imposible": clean(row.get("LIMSUPIM_FLD")),
    }
    if all(v is None for v in limits.values()):
        return None
    return limits


def _format_valnor_row(row: dict) -> dict:
    """Reshape a VALNOR row into our layout JSON format."""
    return {
        "sex": row.get("SEXO_FLD"),  # 0=any, 1=M, 2=F, 8=vet (per LabWin)
        "age_min_value": row.get("EDADINFV_FLD"),
        "age_min_unit": (row.get("EDADINFL_FLD") or "").strip() or None,  # A/M/D
        "age_max_value": row.get("EDADSUPV_FLD"),
        "age_max_unit": (row.get("EDADSUPL_FLD") or "").strip() or None,
        "text": (row.get("TEXTO_FLD") or "").strip(),
    }


def build_layout(
    abbrev: str, results_rows: list[dict], valnor_rows: list[dict]
) -> dict | None:
    """Build a Practice.result_layout JSON dict for one practice.

    Args:
      abbrev: ABREV_FLD value (e.g. "HEMC").
      results_rows: All RESULTS rows for this ABREV_FLD.
      valnor_rows: All VALNOR rows for this ABREV_FLD.

    Returns:
      The result_layout dict, or None if no canonical positions could be
      identified.
    """
    canonical = _pick_canonical_per_position(results_rows)
    if not canonical:
        logger.debug("build_layout(%s): no canonical positions found", abbrev)
        return None

    valnor_by_pos: dict[int, list[dict]] = defaultdict(list)
    for v in valnor_rows:
        valnor_by_pos[v["POSICION_FLD"]].append(_format_valnor_row(v))

    items = []
    for position in sorted(canonical):
        row = canonical[position]
        items.append(
            {
                "position": position,
                "label": (row.get("INRESUL_FLD") or "").strip(),
                "unit": (row.get("UNIDADES_FLD") or "").strip(),
                "decimals": int(row.get("DECIMALES_FLD") or 0),
                "factor": float(row.get("FACTOR_FLD") or 0.0),
                "format": int(row.get("FORMATO_FLD") or 1),
                "is_numeric": int(row.get("FORMATO_FLD") or 1) in NUMERIC_FORMATS,
                "abnormal_limits": _abnormal_limits(row),
                "valnor": valnor_by_pos.get(position, []),
            }
        )

    return {"items": items}


# ---------------------------------------------------------------------------
# Per-study valnor resolution
# ---------------------------------------------------------------------------


# Sex codes in LabWin and what they mean for matching:
#   0 = any (matches everyone)
#   1 = male
#   2 = female
#   8 = veterinary (we don't match human patients to these)
_SEX_HUMAN_M = 1
_SEX_HUMAN_F = 2
_SEX_ANY = 0


def _age_to_days(value: int | None, unit: str | None) -> int | None:
    """Convert (value, unit) to days. unit is 'A' (años), 'M' (meses), 'D' (días)."""
    if value is None:
        return None
    if not unit:
        return None
    unit = unit.upper()
    if unit == "A":
        return int(value) * 365
    if unit == "M":
        return int(value) * 30
    if unit == "D":
        return int(value)
    # Unknown unit — treat as years (closest to LabWin's apparent default)
    return int(value) * 365


def _patient_age_days(patient_dob, sample_date) -> int | None:
    """Days between patient DOB and sample date. Returns None if either missing."""
    if not patient_dob or not sample_date:
        return None
    try:
        return (sample_date - patient_dob).days
    except (TypeError, AttributeError):
        return None


def resolve_valnor_for_patient(
    layout: dict | None,
    patient_sex: int | str | None,
    patient_age_days: int | None,
) -> dict[str, str]:
    """Pick the matching VALNOR text per position for a specific patient.

    Args:
      layout: The Practice.result_layout dict (from build_layout).
      patient_sex: 1=M, 2=F, 0/None=unknown (LabWin convention). Strings
        like "M"/"F" are also accepted.
      patient_age_days: Patient's age at sample time, in days.

    Returns:
      {str(position): valnor_text} for every position where a match was
      found. Missing positions = no V.R. should be displayed.
    """
    if not layout or not isinstance(layout.get("items"), list):
        return {}

    sex_int = _normalize_sex(patient_sex)

    resolved: dict[str, str] = {}
    for item in layout["items"]:
        position = item.get("position")
        valnors = item.get("valnor") or []
        if not valnors:
            continue

        match = _pick_best_valnor(valnors, sex_int, patient_age_days)
        if match:
            resolved[str(position)] = match["text"]

    return resolved


def _normalize_sex(value) -> int:
    """Map various inputs to LabWin's sex int convention."""
    if value is None:
        return _SEX_ANY
    if isinstance(value, int):
        return value
    s = str(value).strip().upper()
    if s in ("M", "MALE", "1"):
        return _SEX_HUMAN_M
    if s in ("F", "FEMALE", "2"):
        return _SEX_HUMAN_F
    return _SEX_ANY


def _pick_best_valnor(
    valnors: list[dict], sex: int, age_days: int | None
) -> dict | None:
    """Pick the most specific VALNOR row that matches.

    Match priority:
      1. Sex-specific + age-specific match wins over sex-any + age-any.
      2. If no sex-specific match, fall back to sex=0 (any).
      3. If no age info, ignore the age check.
      4. Skip vet rows (sex=8) for human patients.
    """
    if not valnors:
        return None

    candidates = []
    for v in valnors:
        v_sex = v.get("sex")
        # Skip vet (sex=8) for human patients (sex 0/1/2)
        if v_sex == 8 and sex != 8:
            continue

        sex_match = v_sex == sex or v_sex == _SEX_ANY
        if not sex_match:
            continue

        # Age match
        if age_days is not None:
            v_min_days = _age_to_days(v.get("age_min_value"), v.get("age_min_unit"))
            v_max_days = _age_to_days(v.get("age_max_value"), v.get("age_max_unit"))
            if v_min_days is not None and age_days < v_min_days:
                continue
            if v_max_days is not None and age_days >= v_max_days:
                continue

        # Specificity score: prefer sex-specific matches, prefer narrower age bands
        specificity = 0
        if v_sex == sex and sex != _SEX_ANY:
            specificity += 100
        v_max_days = _age_to_days(v.get("age_max_value"), v.get("age_max_unit"))
        v_min_days = _age_to_days(v.get("age_min_value"), v.get("age_min_unit"))
        if v_min_days is not None and v_max_days is not None:
            band = max(1, v_max_days - v_min_days)
            specificity += max(0, 100000 - band)  # narrower band = higher score

        candidates.append((specificity, v))

    if not candidates:
        # Last resort: any sex=0 row, ignoring age
        for v in valnors:
            if v.get("sex") == _SEX_ANY:
                return v
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]
