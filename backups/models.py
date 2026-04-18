"""
配置备份数据模型

包含 ConfigBackup（配置备份）模型。
"""

from django.conf import settings
from django.db import models


class ConfigBackup(models.Model):
    """配置备份模型 - 记录设备配置的 Git 版本信息"""

    STATUS_CHOICES = [
        ('success', '成功'),
        ('failed', '失败'),
        ('pending', '进行中'),
    ]

    device = models.ForeignKey(
        'devices.Device', on_delete=models.CASCADE,
        verbose_name='设备', related_name='config_backups'
    )
    config_content = models.TextField('配置内容')
    git_commit_hash = models.CharField('Git Commit Hash', max_length=40)
    commit_message = models.TextField('变更说明')
    backed_up_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='备份人', related_name='config_backups'
    )
    backed_up_at = models.DateTimeField('备份时间', auto_now_add=True)
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='success')

    class Meta:
        verbose_name = '配置备份'
        verbose_name_plural = '配置备份'
        ordering = ['-backed_up_at']

    def __str__(self):
        return f"{self.device.name} - {self.git_commit_hash[:8]} ({self.backed_up_at})"

    @property
    def version(self):
        """版本号：使用commit hash前8位"""
        return self.git_commit_hash[:8]

    @property
    def backup_time(self):
        """兼容模板属性"""
        return self.backed_up_at

    @property
    def filename(self):
        """文件名：device_id/config.txt"""
        return f"{self.device_id}/config.txt"

    @property
    def file_size(self):
        """文件大小：配置内容字节数"""
        return len(self.config_content.encode('utf-8')) if self.config_content else 0
