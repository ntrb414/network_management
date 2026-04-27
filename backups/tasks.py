"""
配置备份 Celery 异步任务

包含配置备份清理等任务。
"""

from celery import shared_task


@shared_task(
    bind=True,
    max_retries=2,
    queue='low',
)
def cleanup_old_backups(self, days: int = 30):
    # 清理老旧备份任务
    # days 参数指定保留天数
    from .services import BackupService

    service = BackupService()

    result = service.cleanup_old_backups(days=days)

    return result
