# Counter for protocols skipped because their PACIENTES.NUMMEDICO_FLD points
# at the "Sin Consigna" sentinel (NUMERO=175) or is unset (=0). These are
# walk-ins / vet / internal-use studies that the lab does not want surfaced
# in the patient portal. See mappers.is_derivacion_doctor.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("labwin_sync", "0003_synclog_backup_filename"),
    ]

    operations = [
        migrations.AddField(
            model_name="synclog",
            name="derivacion_skipped",
            field=models.IntegerField(default=0),
        ),
    ]
