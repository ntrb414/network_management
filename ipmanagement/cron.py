"""
IP Management Cron Jobs

已废弃 - 定时任务现在由 Celery Beat 直接调度
此文件保留用于参考，不再被调用

历史 cron 配置:
- scan_subnets_periodic: 每小时 -> ipmanagement.tasks.auto_scan_all_subnets
"""
