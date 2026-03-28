"""
配置管理 Celery 异步任务

包含配置下发、定时备份等异步任务。
需求引用：3.9
"""

from celery import shared_task
from django.utils import timezone


def _get_schedule_devices(schedule):
    from devices.models import Device

    devices = Device.objects.all() if schedule.target_all_devices else schedule.target_devices.all()
    if schedule.only_online_devices:
        devices = devices.filter(status='online')
    return devices


def _matches_exec_days(exec_days, current_time):
    if exec_days == '*':
        return True

    current_day = (current_time.weekday() + 1) % 7
    for part in exec_days.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            start, end = part.split('-', 1)
            try:
                if int(start) <= current_day <= int(end):
                    return True
            except ValueError:
                continue
            continue
        try:
            if int(part) == current_day:
                return True
        except ValueError:
            continue
    return False


def _is_schedule_due(schedule, now):
    if not schedule.enabled:
        return False

    if schedule.exec_mode == 'interval':
        if schedule.last_run_time is None:
            return True
        elapsed = (now - schedule.last_run_time).total_seconds()
        return elapsed >= schedule.interval_seconds

    current_time = timezone.localtime(now)
    if not schedule.exec_time or not _matches_exec_days(schedule.exec_days, current_time):
        return False

    scheduled_at = current_time.replace(
        hour=schedule.exec_time.hour,
        minute=schedule.exec_time.minute,
        second=0,
        microsecond=0,
    )

    delta_seconds = (current_time - scheduled_at).total_seconds()
    if delta_seconds < 0 or delta_seconds >= 60:
        return False

    if schedule.last_run_time is None:
        return True

    return timezone.localtime(schedule.last_run_time) < scheduled_at


@shared_task(bind=True, max_retries=2)
def backup_all_devices_configs(self, schedule_id: int = None):
    """定时备份所有设备配置任务"""
    from devices.models import Device
    from .models import ConfigFetchSchedule, ConfigFetchLog
    from .services import ConfigManagementService
    from logs.models import SystemLog

    service = ConfigManagementService()
    schedule = None
    log = None
    devices = Device.objects.all()

    if schedule_id:
        schedule = ConfigFetchSchedule.objects.filter(pk=schedule_id).first()
        if schedule:
            devices = _get_schedule_devices(schedule)
            schedule.last_run_time = timezone.now()
            schedule.total_run_count += 1
            schedule.save(update_fields=['last_run_time', 'total_run_count'])
            log = ConfigFetchLog.objects.create(
                schedule=schedule,
                status='running',
                total_devices=devices.count(),
            )

    success_count = 0
    failure_count = 0
    results = []

    for device in devices:
        try:
            result = service.backup_device_configs(device)
            if result['success']:
                success_count += 1
            else:
                failure_count += 1
            results.append(result)
        except Exception as e:
            failure_count += 1
            results.append({
                'device_id': device.id,
                'device_name': device.name,
                'success': False,
                'error': str(e)
            })

    SystemLog.objects.create(
        log_type='system',
        message=f"定时配置备份完成: 成功 {success_count} 台, 失败 {failure_count} 台",
        details={'results': results}
    )

    if log and schedule:
        log.end_time = timezone.now()
        log.success_count = success_count
        log.failed_count = failure_count
        log.result_detail = {'results': results}

        if failure_count == 0:
            log.status = 'success'
            schedule.last_run_status = 'success'
        elif success_count == 0:
            log.status = 'failed'
            schedule.last_run_status = 'failed'
        else:
            log.status = 'partial'
            schedule.last_run_status = 'partial'

        log.save()
        schedule.save(update_fields=['last_run_status'])

    return {
        'success': True,
        'total_devices': devices.count(),
        'success_count': success_count,
        'failure_count': failure_count,
    }


@shared_task(bind=True, max_retries=3)
def backup_single_device_config(self, device_id: int, schedule_id: int = None):
    """备份单个设备配置任务"""
    from devices.models import Device
    from .models import ConfigFetchSchedule, ConfigFetchLog
    from .services import ConfigManagementService

    schedule = None
    log = None

    if schedule_id:
        schedule = ConfigFetchSchedule.objects.filter(pk=schedule_id).first()
        if schedule:
            schedule.last_run_time = timezone.now()
            schedule.total_run_count += 1
            schedule.save(update_fields=['last_run_time', 'total_run_count'])
            log = ConfigFetchLog.objects.create(
                schedule=schedule,
                status='running',
                total_devices=1,
            )

    try:
        device = Device.objects.get(pk=device_id)
    except Device.DoesNotExist:
        if log and schedule:
            log.end_time = timezone.now()
            log.status = 'failed'
            log.failed_count = 1
            log.error_message = f'Device with id {device_id} not found'
            log.result_detail = {'results': [{'device_id': device_id, 'success': False, 'error': log.error_message}]}
            log.save()
            schedule.last_run_status = 'failed'
            schedule.save(update_fields=['last_run_status'])
        return {
            'success': False,
            'error': f'Device with id {device_id} not found',
        }

    service = ConfigManagementService()
    result = service.backup_device_configs(device)

    if log and schedule:
        log.end_time = timezone.now()
        log.success_count = 1 if result.get('success') else 0
        log.failed_count = 0 if result.get('success') else 1
        log.status = 'success' if result.get('success') else 'failed'
        log.error_message = result.get('error', '')
        log.result_detail = {
            'results': [{
                'device_id': device.id,
                'device_name': device.name,
                'success': result.get('success', False),
                'error': result.get('error', ''),
            }]
        }
        log.save()
        schedule.last_run_status = log.status
        schedule.save(update_fields=['last_run_status'])

    return result


