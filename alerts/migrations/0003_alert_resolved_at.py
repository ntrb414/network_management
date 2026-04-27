# Generated migration for adding resolved_at field and resolved status

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('alerts', '0002_alter_alert_alert_type_alter_alert_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='alert',
            name='resolved_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='恢复时间'),
        ),
    ]
