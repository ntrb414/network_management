"""
性能监控 Celery 异步任务

包含监控数据采集、清理等任务。
需求引用：4.2, 4.3, 4.6
"""

from celery import shared_task
from django.utils import timezone


@shared_task(bind=True, max_retries=3)
def collect_device_metrics(self, device_id: int):
    """
    采集设备监控数据任务

    Args:
        device_id: 设备ID

    Requirements: 4.1, 4.2, 4.3
    """
    from devices.models import Device
    from .services import MonitoringService

    try:
        device = Device.objects.get(pk=device_id)
    except Device.DoesNotExist:
        return {
            'success': False,
            'error': f'Device with id {device_id} not found',
        }

    service = MonitoringService()

    try:
        # 采集指标
        metrics = service.collect_metrics(device)

        # 存储指标
        stored_count = service.store_metrics(device, metrics)

        # 检查阈值
        alerts = service.check_thresholds(device, metrics)

        return {
            'success': True,
            'device_id': device_id,
            'stored_count': stored_count,
            'alerts_count': len(alerts),
        }

    except Exception as exc:
        return {
            'success': False,
            'error': str(exc),
        }


@shared_task(bind=True, max_retries=2)
def collect_all_online_devices_metrics(self):
    """
    采集所有在线设备的监控数据

    根据设备类型使用不同的采集策略:
    - AP: 实时采集 (实际上会更频繁)
    - 其他: 每5分钟采集一次

    Requirements: 4.2, 4.3
    """
    from devices.models import Device

    online_devices = Device.objects.filter(status='online')

    results = []

    for device in online_devices:
        # 触发采集任务
        collect_device_metrics.delay(device.id)
        results.append({
            'device_id': device.id,
            'device_name': device.name,
        })

    return {
        'success': True,
        'devices_count': len(results),
        'results': results,
    }


@shared_task(bind=True, max_retries=2)
def collect_ap_devices_metrics(self):
    """
    采集AP设备监控数据 (实时采集)

    Requirements: 4.2
    """
    from devices.models import Device

    ap_devices = Device.objects.filter(
        status='online',
        device_type='ap'
    )

    results = []

    for device in ap_devices:
        collect_device_metrics.delay(device.id)
        results.append({
            'device_id': device.id,
        })

    return {
        'success': True,
        'devices_count': len(results),
        'results': results,
    }


@shared_task(bind=True, max_retries=2)
def cleanup_old_metrics(self):
    """
    清理过期的监控数据

    保留24小时的数据

    Requirements: 4.6
    """
    from .services import MonitoringService

    service = MonitoringService()

    result = service.cleanup_old_metrics(retention_hours=24)

    return result