@shared_task(bind=True, max_retries=2)
def execute_config_task(self, task_id: int):
    """执行配置任务"""
    from .models import ConfigTask
    from .services import ConfigManagementService

    try:
        task = ConfigTask.objects.get(pk=task_id)
    except ConfigTask.DoesNotExist:
        return {
            'success': False,
            'error': f'Task with id {task_id} not found',
        }

    service = ConfigManagementService()

    try:
        result = service.execute_task(task)

        from logs.models import SystemLog
        SystemLog.objects.create(
            log_type='system',
            user=task.created_by,
            message=f"配置任务执行完成: {task.name}",
            details=result,
        )

        return result

    except Exception as exc:
        task.status = 'failed'
        task.save()

        return {
            'success': False,
            'error': str(exc),
        }


@shared_task(bind=True, max_retries=2)
def deploy_single_device_config(self, device_id: int, config: str):
    """单设备配置下发任务"""
    from devices.models import Device
    from .services import ConfigManagementService

    try:
        device = Device.objects.get(pk=device_id)
    except Device.DoesNotExist:
        return {
            'success': False,
            'error': f'Device with id {device_id} not found',
        }

    service = ConfigManagementService()
    result = service.deploy_config(device, config)

    return result


@shared_task(bind=True, max_retries=2)
def deploy_batch_device_config(self, device_ids: list, config: str):
    """批量设备配置下发任务（使用 Nornir）"""
    from devices.models import Device
    from .services import ConfigManagementService

    devices = Device.objects.filter(pk__in=device_ids)
    service = ConfigManagementService()
    result = service.deploy_config_batch(list(devices), config)

    return result


@shared_task(bind=True, max_retries=2)
def execute_scheduled_backup(self):
    """执行定时配置备份任务"""
    from .models import ConfigFetchSchedule
    import logging
    
    logger = logging.getLogger(__name__)
    now = timezone.now()
    
    try:
        schedules = ConfigFetchSchedule.objects.filter(task_type='backup', enabled=True).order_by('id')
        
        if not schedules.exists():
            logger.warning("未找到启用的配置备份调度")
            return {'success': False, 'error': '未找到启用的备份调度'}

        triggered = []
        for schedule in schedules:
            if not _is_schedule_due(schedule, now):
                continue

            job = backup_all_devices_configs.delay(schedule.id)
            triggered.append({
                'schedule_id': schedule.id,
                'schedule_name': schedule.name,
                'job_id': job.id,
            })

        if not triggered:
            return {'success': True, 'message': '当前无到期的备份任务', 'triggered_count': 0}

        logger.info(f"定时配置备份已触发: {triggered}")
        return {'success': True, 'triggered_count': len(triggered), 'jobs': triggered}
        
    except Exception as exc:
        logger.error(f"定时配置备份执行失败: {exc}")
        return {'success': False, 'error': str(exc)}


@shared_task(bind=True, max_retries=2)
def cleanup_old_config_results(self):
    """清理旧的配置任务结果"""
    from datetime import timedelta
    from .models import ConfigTaskResult

    cutoff_date = timezone.now() - timedelta(days=30)

    deleted_count = ConfigTaskResult.objects.filter(
        executed_at__lt=cutoff_date
    ).delete()[0]

    return {
        'success': True,
        'deleted_count': deleted_count,
    }


@shared_task(bind=True, max_retries=2)
def preload_device_configs_task(self, schedule_id: int):
    """预加载设备配置任务（供定时任务调用）"""
    import logging
    logger = logging.getLogger(__name__)

    from devices.models import Device
    from .models import ConfigFetchSchedule, ConfigFetchLog
    from .services import ConfigManagementService

    try:
        schedule = ConfigFetchSchedule.objects.get(pk=schedule_id)
    except ConfigFetchSchedule.DoesNotExist:
        logger.error(f"定时任务不存在: {schedule_id}")
        return {'success': False, 'error': 'Schedule not found'}

    log = ConfigFetchLog.objects.create(
        schedule=schedule,
        status='running'
    )

    schedule.last_run_time = timezone.now()
    schedule.total_run_count += 1
    schedule.save()

    if schedule.target_all_devices:
        devices = Device.objects.all()
        if schedule.only_online_devices:
            devices = devices.filter(status='online')
    else:
        devices = schedule.target_devices.all()
        if schedule.only_online_devices:
            devices = devices.filter(status='online')

    total_devices = devices.count()
    log.total_devices = total_devices
    log.save()

    service = ConfigManagementService()
    success_count = 0
    failed_count = 0
    results = []

    logger.info(f"开始预加载配置: {schedule.name}, 设备数: {total_devices}")

    for device in devices:
        try:
            running_config = service.get_current_config(device, use_cache=False)
            startup_config = service.get_startup_config(device, use_cache=False)

            success_count += 1
            results.append({
                'device_id': device.id,
                'device_name': device.name,
                'success': True,
            })
            logger.debug(f"配置获取成功: {device.name}")

        except Exception as e:
            failed_count += 1
            results.append({
                'device_id': device.id,
                'device_name': device.name,
                'success': False,
                'error': str(e),
            })
            logger.error(f"配置获取失败: {device.name}, 错误: {e}")

    log.end_time = timezone.now()
    log.success_count = success_count
    log.failed_count = failed_count
    log.result_detail = {'results': results}

    if failed_count == 0:
        log.status = 'success'
        schedule.last_run_status = 'success'
    elif success_count == 0:
        log.status = 'failed'
        schedule.last_run_status = 'failed'
    else:
        log.status = 'partial'
        schedule.last_run_status = 'partial'

    log.save()
    schedule.save()

    logger.info(f"配置预加载完成: 成功 {success_count}, 失败 {failed_count}")

    return {
        'success': True,
        'schedule_id': schedule_id,
        'total_devices': total_devices,
        'success_count': success_count,
        'failed_count': failed_count,
    }
