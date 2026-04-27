# 配置管理Celery异步任务
import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


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


@shared_task(
    bind=True,
    max_retries=2,
    time_limit=600,
    soft_time_limit=540,
    queue='low',
)
def backup_all_devices_configs(self, schedule_id: int = None):
    # 定时配置保存任务：在设备上执行 save 命令，然后拉取配置并推送到 GitLab
    from devices.models import Device
    from .models import ConfigFetchSchedule, ConfigFetchLog
    from .services import ConfigManagementService
    from .gitlab_service import ConfigGitlabService
    from logs.models import SystemLog

    config_service = ConfigManagementService()
    gitlab_service = ConfigGitlabService()
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
    successful_device_configs = []

    for target_device in devices:
        try:
            # 第一步：在设备上执行 save 命令并获取配置
            save_result = config_service.save_device_configs(target_device)
            if save_result['success']:
                success_count += 1
                # 收集成功获取的配置内容
                successful_device_configs.append({
                    'device_id': target_device.id,
                    'device_name': target_device.name,
                    'running_config': save_result.get('running_config', ''),
                    'startup_config': save_result.get('startup_config', ''),
                })
            else:
                failure_count += 1
            results.append(save_result)
        except Exception as error:
            failure_count += 1
            results.append({
                'device_id': target_device.id,
                'device_name': target_device.name,
                'success': False,
                'error': str(error)
            })

    # 第二步：将所有成功获取的配置推送到 GitLab（只推送启动配置）
    gitlab_push_success = False
    gitlab_error = None
    if successful_device_configs:
        try:
            gitlab_result = gitlab_service.push_configs(
                successful_device_configs,
                commit_message=f"Scheduled save at {timezone.now().strftime('%Y-%m-%d %H:%M')}",
                startup_only=True
            )
            if gitlab_result.get('success'):
                gitlab_push_success = True
                logger.info(f"配置已推送到 GitLab, commit: {gitlab_result.get('commit_hash', '')}")
            else:
                gitlab_error = gitlab_result.get('error', '未知错误')
                logger.error(f"推送到 GitLab 失败: {gitlab_error}")
        except Exception as error:
            gitlab_error = str(error)
            logger.error(f"推送到 GitLab 异常: {error}")

    SystemLog.objects.create(
        log_type='system',
        message=f"定时配置保存完成: 成功 {success_count} 台, 失败 {failure_count} 台, GitLab推送: {'成功' if gitlab_push_success else '失败'}",
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


@shared_task(
    bind=True,
    max_retries=3,
    time_limit=300,
    soft_time_limit=270,
    queue='low',
)
def backup_single_device_config(self, device_id: int, schedule_id: int = None):
    # 单个设备配置保存任务：执行 save 命令，拉取配置并推送到 GitLab
    from devices.models import Device
    from .models import ConfigFetchSchedule, ConfigFetchLog
    from .services import ConfigManagementService
    from .gitlab_service import ConfigGitlabService

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

    config_service = ConfigManagementService()
    gitlab_service = ConfigGitlabService()

    # 在设备上执行 save 命令并获取配置
    result = config_service.save_device_configs(device)

    # 如果 save 成功，将配置推送到 GitLab
    gitlab_push_success = False
    if result.get('success'):
        try:
            gitlab_result = gitlab_service.push_configs(
                [{
                    'device_id': device.id,
                    'device_name': device.name,
                    'running_config': result.get('running_config', ''),
                    'startup_config': result.get('startup_config', ''),
                }],
                commit_message=f"Manual save for {device.name} at {timezone.now().strftime('%Y-%m-%d %H:%M')}"
            )
            if gitlab_result.get('success'):
                gitlab_push_success = True
                logger.info(f"单设备配置已推送到 GitLab: {device.name}")
            else:
                logger.error(f"单设备配置推送到 GitLab 失败: {gitlab_result.get('error')}")
        except Exception as error:
            logger.error(f"单设备配置推送到 GitLab 异常: {error}")

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


@shared_task(
    bind=True,
    max_retries=2,
    time_limit=300,
    soft_time_limit=270,
    queue='low',
)
def execute_config_task(self, task_id: int):
    # 执行配置任务
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


@shared_task(
    bind=True,
    max_retries=2,
    time_limit=300,
    soft_time_limit=270,
    queue='low',
)
def deploy_single_device_config(self, device_id: int, config: str):
    # 单设备配置下发任务
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


@shared_task(
    bind=True,
    max_retries=2,
    time_limit=600,
    soft_time_limit=540,
    queue='low',
)
def deploy_batch_device_config(self, device_ids: list, config: str):
    # 批量设备配置下发任务（使用Nornir）
    from devices.models import Device
    from .services import ConfigManagementService

    devices = Device.objects.filter(pk__in=device_ids)
    service = ConfigManagementService()
    result = service.deploy_config_batch(list(devices), config)

    return result


@shared_task(
    bind=True,
    max_retries=2,
    time_limit=120,
    soft_time_limit=100,
    queue='low',
)
def execute_scheduled_backup(self):
    # 执行定时配置备份任务，检查并触发到期的备份调度
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


@shared_task(
    bind=True,
    max_retries=2,
    queue='low',
)
def cleanup_old_config_results(self):
    # 清理30天前的配置任务结果
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


@shared_task(
    bind=True,
    max_retries=2,
    time_limit=600,
    soft_time_limit=540,
    queue='low',
)
def preload_device_configs_task(self, schedule_id: int):
    # 预加载设备配置任务，供定时任务调用
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
