"""Search helpers for accent-insensitive Postgres queries.

Use unaccent_icontains_q(value, *fields) to build a Q() object that matches
any of the given fields with both case AND accent insensitivity. Examples:
    "si"  matches  "Sí", "Asunción", "Mariña"
    "muno" matches "Muñoz", "MUÑOZ"

Requires the Postgres `unaccent` extension (created in migration
apps.core.migrations.0001_unaccent_extension).
"""

from django.contrib.postgres.lookups import Unaccent
from django.db.models import CharField, Q, TextField

# Register the __unaccent transform on CharField/TextField so we can chain
# it with other lookups: field__unaccent__icontains=value
# Unaccent has bilateral=True, so Django applies UNACCENT() to BOTH the
# field AND the search value at query time — exactly what we want.
# register_lookup is idempotent (overwrites the dict entry); safe to call
# at module import time even on re-imports.
CharField.register_lookup(Unaccent)
TextField.register_lookup(Unaccent)


def unaccent_icontains_q(value, *fields):
    """Build a Q() matching `value` against any of `fields`, case- and
    accent-insensitive, with whitespace-tokenized AND semantics.

    The input is split on whitespace into tokens. Each token must match
    *some* field (OR across fields), and ALL tokens must match (AND across
    tokens). This makes searches like "estefania s" behave the way users
    expect: it matches "Estefania Schmidt" because "estefania" matches
    first_name AND "s" matches last_name. Pre-2026-05-12 the helper
    treated the whole string as one substring, so any space in the query
    silently returned 0 results unless a single field happened to contain
    that exact substring.

    A single-token query (no whitespace) behaves identically to the old
    helper — just an OR across fields with the substring lookup.

    Args:
        value: search term (Python str). Empty/None/whitespace-only
               returns Q() (always-true).
        *fields: one or more Django field paths
                 (e.g. "first_name", "patient__email", "study_practices__practice__name").

    Returns:
        Q: AND across whitespace-split tokens, each an OR across fields
           via `field__unaccent__icontains=token`.

    Examples:
        User.objects.filter(
            unaccent_icontains_q("si", "first_name", "last_name")
        )  # ← matches "Sí", "Asunción", "Síngela", etc.

        User.objects.filter(
            unaccent_icontains_q("estefania s", "first_name", "last_name")
        )  # ← matches "Estefania Schmidt" (1st token first_name,
           #   2nd token last_name)
    """
    if not value:
        return Q()
    tokens = value.split()
    if not tokens:
        return Q()
    q_all = Q()
    for token in tokens:
        q_token = Q()
        for field in fields:
            q_token |= Q(**{f"{field}__unaccent__icontains": token})
        q_all &= q_token
    return q_all
