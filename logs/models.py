"""
日志数据模型

包含 SystemLog（系统日志）模型。
需求引用：7.1, 10.1, 10.2
"""

from django.conf import settings
from django.db import models


class SystemLog(models.Model):
    """系统日志模型 - 包含告警日志、系统日志和操作日志"""

    LOG_TYPES = [
        ('alert', '告警日志'),
        ('system', '系统日志'),
    ]

    log_type = models.CharField('日志类型', max_length=20, choices=LOG_TYPES)
    device = models.ForeignKey(
        'devices.Device', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='相关设备', related_name='system_logs'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='操作用户', related_name='system_logs'
    )
    message = models.TextField('日志内容')
    details = models.JSONField('详细信息', blank=True, null=True)
    timestamp = models.DateTimeField('时间戳', auto_now_add=True)

    class Meta:
        verbose_name = '系统日志'
        verbose_name_plural = '系统日志'
        indexes = [
            models.Index(fields=['log_type', 'timestamp']),
        ]
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.get_log_type_display()}] {self.timestamp}: {self.message[:50]}"
