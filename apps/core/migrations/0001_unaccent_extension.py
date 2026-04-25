"""Enable Postgres unaccent extension for accent-insensitive search.

Used by apps.core.search.unaccent_icontains so that searching for "si"
matches names like "Sí", "Asunción", "Mariña". Without this extension,
__icontains is case-insensitive but not accent-insensitive — Spanish-named
patients aren't findable by their accent-stripped form.

The extension is built into the Postgres image we use (postgres:15-alpine).
CREATE EXTENSION requires superuser; in production we run migrations as
the labcontrol_user role which by default is the DB owner — that suffices.
If a deploy fails here with "permission denied to create extension", grant
it once: ALTER USER labcontrol_user SUPERUSER; (or have the DBA pre-create
the extension with: CREATE EXTENSION IF NOT EXISTS unaccent;).
"""

from django.db import migrations


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.RunSQL(
            sql="CREATE EXTENSION IF NOT EXISTS unaccent;",
            reverse_sql="DROP EXTENSION IF EXISTS unaccent;",
        ),
    ]
