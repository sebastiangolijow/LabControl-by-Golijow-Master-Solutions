# Generated for SyncLog counter additions: study_practices_created,
# notifications_queued, emails_skipped. The in-memory counters dict in
# sync_labwin_results already increments these; sync_log.save() persists
# any field that exists via hasattr(), so this migration is enough to
# light them up without code changes elsewhere.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("labwin_sync", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="synclog",
            name="study_practices_created",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="synclog",
            name="notifications_queued",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="synclog",
            name="emails_skipped",
            field=models.IntegerField(default=0),
        ),
    ]
