# Generated for backup-file dedup. The BackupImporter records the filename
# of every successfully-processed `.fbk.gz` here, then skips re-imports of
# the same filename so the lab uploading the same backup twice doesn't
# re-run a 2.5-minute restore.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("labwin_sync", "0002_synclog_counters_extension"),
    ]

    operations = [
        migrations.AddField(
            model_name="synclog",
            name="backup_filename",
            field=models.CharField(blank=True, db_index=True, max_length=255),
        ),
    ]
