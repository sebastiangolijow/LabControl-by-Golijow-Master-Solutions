# Generated manually
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="matricula",
            field=models.CharField(
                blank=True,
                help_text="Medical license number (for doctors)",
                max_length=50,
                verbose_name="matricula",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="deleted_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Date when the user was soft-deleted",
                null=True,
                verbose_name="deleted at",
            ),
        ),
        migrations.AddField(
            model_name="historicaluser",
            name="matricula",
            field=models.CharField(
                blank=True,
                help_text="Medical license number (for doctors)",
                max_length=50,
                verbose_name="matricula",
            ),
        ),
        migrations.AddField(
            model_name="historicaluser",
            name="deleted_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Date when the user was soft-deleted",
                null=True,
                verbose_name="deleted at",
            ),
        ),
    ]
