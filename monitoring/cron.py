"""
监控模块定时任务模块

已废弃 - 定时任务现在由 Celery Beat 直接调度
此文件保留用于参考，不再被调用

历史 cron 配置:
- collect_online_devices_metrics: 每分钟 -> monitoring.tasks.collect_all_online_devices_metrics
- cleanup_metrics: 每小时 -> monitoring.tasks.cleanup_old_metrics
"""
