"""
设备管理数据模型

包含 Device（设备）和 Port（端口）模型。
需求引用：1.4, 2.1, 2.9
"""

from django.db import models


class Device(models.Model):
    """网络设备模型"""

    DEVICE_TYPES = [
        ('router', '路由器'),
        ('switch', '交换机'),
        ('ap', 'AP'),
        ('ac', 'AC'),
    ]

    STATUS_CHOICES = [
        ('online', '在线'),
        ('offline', '下线'),
        ('fault', '故障'),
        ('preparing', '预备上线'),
    ]

    LAYER_CHOICES = [
        ('access', '接入层'),
        ('aggregation', '汇聚层'),
        ('core', '核心层'),
    ]

    name = models.CharField('设备名称', max_length=100, unique=True)
    device_type = models.CharField('设备类型', max_length=20, choices=DEVICE_TYPES)
    model = models.CharField('设备型号', max_length=100, blank=True)
    ip_address = models.GenericIPAddressField('IP地址', null=True, blank=True)
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='preparing')
    layer = models.CharField('网络层级', max_length=20, choices=LAYER_CHOICES, null=True, blank=True)
    location = models.CharField('位置描述', max_length=200, blank=True)

    # SSH 配置
    ssh_port = models.IntegerField('SSH端口', default=22)
    ssh_username = models.CharField('SSH用户名', max_length=50, blank=True)
    ssh_password = models.CharField('SSH密码', max_length=200, blank=True)  # 生产环境应加密存储

    # SNMP 配置
    snmp_community = models.CharField('SNMP团体名', max_length=100, blank=True)

    # 网络测试字段
    latency = models.FloatField('延迟(ms)', null=True, blank=True, help_text='Ping测试延迟，单位毫秒')

    # 时间字段
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)
    last_seen = models.DateTimeField('最后在线时间', null=True, blank=True)

    class Meta:
        verbose_name = '设备'
        verbose_name_plural = '设备'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.get_device_type_display()}) - {self.ip_address or 'N/A'}"


class Port(models.Model):
    """设备端口模型"""

    device = models.ForeignKey(
        Device, on_delete=models.CASCADE, related_name='ports', verbose_name='所属设备'
    )
    name = models.CharField('端口名称', max_length=50)
    port_type = models.CharField('端口类型', max_length=20, blank=True)
    status = models.CharField('端口状态', max_length=20, blank=True)
    speed = models.CharField('端口速率', max_length=20, blank=True)
    mac_address = models.CharField('MAC地址', max_length=17, blank=True)

    class Meta:
        verbose_name = '端口'
        verbose_name_plural = '端口'
        unique_together = ['device', 'name']

    def __str__(self):
        return f"{self.device.name}:{self.name}"
