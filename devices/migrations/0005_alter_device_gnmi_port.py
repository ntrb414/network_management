from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("devices", "0004_remove_device_snmp_community_device_gnmi_insecure_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="device",
            name="gnmi_port",
            field=models.IntegerField(default=50000, verbose_name="gNMI端口"),
        ),
    ]
