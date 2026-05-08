# Generated 2026-05-08 by hand (matches what makemigrations would produce).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("studies", "0006_historicalstudy_notification_sent_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="practice",
            name="result_layout",
            field=models.JSONField(
                blank=True,
                help_text=(
                    "Per-position metadata (label, unit, factor, decimals, valnor) "
                    "synced from LabWin RESULTS + VALNOR tables. None means no layout "
                    "available — frontend falls back to raw result string."
                ),
                null=True,
                verbose_name="result layout",
            ),
        ),
        migrations.AddField(
            model_name="studypractice",
            name="resolved_valnor",
            field=models.JSONField(
                blank=True,
                help_text=(
                    "Per-position reference range strings resolved against the "
                    "patient's sex and age. Schema: {position_str: valnor_text}."
                ),
                null=True,
                verbose_name="resolved reference ranges",
            ),
        ),
    ]
