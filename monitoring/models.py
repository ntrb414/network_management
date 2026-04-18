"""
性能监控数据模型

包含 MetricData（监控指标数据）模型。
"""

from django.db import models


class MetricData(models.Model):
    """
    监控指标数据模型

    已弃用直接写入：新的监控数据已迁移至 Redis（TTL 10 分钟）。
    此模型仅保留用于兼容历史数据与 Admin 管理。
    """

    METRIC_TYPES = [
        ('traffic', '端口流量'),
        ('packet_loss', '丢包率'),
        ('connections', '连接数'),
        ('interface_status', '接口状态'),
        ('interface_in_traffic', '接口入向流量'),
        ('interface_out_traffic', '接口出向流量'),
        ('interface_in_drops', '接口入向丢包'),
        ('interface_out_drops', '接口出向丢包'),
        ('ospf_neighbor', 'OSPF邻居状态'),
    ]

    device = models.ForeignKey(
        'devices.Device', on_delete=models.CASCADE,
        verbose_name='设备', related_name='metrics'
    )
    metric_type = models.CharField('指标类型', max_length=30, choices=METRIC_TYPES)
    metric_name = models.CharField('指标名称', max_length=50,
                                   help_text='如 port_eth0_traffic')
    value = models.FloatField('指标值')
    unit = models.CharField('单位', max_length=20)
    timestamp = models.DateTimeField('采集时间', auto_now_add=True)

    class Meta:
        verbose_name = '监控数据'
        verbose_name_plural = '监控数据'
        indexes = [
            models.Index(fields=['device', 'metric_type', 'timestamp']),
        ]
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.device.name} - {self.get_metric_type_display()}: {self.value}{self.unit}"
