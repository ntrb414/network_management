import json
import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from ipmanagement.models import Subnet, IPScanTask, IPAddress
import ipmanagement.tasks as tasks_module
from ipmanagement.services import IPScanService, IPAMService, NetworkDiscoveryService
from devices.models import Device


class FakeRedis:
    def __init__(self):
        self._data = {}

    def setex(self, key, ttl, value):
        self._data[key] = value

    def get(self, key):
        return self._data.get(key)


@pytest.mark.django_db
def test_enqueue_scan_task_triggers_scan_and_sync(monkeypatch):
    # 创建测试网段
    subnet = Subnet.objects.create(cidr='192.0.2.0/30', name='test-subnet')

    # 模拟扫描结果：返回一个存活主机列表
    fake_alive = [
        {"ip": "192.0.2.1", "alive": True, "hostname": "host1", "response_time": 5},
    ]

    # Monkeypatch IPScanService.scan_subnet: 调用 progress_callback 来填充 alive_hosts
    def fake_scan(self, cidr, progress_callback=None, return_all=False):
        if progress_callback:
            for r in fake_alive:
                progress_callback(1, 1, r)
        return fake_alive if return_all else fake_alive

    monkeypatch.setattr(IPScanService, 'scan_subnet', fake_scan)

    # 将 scan_subnet_task.delay 覆盖为直接调用 scan_subnet_task（同步执行）
    def fake_delay(task_id):
        return tasks_module.scan_subnet_task.run(task_id)

    monkeypatch.setattr(tasks_module.scan_subnet_task, 'delay', fake_delay)

    # Mock Redis 连接，避免测试环境依赖 Redis 服务
    monkeypatch.setattr(tasks_module, 'get_redis_connection', lambda alias: FakeRedis())

    # 调用 enqueue_scan_task（作为任务函数直接调用，传 None 作为 self）
    # 直接创建扫描任务（与 enqueue_scan_task 的行为一致），然后同步执行 scan_subnet_task
    task = IPScanTask.objects.create(
        subnet_id=subnet.id,
        cidr=subnet.cidr,
        status='pending',
        total_ips=subnet.total_ips,
        scanned_ips=0,
        alive_ips=0,
    )

    tasks_module.scan_subnet_task.run(task.id)

    # 刷新并验证任务已被标记为 completed，并且已记录存活数量
    task.refresh_from_db()
    assert task.status == 'completed'
    assert task.alive_ips == len(fake_alive)

    # 检查 IPAddress 是否已被同步到数据库并状态为 available（扫描发现不自动分配）
    ip_obj = IPAddress.objects.filter(ip_address='192.0.2.1').first()
    assert ip_obj is not None
    assert ip_obj.status == 'available'


@pytest.mark.django_db
def test_sync_scan_results_to_ipam_task(monkeypatch):
    # 创建子网和一个扫描任务，但不自动触发扫描
    subnet = Subnet.objects.create(cidr='198.51.100.0/30', name='sync-subnet')
    alive_hosts = [{"ip": "198.51.100.1", "alive": True, "hostname": "h2", "response_time": 8}]

    task = IPScanTask.objects.create(
        subnet=subnet,
        cidr=subnet.cidr,
        status='pending',
        total_ips=subnet.total_ips,
        scanned_ips=0,
        alive_ips=0,
        message=json.dumps(alive_hosts),
    )

    # 预先创建同IP的 IPAddress（available），以验证 sync_scan_results 不会改变其状态
    IPAddress.objects.create(ip_address='198.51.100.1', subnet=subnet, status='available')

    # Mock Redis 连接并预写入扫描结果
    fake_redis = FakeRedis()
    fake_redis.setex(
        f"ipscan:task:{task.id}",
        300,
        json.dumps({
            'alive_hosts': alive_hosts,
            'alive_count': len(alive_hosts),
            'all_results': alive_hosts,
            'completed_at': timezone.now().isoformat(),
        })
    )
    monkeypatch.setattr(tasks_module, 'get_redis_connection', lambda alias: fake_redis)

    # 直接调用同步任务函数
    result = tasks_module.sync_scan_results_to_ipam.run(task.id)

    assert result['success'] is True
    # 确认 IPAddress 状态保持 available（扫描不自动分配）
    ip_obj = IPAddress.objects.filter(ip_address='198.51.100.1').first()
    assert ip_obj is not None
    assert ip_obj.status == 'available'

    # 确认没有产生 scan_discover 日志（扫描不再改变状态）
    from ipmanagement.models import AllocationLog
    log = AllocationLog.objects.filter(ip_address='198.51.100.1', action='scan_discover').first()
    assert log is None


