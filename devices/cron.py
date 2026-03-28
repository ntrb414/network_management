"""
设备管理定时任务模块

已废弃 - 定时任务现在由 Celery Beat 直接调度
此文件保留用于参考，不再被调用

历史 cron 配置:
- check_devices_status: 每分钟 -> devices.tasks.check_device_online
- discover_devices: 每2小时 -> devices.tasks.scheduled_device_discovery
"""
