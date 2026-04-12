# Generated manually
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('studies', '0003_add_solicited_date_to_study'),
    ]

    operations = [
        # Rename sample_collected_at to service_date
        migrations.RenameField(
            model_name='study',
            old_name='sample_collected_at',
            new_name='service_date',
        ),
        # Update verbose_name for solicited_date
        migrations.AlterField(
            model_name='study',
            name='solicited_date',
            field=models.DateField(blank=True, help_text='Date the study was requested/ordered by the doctor', null=True, verbose_name='fecha de solicitud'),
        ),
        # Update verbose_name for service_date (formerly sample_collected_at)
        migrations.AlterField(
            model_name='study',
            name='service_date',
            field=models.DateTimeField(blank=True, help_text='Date and time when the service was provided (sample collection date)', null=True, verbose_name='fecha de atención'),
        ),
        # Update verbose_name for completed_at
        migrations.AlterField(
            model_name='study',
            name='completed_at',
            field=models.DateTimeField(blank=True, help_text='Date and time when the results were delivered/completed', null=True, verbose_name='fecha de entrega'),
        ),
        # Historical model changes
        migrations.RenameField(
            model_name='historicalstudy',
            old_name='sample_collected_at',
            new_name='service_date',
        ),
    ]
