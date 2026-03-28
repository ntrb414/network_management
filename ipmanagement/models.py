"""
IP Management Models

包含网段配置、IP地址管理、扫描任务和分配记录。
"""

import ipaddress
from django.db import models
from django.utils import timezone


class Subnet(models.Model):
    """网段配置模型"""

    SOURCE_CHOICES = [
        ('manual', '手动输入'),
        ('auto', '自动获取'),
    ]

    cidr = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='网段(CIDR)',
        help_text='例如: 192.168.1.0/24'
    )
    name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='名称',
        help_text='网段描述名称'
    )
    vlan_id = models.IntegerField(
        'VLAN ID',
        null=True,
        blank=True,
        help_text='VLAN编号 (1-4094)'
    )
    description = models.TextField(
        '描述',
        blank=True,
        help_text='网段用途描述'
    )
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default='manual',
        verbose_name='来源'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='启用扫描'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='更新时间'
    )

    class Meta:
        verbose_name = '网段配置'
        verbose_name_plural = '网段配置'
        ordering = ['cidr']

    def __str__(self):
        return f"{self.name or self.cidr} ({self.cidr})"

    @property
    def total_ips(self):
        """网段内可用的IP总数（排除网络地址和广播地址）"""
        try:
            network = ipaddress.ip_network(self.cidr, strict=False)
            return len(list(network.hosts()))
        except ValueError:
            return 0

    @property
    def used_ips(self):
        """已分配的IP数量（排除available状态）"""
        return self.ip_addresses.exclude(status='available').count()

    @property
    def available_ips(self):
        """可用IP数量"""
        return self.ip_addresses.filter(status='available').count()

    @property
    def usage_rate(self):
        """IP使用率百分比"""
        total = self.total_ips
        if total == 0:
            return 0
        return round(self.used_ips / total * 100, 1)

    def get_network_address(self):
        """获取网络地址"""
        try:
            return str(ipaddress.ip_network(self.cidr, strict=False).network_address)
        except ValueError:
            return None

    def get_broadcast_address(self):
        """获取广播地址"""
        try:
            return str(ipaddress.ip_network(self.cidr, strict=False).broadcast_address)
        except ValueError:
            return None

    def get_gateway_ip(self):
        """获取网关IP（通常是第一个或最后一个可用IP）"""
        try:
            network = ipaddress.ip_network(self.cidr, strict=False)
            hosts = list(network.hosts())
            if hosts:
                return str(hosts[0])
            return None
        except ValueError:
            return None


class IPAddress(models.Model):
    """IP地址模型 - 记录网段内每个IP的状态和分配信息"""

    STATUS_CHOICES = [
        ('available', '可用'),
        ('allocated', '已分配'),
        ('reserved', '预留'),
    ]

    ip_address = models.GenericIPAddressField(
        'IP地址',
        unique=True
    )
    subnet = models.ForeignKey(
        Subnet,
        on_delete=models.CASCADE,
        related_name='ip_addresses',
        verbose_name='所属网段'
    )
    hostname = models.CharField(
        '主机名',
        max_length=255,
        blank=True,
        help_text='DNS主机名'
    )
    mac_address = models.CharField(
        'MAC地址',
        max_length=17,
        blank=True,
        help_text='例如: AA:BB:CC:DD:EE:FF'
    )
    description = models.TextField(
        '描述',
        blank=True,
        help_text='IP地址用途描述'
    )
    status = models.CharField(
        '状态',
        max_length=20,
        choices=STATUS_CHOICES,
        default='available',
        db_index=True
    )
    device = models.ForeignKey(
        'devices.Device',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_ips',
        verbose_name='关联设备'
    )
    allocated_at = models.DateTimeField(
        '分配时间',
        null=True,
        blank=True
    )
    allocated_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ip_allocations',
        verbose_name='分配人'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='更新时间'
    )

    class Meta:
        verbose_name = 'IP地址'
        verbose_name_plural = 'IP地址'
        ordering = ['ip_address']
        indexes = [
            models.Index(fields=['subnet', 'status']),
            models.Index(fields=['hostname']),
            models.Index(fields=['mac_address']),
        ]

    def __str__(self):
        return f"{self.ip_address} ({self.get_status_display()})"

    def allocate(self, device=None, user=None, hostname='', description=''):
        """分配IP给设备"""
        if self.status == 'reserved':
            raise ValueError('Cannot allocate a reserved IP')
        if self.status not in ('available', 'allocated'):
            raise ValueError(f'Cannot allocate IP with status: {self.status}')
        self.status = 'allocated'
        self.device = device
        self.hostname = hostname
        self.description = description
        self.allocated_at = timezone.now()
        self.allocated_by = user
        self.save()

    def release(self):
        """释放IP"""
        if self.status not in ('allocated', 'reserved'):
            raise ValueError(f'Cannot release IP with status: {self.status}')
        self.status = 'available'
        self.device = None
        self.hostname = ''
        self.allocated_at = None
        self.allocated_by = None
        self.save()

    def reserve(self, user=None, description='', device=None):
        """预留IP"""
        if self.status != 'available':
            raise ValueError(f'Cannot reserve IP with status: {self.status}')
        self.status = 'reserved'
        self.description = description
        self.device = device
        self.save()


