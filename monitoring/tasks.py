# 性能监控Celery异步任务
from celery import shared_task
from django.utils import timezone


@shared_task(
    bind=True,
    max_retries=3,
    time_limit=120,
    soft_time_limit=100,
    queue='metrics',
)
def collect_device_metrics(self, device_id: int):
    # 采集设备监控数据并检查阈值
    # 参数: device_id-设备ID
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


@shared_task(
    bind=True,
    max_retries=2,
    time_limit=300,
    soft_time_limit=270,
    queue='metrics',
)
def collect_all_online_devices_metrics(self):
    # 采集所有在线设备监控数据，排除dial_out模式设备
    from devices.models import Device

    # Exclude devices that use 'dial_out' mode, as they push their data to the gRPC receiver
    online_devices = Device.objects.filter(status='online').exclude(telemetry_mode='dial_out')

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


@shared_task(
    bind=True,
    max_retries=2,
    time_limit=300,
    soft_time_limit=270,
    queue='metrics',
)
def collect_ap_devices_metrics(self):
    # 采集AP设备监控数据
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


@shared_task(
    bind=True,
    max_retries=2,
    queue='low',
)
def cleanup_old_metrics(self):
    # 清理过期监控数据，保留24小时
    from .services import MonitoringService

    service = MonitoringService()

    result = service.cleanup_old_metrics(retention_hours=24)

    return result
