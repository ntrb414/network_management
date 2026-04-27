# 告警Celery异步任务
from celery import shared_task
from django.utils import timezone


@shared_task(
    bind=True,
    max_retries=3,
    time_limit=30,
    soft_time_limit=25,
    queue='critical',
)
def check_device_status(self):
    # 检查设备在线状态（已被check_device_online替代，保留兼容）
    return {
        'success': True,
        'devices_checked': 0,
        'alerts_created': 0,
        'message': '此任务已被 check_device_online 替代，不再执行独立告警检查',
    }


@shared_task(
    bind=True,
    max_retries=2,
    queue='low',
)
def cleanup_old_alerts(self):
    # 清理30天前的已处理告警
    from .services import AlertService

    service = AlertService()

    result = service.cleanup_old_alerts(days=30)

    return result


@shared_task(
    bind=True,
    max_retries=2,
    queue='low',
)
def generate_alert_report(self, days: int = 7):
    # 生成告警统计报告
    # 参数: days-统计天数
    from .services import AlertService

    service = AlertService()

    statistics = service.get_alert_statistics(days=days)

    # 可以在这里发送邮件报告
    return {
        'success': True,
        'statistics': statistics,
    }