class AllocationLog(models.Model):
    """IP分配记录模型 - 记录IP的所有变更历史"""

    ACTION_CHOICES = [
        ('allocate', '分配'),
        ('release', '释放'),
        ('update', '更新'),
        ('reserve', '预留'),
        ('scan_discover', '扫描发现'),
    ]

    ip_address = models.GenericIPAddressField(
        'IP地址',
        db_index=True
    )
    hostname = models.CharField(
        '主机名',
        max_length=255,
        blank=True
    )
    action = models.CharField(
        '操作',
        max_length=20,
        choices=ACTION_CHOICES,
        db_index=True
    )
    old_value = models.JSONField(
        '旧值',
        null=True,
        blank=True,
        help_text='操作前的IP状态'
    )
    new_value = models.JSONField(
        '新值',
        null=True,
        blank=True,
        help_text='操作后的IP状态'
    )
    performed_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ip_allocation_logs',
        verbose_name='操作人'
    )
    performed_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='操作时间'
    )
    notes = models.TextField(
        '备注',
        blank=True,
        help_text='操作备注信息'
    )

    class Meta:
        verbose_name = '分配记录'
        verbose_name_plural = '分配记录'
        ordering = ['-performed_at']
        indexes = [
            models.Index(fields=['ip_address', '-performed_at']),
        ]

    def __str__(self):
        return f"{self.ip_address} - {self.get_action_display()} @ {self.performed_at}"


class IPScanTask(models.Model):
    """IP扫描任务记录（仅用于跟踪扫描状态，不存储结果）"""

    STATUS_CHOICES = [
        ('pending', '等待中'),
        ('running', '扫描中'),
        ('completed', '已完成'),
        ('failed', '失败'),
    ]

    subnet = models.ForeignKey(
        Subnet,
        on_delete=models.CASCADE,
        verbose_name='网段',
        null=True,
        blank=True
    )
    cidr = models.CharField(
        max_length=50,
        verbose_name='扫描网段'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='状态'
    )
    total_ips = models.IntegerField(
        default=0,
        verbose_name='总IP数'
    )
    scanned_ips = models.IntegerField(
        default=0,
        verbose_name='已扫描数'
    )
    alive_ips = models.IntegerField(
        default=0,
        verbose_name='存活IP数'
    )
    message = models.TextField(
        blank=True,
        verbose_name='消息/错误信息'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间'
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='完成时间'
    )

    class Meta:
        verbose_name = '扫描任务'
        verbose_name_plural = '扫描任务'
        ordering = ['-created_at']

    def __str__(self):
        return f"扫描任务 {self.cidr} - {self.get_status_display()}"