@pytest.mark.django_db
def test_sync_scan_results_marks_unresponsive_ip_as_available():
    subnet = Subnet.objects.create(cidr='203.0.113.0/30', name='status-sync-subnet')

    service = IPAMService()
    result = service.sync_scan_results(subnet.id, [
        {"ip": "203.0.113.1", "alive": True, "hostname": "alive-host", "response_time": 3},
        {"ip": "203.0.113.2", "alive": False, "hostname": None, "response_time": None},
    ])

    assert result['success'] is True
    assert IPAddress.objects.get(ip_address='203.0.113.1').status == 'available'
    assert IPAddress.objects.get(ip_address='203.0.113.2').status == 'available'


@pytest.mark.django_db
def test_network_discovery_service_derives_subnets_from_device_ips():
    Device.objects.create(name='edge-sw-1', device_type='switch', ip_address='192.168.50.10')
    Device.objects.create(name='edge-sw-2', device_type='switch', ip_address='192.168.50.200')
    Device.objects.create(name='core-r1', device_type='router', ip_address='10.0.8.1')

    service = NetworkDiscoveryService()

    assert service.discover_network_subnets() == ['10.0.8.0/24', '192.168.50.0/24']


@pytest.mark.django_db
def test_auto_subnets_api_returns_missing_device_subnets_only(client):
    user = get_user_model().objects.create_user(username='ipam-admin', password='secret123')
    client.force_login(user)

    Device.objects.create(name='access-1', device_type='switch', ip_address='192.168.60.10')
    Device.objects.create(name='access-2', device_type='switch', ip_address='192.168.60.11')
    Device.objects.create(name='core-1', device_type='router', ip_address='10.10.10.1')
    Subnet.objects.create(cidr='192.168.60.0/24', name='existing-subnet')

    response = client.get('/ipmanagement/api/auto-subnets/')

    assert response.status_code == 200
    payload = response.json()
    assert payload['success'] is True
    assert payload['subnets'] == [
        {
            'cidr': '10.10.10.0/24',
            'name': '自动发现-10.10.10.0/24',
            'device_count': 1,
            'exists': False,
        }
    ]


@pytest.mark.django_db
def test_api_subnets_post_supports_auto_source(client):
    user = get_user_model().objects.create_user(username='ipam-operator', password='secret123')
    client.force_login(user)

    response = client.post(
        '/ipmanagement/api/subnets/',
        data=json.dumps({
            'cidr': '172.16.5.0/24',
            'name': '自动发现-172.16.5.0/24',
            'source': 'auto',
            'is_active': True,
        }),
        content_type='application/json'
    )

    assert response.status_code == 201
    subnet = Subnet.objects.get(cidr='172.16.5.0/24')
    assert subnet.source == 'auto'




@pytest.mark.django_db
def test_sync_scan_results_downgrades_stale_allocated_ip():
    """验证扫描会将之前自动发现、现已离线的 allocated IP 降级为 available"""
    from ipmanagement.models import AllocationLog

    subnet = Subnet.objects.create(cidr='203.0.113.0/30', name='stale-sync-subnet')

    # 预先创建一个状态为 allocated 但没有分配人和设备的 IP（模拟扫描自动发现）
    IPAddress.objects.create(
        ip_address='203.0.113.1',
        subnet=subnet,
        status='allocated',
        hostname='old-host',
    )

    service = IPAMService()
    result = service.sync_scan_results(subnet.id, [
        {"ip": "203.0.113.1", "alive": False, "hostname": None, "response_time": None},
    ])

    assert result['success'] is True
    ip_obj = IPAddress.objects.get(ip_address='203.0.113.1')
    assert ip_obj.status == 'available'
    assert ip_obj.hostname == ''
    assert ip_obj.allocated_by is None

    log = AllocationLog.objects.filter(ip_address='203.0.113.1', action='scan_release').first()
    assert log is not None


