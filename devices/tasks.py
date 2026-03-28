"""
设备发现 Celery 异步任务

包含设备发现的异步任务和定时任务。
需求引用：1.5, 1.6
"""

from celery import shared_task
from django.utils import timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

from .utils import ping_host, DEVICE_CHECK_MAX_WORKERS


@shared_task(bind=True, max_retries=3)
def scan_ip_range_task(self, start_ip: str, end_ip: str):
    """
    扫描IP地址范围任务

    Args:
        start_ip: 起始IP地址
        end_ip: 结束IP地址

    Requirements: 1.1, 1.6
    """
    from .services import DeviceDiscoveryService
    from .models import Device

    service = DeviceDiscoveryService()

    try:
        # 执行IP范围扫描
        discovered_devices = service.scan_ip_range(start_ip, end_ip)

        # 保存发现的设备到数据库
        for device_info in discovered_devices:
            # 检查设备是否已存在
            existing = Device.objects.filter(ip_address=device_info['ip_address']).first()

            if not existing:
                # 创建新设备
                service.add_device_manually(device_info)
            else:
                # 更新现有设备状态
                existing.status = device_info.get('status', 'online')
                existing.save()

        return {
            'success': True,
            'discovered_count': len(discovered_devices),
            'devices': [d['ip_address'] for d in discovered_devices],
        }

    except Exception as exc:
        return {
            'success': False,
            'error': str(exc),
        }


@shared_task(bind=True, max_retries=3)
def scan_lldp_task(self, seed_device_id: int):
    """
    通过LLDP发现相邻设备任务

    Args:
        seed_device_id: 种子设备ID

    Requirements: 1.2
    """
    from .services import DeviceDiscoveryService
    from .models import Device

    service = DeviceDiscoveryService()

    try:
        seed_device = Device.objects.get(id=seed_device_id)

        # 执行LLDP发现
        discovered_devices = service.discover_via_lldp(seed_device)

        # 保存发现的设备和连接关系
        for device_info in discovered_devices:
            # 检查设备是否已存在
            existing = Device.objects.filter(ip_address=device_info['ip_address']).first()

            if not existing:
                # 创建新设备
                new_device = service.add_device_manually(device_info)

                # 创建拓扑连接关系（需要端口信息）
                # 实际实现需要从LLDP响应中获取端口信息

        return {
            'success': True,
            'discovered_count': len(discovered_devices),
        }

    except Device.DoesNotExist:
        return {
            'success': False,
            'error': f'Device with id {seed_device_id} not found',
        }
    except Exception as exc:
        return {
            'success': False,
            'error': str(exc),
        }


@shared_task(bind=True, max_retries=2)
def scheduled_device_discovery(self):
    """
    定时设备发现任务 - 每2小时执行一次

    Requirements: 1.5
    """
    from .models import Device

    # 获取所有在线设备的IP范围
    # 这里简化处理，实际应该配置扫描范围
    online_devices = Device.objects.filter(status='online')

    if not online_devices:
        return {
            'success': True,
            'message': 'No online devices to use as seed for discovery',
        }

    # 使用第一个在线设备作为种子进行LLDP发现
    seed_device = online_devices.first()

    # 触发LLDP发现任务
    scan_lldp_task.delay(seed_device.id)

    return {
        'success': True,
        'seed_device': seed_device.ip_address,
    }


@shared_task(bind=True, max_retries=3)
def discover_device_details(self, device_id: int):
    """
    发现设备详细信息任务

    Args:
        device_id: 设备ID

    Requirements: 1.4
    """
    from .services import DeviceDiscoveryService
    from .models import Device, Port

    service = DeviceDiscoveryService()

    try:
        device = Device.objects.get(id=device_id)

        # 获取设备详细信息
        details = service.get_device_details(device)

        # 更新设备信息
        device.model = details.get('model', '')
        device.status = details.get('status', device.status)
        device.save()

        # 更新端口信息
        # 先删除旧端口
        device.ports.all().delete()

        # 创建新端口
        for port_info in details.get('ports', []):
            Port.objects.create(
                device=device,
                name=port_info['name'],
                port_type=port_info.get('port_type', ''),
                status=port_info.get('status', ''),
                speed=port_info.get('speed', ''),
                mac_address=port_info.get('mac_address', ''),
            )

        return {
            'success': True,
            'device_id': device_id,
            'ports_count': len(details.get('ports', [])),
        }

    except Device.DoesNotExist:
        return {
            'success': False,
            'error': f'Device with id {device_id} not found',
        }
    except Exception as exc:
        return {
            'success': False,
            'error': str(exc),
        }


@shared_task(bind=True, max_retries=3)
def check_device_online(self):
    """
    定时检测设备在线状态任务

    每60秒对所有设备进行ping测试，检查设备是否在线。
    如果设备离线，同步更新设备状态并触发告警。
    使用并发ping提高检测效率。

    Requirements: 设备管理-定时检测
    """
    from .models import Device

    offline_devices = []
    online_count = 0

    def ping_device(device):
        """对单个设备执行ping检测"""
        result = ping_host(device.ip_address, count=1, timeout=2)
        return device, result.get('reachable', False)

    try:
        # 获取所有设备
        devices = list(Device.objects.all())
        total_devices = len(devices)

        # 使用线程池并发执行ping
        max_workers = min(DEVICE_CHECK_MAX_WORKERS, total_devices)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(ping_device, device): device for device in devices}
            results = []
            for future in as_completed(futures):
                results.append(future.result())

        # 处理结果
        for device, is_online in results:
            if is_online:
                # 在线：更新状态和最后在线时间
                device.last_seen = timezone.now()
                if device.status != 'online':
                    device.status = 'online'
                device.save()
                online_count += 1
            else:
                # 离线：检查状态变化，触发告警
                if device.status == 'online':
                    # 从在线变为离线，触发告警
                    device.status = 'offline'
                    device.save()
                    offline_devices.append(device.ip_address)

                    # 创建离线告警
                    from alerts.services import AlertService
                    alert_service = AlertService()
                    alert_service.create_device_offline_alert(device)
                elif device.status in ['preparing', 'fault']:
                    # 已经是离线状态，只更新状态
                    device.status = 'offline'
                    device.save()

        return {
            'success': True,
            'total_devices': total_devices,
            'online_count': online_count,
            'offline_devices': len(offline_devices),
            'offline_ips': offline_devices,
        }

    except Exception as exc:
        return {
            'success': False,
            'error': str(exc),
        }
