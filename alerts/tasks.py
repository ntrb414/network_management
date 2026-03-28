"""
告警 Celery 异步任务

包含告警检查、清理等任务。
"""

from celery import shared_task
from django.utils import timezone


@shared_task(bind=True, max_retries=3)
def check_device_status(self):
    """
    检查设备在线状态任务

    检查设备状态，当设备为离线或故障时生成告警。
    为避免重复告警，仅在该设备当前无同类活动告警时才创建新告警。

    Requirements: 5.1
    """
    from devices.models import Device
    from alerts.models import Alert
    from .services import AlertService

    service = AlertService()
    devices = Device.objects.all()
    alerted = 0

    for device in devices:
        if device.status == 'offline':
            # 检查是否已有活动的离线告警，避免重复
            exists = Alert.objects.filter(
                device=device,
                alert_type='device_offline',
                status='active',
            ).exists()
            if not exists:
                service.create_device_offline_alert(device)
                alerted += 1

        elif device.status == 'fault':
            # 检查是否已有活动的故障告警，避免重复
            exists = Alert.objects.filter(
                device=device,
                alert_type='device_fault',
                status='active',
            ).exists()
            if not exists:
                service.create_device_fault_alert(device)
                alerted += 1

    return {
        'success': True,
        'devices_checked': devices.count(),
        'alerts_created': alerted,
    }


@shared_task(bind=True, max_retries=2)
def cleanup_old_alerts(self):
    """
    清理老旧告警任务

    清理30天前的已处理告警

    Requirements: 5.9
    """
    from .services import AlertService

    service = AlertService()

    result = service.cleanup_old_alerts(days=30)

    return result


@shared_task(bind=True, max_retries=2)
def generate_alert_report(self, days: int = 7):
    """
    生成告警报告任务

    Args:
        days: 报告天数
    """
    from .services import AlertService

    service = AlertService()

    statistics = service.get_alert_statistics(days=days)

    # 可以在这里发送邮件报告
    return {
        'success': True,
        'statistics': statistics,
    }