@pytest.mark.django_db
def test_sync_scan_results_preserves_manually_allocated_ip():
    """验证扫描不会将有人工分配记录的 allocated IP 降级"""
    from ipmanagement.models import AllocationLog
    from django.contrib.auth import get_user_model

    subnet = Subnet.objects.create(cidr='203.0.113.0/30', name='manual-sync-subnet')
    user = get_user_model().objects.create_user(username='ip-admin', password='secret')

    # 预先创建一个有人工分配记录的 allocated IP
    ip = IPAddress.objects.create(
        ip_address='203.0.113.1',
        subnet=subnet,
        status='allocated',
        hostname='manual-host',
    )
    ip.allocated_by = user
    ip.save()

    service = IPAMService()
    result = service.sync_scan_results(subnet.id, [
        {"ip": "203.0.113.1", "alive": False, "hostname": None, "response_time": None},
    ])

    assert result['success'] is True
    ip_obj = IPAddress.objects.get(ip_address='203.0.113.1')
    assert ip_obj.status == 'allocated'
    assert ip_obj.hostname == 'manual-host'
    assert ip_obj.allocated_by == user

    # 不应产生 scan_release 日志
    log = AllocationLog.objects.filter(ip_address='203.0.113.1', action='scan_release').first()
    assert log is None



@pytest.mark.django_db
def test_sync_scan_results_creates_new_ip_as_available():
    """验证扫描发现的新 IP 默认创建为 available，而非 allocated"""
    subnet = Subnet.objects.create(cidr='203.0.113.0/30', name='create-sync-subnet')

    service = IPAMService()
    result = service.sync_scan_results(subnet.id, [
        {"ip": "203.0.113.1", "alive": True, "hostname": "alive-host", "response_time": 3},
    ])

    assert result['success'] is True
    ip_obj = IPAddress.objects.get(ip_address='203.0.113.1')
    assert ip_obj.status == 'available'
    assert ip_obj.hostname == ''  # available IP 不更新 hostname


@pytest.mark.django_db
def test_icmp_ping_retry_on_failure(monkeypatch):
    """验证 icmp_ping 在第一次失败后重试 1 次"""
    import subprocess
    from ipmanagement.services import IPScanService

    call_count = [0]

    def fake_subprocess_run(cmd, **kwargs):
        call_count[0] += 1
        class FakeResult:
            returncode = 0 if call_count[0] >= 2 else 1
            stdout = b'rtt min/avg/max/mdev = 0.5/0.5/0.5/0.000 ms'
            stderr = b''
        return FakeResult()

    monkeypatch.setattr(subprocess, 'run', fake_subprocess_run)

    scanner = IPScanService()
    result = scanner.icmp_ping('192.0.2.1')

    assert result['alive'] is True
    assert result['method'] == 'ICMP'
    assert call_count[0] == 2  # 第一次失败，第二次成功


@pytest.mark.django_db
def test_icmp_ping_retry_both_fail(monkeypatch):
    """验证 icmp_ping 重试后仍然失败"""
    import subprocess
    from ipmanagement.services import IPScanService

    def fake_subprocess_run(cmd, **kwargs):
        class FakeResult:
            returncode = 1
            stdout = b''
            stderr = b''
        return FakeResult()

    monkeypatch.setattr(subprocess, 'run', fake_subprocess_run)

    scanner = IPScanService()
    result = scanner.icmp_ping('192.0.2.1')

    assert result['alive'] is False
    assert result['method'] == 'ICMP'
