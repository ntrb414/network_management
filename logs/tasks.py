"""
日志 Celery 异步任务

包含日志清理、日志采集等任务。
"""

from celery import shared_task


@shared_task(bind=True, max_retries=2)
def cleanup_old_logs(self, days: int = 7):
    """
    清理老旧日志任务

    清理指定天数前的日志

    """
    from .services import LogService

    service = LogService()

    result = service.cleanup_old_logs(days=days)

    return result


@shared_task(bind=True, max_retries=2)
def generate_log_report(self, days: int = 7):
    """
    生成日志报告任务

    Args:
        days: 报告天数
    """
    from .services import LogService

    service = LogService()

    statistics = service.get_statistics(days=days)

    # 可以在这里发送邮件报告
    return {
        'success': True,
        'statistics': statistics,
    }


@shared_task(bind=True, max_retries=2)
def collect_device_logs(self, device_id: int):
    """
    采集单个设备日志任务

    Args:
        device_id: 设备ID

    """
    from devices.models import Device
    from .services import LogService

    try:
        device = Device.objects.get(pk=device_id)
    except Device.DoesNotExist:
        return {
            'success': False,
            'error': f'Device with id {device_id} not found',
        }

    service = LogService()
    result = service.collect_logs_from_device(device)

    return result


@shared_task(bind=True, max_retries=2)
def collect_all_online_devices_logs(self):
    """
    采集所有在线设备日志任务

    遍历所有在线设备，通过SSH采集日志并存储到数据库

    """
    from devices.models import Device
    from .services import LogService

    online_devices = Device.objects.filter(status='online')

    results = []
    success_count = 0
    failure_count = 0

    for device in online_devices:
        service = LogService()
        result = service.collect_logs_from_device(device)
        results.append(result)

        if result.get('success'):
            success_count += 1
        else:
            failure_count += 1

    return {
        'success': True,
        'total_online_devices': online_devices.count(),
        'success_count': success_count,
        'failure_count': failure_count,
        'results': results,
    }
