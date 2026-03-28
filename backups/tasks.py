"""
配置备份 Celery 异步任务

包含定时备份、清理等任务。
"""

from celery import shared_task


@shared_task(bind=True, max_retries=2)
def backup_all_devices(self):
    """
    备份所有设备配置任务

    遍历所有设备进行配置备份

    Requirements: 8.1
    """
    from devices.models import Device
    from configs.services import ConfigManagementService
    from .services import BackupService

    backup_service = BackupService()
    config_service = ConfigManagementService()

    devices = Device.objects.all()
    success_count = 0
    failed_count = 0

    for device in devices:
        # 通过 ConfigManagementService 获取设备真实配置
        try:
            config_content = config_service.get_current_config(device, use_cache=True)
            if not config_content:
                config_content = f"# Configuration backup for {device.name}\n# IP: {device.ip_address}\n# Type: {device.device_type}\n# Warning: No config retrieved from device"
        except Exception as e:
            config_content = f"# Configuration backup for {device.name}\n# IP: {device.ip_address}\n# Type: {device.device_type}\n# Error: {e}"

        result = backup_service.backup_device_config(
            device=device,
            config_content=config_content,
            commit_message=f"Auto backup for {device.name}",
        )

        if result.get('success'):
            success_count += 1
        else:
            failed_count += 1

    return {
        'success': True,
        'total_devices': devices.count(),
        'success_count': success_count,
        'failed_count': failed_count,
    }


@shared_task(bind=True, max_retries=3)
def backup_single_device(self, device_id: int, commit_message: str = ''):
    """
    备份单个设备配置任务

    Args:
        device_id: 设备ID
        commit_message: 可选的提交说明
    """
    from devices.models import Device
    from configs.services import ConfigManagementService
    from .services import BackupService

    backup_service = BackupService()

    try:
        device = Device.objects.get(id=device_id)
    except Device.DoesNotExist:
        return {
            'success': False,
            'error': 'Device not found',
        }

    # 通过 ConfigManagementService 获取设备真实配置（优先 Redis 缓存，其次 SSH）
    try:
        config_service = ConfigManagementService()
        config_content = config_service.get_current_config(device, use_cache=True)
        if not config_content:
            config_content = f"# Configuration backup for {device.name}\n# IP: {device.ip_address}\n# Type: {device.device_type}\n# Warning: No config retrieved from device"
    except Exception as e:
        config_content = f"# Configuration backup for {device.name}\n# IP: {device.ip_address}\n# Type: {device.device_type}\n# Error retrieving config: {e}"

    msg = commit_message if commit_message else f"Manual backup for {device.name}"

    result = backup_service.backup_device_config(
        device=device,
        config_content=config_content,
        commit_message=msg,
    )

    return result


@shared_task(bind=True, max_retries=2)
def cleanup_old_backups(self, days: int = 30):
    """
    清理老旧备份任务

    Args:
        days: 保留天数

    Requirements: 8.7
    """
    from .services import BackupService

    service = BackupService()

    result = service.cleanup_old_backups(days=days)

    return result
