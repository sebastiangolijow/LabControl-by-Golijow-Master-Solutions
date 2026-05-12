"""
Add User.biological_sex.

Splits the existing single `gender` field into two semantically distinct
columns:

  - biological_sex (M/F, read-only for patients, used clinically)
  - gender         (M/F/O/P, patient self-declared, never used clinically)

Data backfill: every existing user whose `gender` is 'M' or 'F' gets that
value copied into `biological_sex`. The original `gender` value is left
intact — for sync-imported users this is fine (their gender was always
M/F because LabWin's SEXO_FLD only encodes those), and for self-registered
users we don't want to silently change what they entered.

Reverse: drops the column. Patient gender values are not touched in
either direction so the migration is safe to roll back.
"""

from django.db import migrations, models


def backfill_biological_sex(apps, schema_editor):
    User = apps.get_model("users", "User")
    HistoricalUser = apps.get_model("users", "HistoricalUser")

    User.objects.filter(gender__in=["M", "F"]).update(
        biological_sex=models.F("gender")
    )
    # Backfill the audit-trail rows too, otherwise as_of() reads will show
    # biological_sex='' for snapshots taken before this migration even
    # though the live row has it populated.
    HistoricalUser.objects.filter(gender__in=["M", "F"]).update(
        biological_sex=models.F("gender")
    )


def noop_reverse(apps, schema_editor):
    """Reverse is a no-op — column is dropped by the schema migration above."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0002_alter_historicaluser_dni_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="biological_sex",
            field=models.CharField(
                blank=True,
                choices=[("M", "Male"), ("F", "Female")],
                help_text=(
                    "Biological sex (M/F). Sourced from LabWin SEXO_FLD; "
                    "used for clinical reference ranges. Read-only for "
                    "patients — only admin or sync can change it. Distinct "
                    "from `gender`, which is the patient's self-declared "
                    "identity and never used clinically."
                ),
                max_length=1,
                verbose_name="biological sex",
            ),
        ),
        migrations.AddField(
            model_name="historicaluser",
            name="biological_sex",
            field=models.CharField(
                blank=True,
                choices=[("M", "Male"), ("F", "Female")],
                help_text=(
                    "Biological sex (M/F). Sourced from LabWin SEXO_FLD; "
                    "used for clinical reference ranges. Read-only for "
                    "patients — only admin or sync can change it. Distinct "
                    "from `gender`, which is the patient's self-declared "
                    "identity and never used clinically."
                ),
                max_length=1,
                verbose_name="biological sex",
            ),
        ),
        migrations.AlterField(
            model_name="user",
            name="gender",
            field=models.CharField(
                blank=True,
                choices=[
                    ("M", "Male"),
                    ("F", "Female"),
                    ("O", "Other"),
                    ("P", "Prefer not to say"),
                ],
                help_text=(
                    "Self-declared gender. Optional, patient-editable, "
                    "never overwritten by sync. NOT used for clinical "
                    "reference ranges — see `biological_sex` for that."
                ),
                max_length=1,
                verbose_name="gender",
            ),
        ),
        migrations.AlterField(
            model_name="historicaluser",
            name="gender",
            field=models.CharField(
                blank=True,
                choices=[
                    ("M", "Male"),
                    ("F", "Female"),
                    ("O", "Other"),
                    ("P", "Prefer not to say"),
                ],
                help_text=(
                    "Self-declared gender. Optional, patient-editable, "
                    "never overwritten by sync. NOT used for clinical "
                    "reference ranges — see `biological_sex` for that."
                ),
                max_length=1,
                verbose_name="gender",
            ),
        ),
        migrations.RunPython(backfill_biological_sex, noop_reverse),
    ]
