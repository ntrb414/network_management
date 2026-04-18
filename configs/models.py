"""
配置管理数据模型

包含 ConfigTemplate（配置模板）、ConfigTask（配置任务）、ConfigTaskResult（配置任务结果）模型。
"""

from django.conf import settings
from django.db import models
from datetime import time


class ConfigTemplate(models.Model):
    """配置模板模型 - 支持设备命令和 Jinja2 两种模式"""

    TEMPLATE_TYPE_CHOICES = [
        ('device_commands', '设备命令'),
        ('jinja2', 'Jinja2模板'),
    ]

    name = models.CharField('模板名称', max_length=100, unique=True)
    description = models.TextField('模板描述', blank=True)
    template_type = models.CharField(
        '模板类型', max_length=20, choices=TEMPLATE_TYPE_CHOICES, default='device_commands'
    )
    device_types = models.JSONField('适用设备类型', default=list,
                                    help_text='适用的设备类型列表，如 ["router", "switch"]')
    template_content = models.TextField('模板内容', help_text='设备命令文本或 Jinja2 模板')
    variables_schema = models.JSONField('变量定义', default=dict,
                                        help_text='模板变量的定义和默认值（用于 Jinja2 模式）')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        verbose_name='创建者', related_name='config_templates'
    )
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '配置模板'
        verbose_name_plural = '配置模板'
        ordering = ['-updated_at']

    def __str__(self):
        return self.name

    def render(self, variables: dict) -> str:
        """渲染模板内容"""
        if self.template_type == 'device_commands':
            return self.template_content
        elif self.template_type == 'jinja2':
            from jinja2 import Template
            template = Template(self.template_content)
            return template.render(**variables)
        return self.template_content


class ConfigTask(models.Model):
    """配置任务模型 - 批量配置下发任务（简化版，无需审批）"""

    STATUS_CHOICES = [
        ('pending', '待执行'),
        ('executing', '执行中'),
        ('completed', '已完成'),
        ('failed', '失败'),
    ]

    name = models.CharField('任务名称', max_length=100)
    template = models.ForeignKey(
        ConfigTemplate, on_delete=models.CASCADE,
        verbose_name='配置模板', related_name='tasks', null=True, blank=True
    )
    devices = models.ManyToManyField(
        'devices.Device', verbose_name='目标设备', related_name='config_tasks'
    )
    variables = models.JSONField('模板变量值', default=dict)
    config_content = models.TextField('配置内容', blank=True, help_text='直接输入的配置内容（设备命令）')
    status = models.CharField('任务状态', max_length=20, choices=STATUS_CHOICES, default='pending')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        verbose_name='创建者', related_name='created_config_tasks'
    )
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    executed_at = models.DateTimeField('执行时间', null=True, blank=True)

    class Meta:
        verbose_name = '配置任务'
        verbose_name_plural = '配置任务'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"


class ConfigTaskResult(models.Model):
    """配置任务执行结果模型"""

    task = models.ForeignKey(
        ConfigTask, on_delete=models.CASCADE,
        verbose_name='所属任务', related_name='results'
    )
    device = models.ForeignKey(
        'devices.Device', on_delete=models.CASCADE,
        verbose_name='目标设备', related_name='config_results'
    )
    success = models.BooleanField('是否成功')
    config_content = models.TextField('配置内容')
    error_message = models.TextField('错误信息', blank=True)
    executed_at = models.DateTimeField('执行时间', auto_now_add=True)

    class Meta:
        verbose_name = '配置执行结果'
        verbose_name_plural = '配置执行结果'

    def __str__(self):
        status = '成功' if self.success else '失败'
        return f"{self.task.name} - {self.device.name}: {status}"


# ==================== 配置获取定时任务模型 ====================

