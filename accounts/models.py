"""
用户权限数据模型
包含 UserProfile（用户配置文件）模型，扩展 Django User 模型。
"""

from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    """用户配置文件模型 - 扩展 Django User，添加角色和权限"""

    ROLE_CHOICES = [
        ('admin', '管理员'),
        ('user', '普通用户'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        verbose_name='用户', related_name='profile'
    )
    role = models.CharField('角色', max_length=20, choices=ROLE_CHOICES, default='user')
    permissions = models.JSONField(
        '细粒度权限', default=dict,
        help_text='普通用户的细粒度权限配置，如 {"devices": ["view", "edit"], "configs": ["view"]}'
    )

    class Meta:
        verbose_name = '用户配置'
        verbose_name_plural = '用户配置'

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_user(self):
        return self.role == 'user'
