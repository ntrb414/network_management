from django.db import migrations, models


def normalize_ip_statuses(apps, schema_editor):
    IPAddress = apps.get_model('ipmanagement', 'IPAddress')

    # 仅保留三种状态：available/allocated/reserved
    # 将历史 dhcp/monitoring 统一映射为 allocated，其他异常值回退为 available
    IPAddress.objects.filter(status__in=['dhcp', 'monitoring']).update(status='allocated')
    IPAddress.objects.exclude(status__in=['available', 'allocated', 'reserved']).update(status='available')


class Migration(migrations.Migration):

    dependencies = [
        ('ipmanagement', '0002_add_ipam_models'),
    ]

    operations = [
        migrations.RunPython(normalize_ip_statuses, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='ipaddress',
            name='status',
            field=models.CharField(
                choices=[
                    ('available', '可用'),
                    ('allocated', '已分配'),
                    ('reserved', '预留'),
                ],
                db_index=True,
                default='available',
                max_length=20,
                verbose_name='状态',
            ),
        ),
    ]