class ConfigFetchSchedule(models.Model):
    """配置获取定时任务配置"""

    TASK_TYPE_CHOICES = [
        ('preload', '配置预加载'),
        ('backup', '配置备份'),
    ]

    EXEC_MODE_CHOICES = [
        ('interval', '间隔执行'),
        ('cron', '定时执行'),
    ]

    INTERVAL_CHOICES = [
        (300, '每5分钟'),
        (600, '每10分钟'),
        (1800, '每30分钟'),
        (3600, '每1小时'),
        (21600, '每6小时'),
        (43200, '每12小时'),
        (86400, '每24小时'),
    ]

    DAY_CHOICES = [
        ('*', '每天'),
        ('1-5', '工作日'),
        ('0,6', '周末'),
        ('0', '周日'),
        ('1', '周一'),
        ('2', '周二'),
        ('3', '周三'),
        ('4', '周四'),
        ('5', '周五'),
        ('6', '周六'),
    ]

    QUEUE_CHOICES = [
        ('low', '低优先级'),
        ('normal', '普通优先级'),
        ('high', '高优先级'),
    ]

    DEVICE_SELECTION_MODE_CHOICES = [
        ('multiple', '多选'),
        ('single', '单选'),
    ]

    # 基本信息
    name = models.CharField('任务名称', max_length=100, default='设备配置预加载')
    task_type = models.CharField('任务类型', max_length=20, choices=TASK_TYPE_CHOICES, default='preload')
    enabled = models.BooleanField('是否启用', default=True)

    # 执行模式
    exec_mode = models.CharField('执行模式', max_length=20, choices=EXEC_MODE_CHOICES, default='interval')

    # 间隔执行配置
    interval_seconds = models.IntegerField('执行间隔(秒)', choices=INTERVAL_CHOICES, default=1800)

    # 定时执行配置
    exec_time = models.TimeField('执行时间', default=time(2, 0))
    exec_days = models.CharField('执行日期', max_length=20, default='*')

    # 目标配置
    target_devices = models.ManyToManyField('devices.Device', blank=True, verbose_name='目标设备')
    target_all_devices = models.BooleanField('全部设备', default=True)
    device_selection_mode = models.CharField(
        '设备选择模式', max_length=20, choices=DEVICE_SELECTION_MODE_CHOICES, default='multiple'
    )
    only_online_devices = models.BooleanField('仅在线设备', default=True)

    # 任务配置
    queue = models.CharField('任务队列', max_length=20, choices=QUEUE_CHOICES, default='low')
    max_concurrent = models.IntegerField('最大并发数', default=5)

    # 元数据
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, verbose_name='创建者')

    # 执行统计
    last_run_time = models.DateTimeField('上次执行时间', null=True, blank=True)
    last_run_status = models.CharField('上次执行状态', max_length=20, blank=True)
    total_run_count = models.IntegerField('总执行次数', default=0)

    class Meta:
        db_table = 'config_fetch_schedule'
        verbose_name = '配置获取定时任务'
        verbose_name_plural = '配置获取定时任务'

    def __str__(self):
        return self.name


class ConfigFetchLog(models.Model):
    """配置获取执行日志"""

    STATUS_CHOICES = [
        ('running', '执行中'),
        ('success', '成功'),
        ('partial', '部分成功'),
        ('failed', '失败'),
    ]

    schedule = models.ForeignKey(ConfigFetchSchedule, on_delete=models.CASCADE, related_name='logs', verbose_name='定时任务')
    start_time = models.DateTimeField('开始时间', auto_now_add=True)
    end_time = models.DateTimeField('结束时间', null=True, blank=True)
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='running')

    # 执行结果
    total_devices = models.IntegerField('设备总数', default=0)
    success_count = models.IntegerField('成功数', default=0)
    failed_count = models.IntegerField('失败数', default=0)

    # 详细信息
    error_message = models.TextField('错误信息', blank=True)
    result_detail = models.JSONField('执行详情', default=dict, blank=True)

    class Meta:
        db_table = 'config_fetch_log'
        verbose_name = '配置获取日志'
        verbose_name_plural = '配置获取日志'
        ordering = ['-start_time']
