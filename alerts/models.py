"""
告警数据模型

包含 Alert（告警）模型。
"""

from django.conf import settings
from django.db import models


class Alert(models.Model):
    """告警模型"""

    SEVERITY_CHOICES = [
        ('critical', '紧急'),
        ('important', '重要'),
        ('normal', '一般'),
    ]

    ALERT_TYPES = [
        ('device_offline', '设备离线'),
        ('device_fault', '设备故障'),
        ('config_failed', '配置失败'),
        ('metric_abnormal', '指标异常'),
        ('topology_changed', '拓扑变更'),
    ]

    STATUS_CHOICES = [
        ('active', '待处理'),
        ('acknowledged', '已处理'),
        ('ignored', '已忽略'),
        ('resolved', '已恢复'),
    ]

    device = models.ForeignKey(
        'devices.Device', on_delete=models.CASCADE,
        verbose_name='设备', related_name='alerts'
    )
    alert_type = models.CharField('告警类型', max_length=30, choices=ALERT_TYPES)
    severity = models.CharField('优先级', max_length=20, choices=SEVERITY_CHOICES)
    message = models.TextField('告警信息')
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='处理人', related_name='handled_alerts'
    )
    handled_at = models.DateTimeField('处理时间', null=True, blank=True)
    resolved_at = models.DateTimeField('恢复时间', null=True, blank=True)

    class Meta:
        verbose_name = '告警'
        verbose_name_plural = '告警'
        indexes = [
            models.Index(fields=['device', 'status', 'created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_severity_display()}] {self.get_alert_type_display()} - {self.device.name}"
