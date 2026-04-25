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
    accent-insensitive.

    Args:
        value: search term (Python str). Empty/None returns Q() (always-true).
        *fields: one or more Django field paths
                 (e.g. "first_name", "patient__email", "study_practices__practice__name").

    Returns:
        Q: OR of `field__unaccent__icontains=value` for each field.

    Example:
        User.objects.filter(unaccent_icontains_q("si", "first_name", "last_name"))
    """
    if not value:
        return Q()
    q = Q()
    for field in fields:
        q |= Q(**{f"{field}__unaccent__icontains": value})
    return q
