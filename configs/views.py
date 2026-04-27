# 配置管理页面视图和API
from django.views.generic import ListView, DetailView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import ConfigTemplate, ConfigTask, ConfigTaskResult
from .models import ConfigFetchSchedule, ConfigFetchLog
from devices.models import Device
from django.core.cache import cache


def _get_or_create_backup_schedule(user=None):
    from datetime import time

    existing = ConfigFetchSchedule.objects.filter(name='配置备份任务').order_by('id').first()
    if existing:
        updated_fields = []
        if existing.task_type != 'backup':
            existing.task_type = 'backup'
            updated_fields.append('task_type')
        if updated_fields:
            existing.save(update_fields=updated_fields)
        return existing, False

    defaults = {
        'task_type': 'backup',
        'enabled': True,
        'exec_mode': 'cron',
        'exec_time': time(2, 0),
        'exec_days': '*',
        'target_all_devices': True,
        'device_selection_mode': 'multiple',
        'only_online_devices': True,
    }
    if user is not None:
        defaults['created_by'] = user

    return ConfigFetchSchedule.objects.get_or_create(
        name='配置备份任务',
        task_type='backup',
        defaults=defaults,
    )


def _to_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _normalize_device_ids(raw_value):
    if raw_value is None:
        return []
    if isinstance(raw_value, str):
        values = [item.strip() for item in raw_value.split(',') if item.strip()]
    elif isinstance(raw_value, (list, tuple)):
        values = raw_value
    else:
        values = [raw_value]

    normalized = []
    for value in values:
        try:
            normalized.append(int(value))
        except (TypeError, ValueError):
            continue
    return normalized


def _serialize_schedule(schedule):
    target_devices = list(schedule.target_devices.all())
    latest_log = schedule.logs.first()

    if schedule.target_all_devices:
        target_scope = '全部在线设备' if schedule.only_online_devices else '全部设备'
    elif target_devices:
        target_scope = f'指定设备 ({len(target_devices)} 台)'
    else:
        target_scope = '未选择设备'

    return {
        'id': schedule.id,
        'name': schedule.name,
        'task_type': schedule.task_type,
        'task_type_display': schedule.get_task_type_display(),
        'enabled': schedule.enabled,
        'exec_mode': schedule.exec_mode,
        'exec_mode_display': schedule.get_exec_mode_display(),
        'exec_plan': _format_exec_plan(schedule),
        'interval_seconds': schedule.interval_seconds,
        'exec_time': schedule.exec_time.strftime('%H:%M') if schedule.exec_time else None,
        'exec_days': schedule.exec_days,
        'target_all_devices': schedule.target_all_devices,
        'device_selection_mode': schedule.device_selection_mode,
        'device_selection_mode_display': schedule.get_device_selection_mode_display(),
        'only_online_devices': schedule.only_online_devices,
        'target_scope': target_scope,
        'target_devices': [device.id for device in target_devices],
        'target_devices_detail': [
            {
                'id': device.id,
                'name': device.name,
                'ip_address': device.ip_address,
                'status': device.status,
                'device_type': device.device_type,
            }
            for device in target_devices
        ],
        'queue': schedule.queue,
        'max_concurrent': schedule.max_concurrent,
        'last_run_time': schedule.last_run_time.isoformat() if schedule.last_run_time else None,
        'last_run_status': schedule.last_run_status,
        'total_run_count': schedule.total_run_count,
        'latest_result': {
            'status': latest_log.status,
            'success_count': latest_log.success_count,
            'failed_count': latest_log.failed_count,
            'total_devices': latest_log.total_devices,
            'start_time': latest_log.start_time.isoformat(),
            'end_time': latest_log.end_time.isoformat() if latest_log.end_time else None,
        } if latest_log else None,
    }


def _save_schedule_from_request(schedule, request):
    schedule.name = request.data.get('name', schedule.name)
    schedule.task_type = request.data.get('task_type', schedule.task_type)
    schedule.enabled = _to_bool(request.data.get('enabled'), schedule.enabled)
    schedule.exec_mode = request.data.get('exec_mode', schedule.exec_mode)
    schedule.interval_seconds = int(request.data.get('interval_seconds', schedule.interval_seconds))

    exec_time = request.data.get('exec_time')
    if exec_time:
        from datetime import datetime
        schedule.exec_time = datetime.strptime(exec_time, '%H:%M').time()

    schedule.exec_days = request.data.get('exec_days', schedule.exec_days)
    schedule.target_all_devices = _to_bool(request.data.get('target_all_devices'), schedule.target_all_devices)
    schedule.device_selection_mode = request.data.get('device_selection_mode', schedule.device_selection_mode)
    schedule.only_online_devices = _to_bool(request.data.get('only_online_devices'), schedule.only_online_devices)
    schedule.queue = request.data.get('queue', schedule.queue)
    schedule.max_concurrent = int(request.data.get('max_concurrent', schedule.max_concurrent))

    target_device_ids = _normalize_device_ids(request.data.get('target_devices'))
    if schedule.device_selection_mode == 'single' and len(target_device_ids) > 1:
        target_device_ids = target_device_ids[:1]

    if not schedule.target_all_devices and not target_device_ids:
        return False, Response({'error': '请选择至少一台备份设备'}, status=400)

    schedule.save()
    schedule.target_devices.set(target_device_ids)
    return True, None


# ==================== 页面视图 ====================

class ConfigListView(LoginRequiredMixin, ListView):
    # 配置管理首页
    template_name = 'configs/config_list.html'
    context_object_name = 'configs'
    login_url = 'homepage:login'
    paginate_by = 20

    def get_queryset(self):
        return ConfigTemplate.objects.all().order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        context['tasks'] = ConfigTask.objects.all().order_by('-created_at')[:10]
        # 从 ConfigBackupView 迁移：最近备份版本记录
        from backups.models import ConfigBackup
        context['recent_backups'] = ConfigBackup.objects.select_related('device', 'backed_up_by').order_by('-backed_up_at')[:10]
        return context


class ConfigDetailView(LoginRequiredMixin, DetailView):
    # 配置模板详情页面
    model = ConfigTemplate
    template_name = 'configs/config_detail.html'
    context_object_name = 'config'
    login_url = 'homepage:login'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        context['tasks'] = self.object.tasks.all().order_by('-created_at')
        return context


# ==================== 模板 API ====================

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def config_template_list_api(request):
    # 配置模板列表API：GET获取列表，POST创建模板
    if request.method == 'GET':
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))

        templates = ConfigTemplate.objects.all().order_by('-updated_at')
        paginator = Paginator(templates, page_size)

        try:
            templates_page = paginator.page(page)
        except PageNotAnInteger:
            templates_page = paginator.page(1)
        except EmptyPage:
            templates_page = paginator.page(paginator.num_pages)

        templates_data = []
        for template in templates_page:
            templates_data.append({
                'id': template.id,
                'name': template.name,
                'description': template.description,
                'template_type': template.template_type,
                'template_type_display': template.get_template_type_display(),
                'device_types': template.device_types,
                'created_by': template.created_by.username if template.created_by else None,
                'created_at': template.created_at.isoformat(),
                'updated_at': template.updated_at.isoformat(),
            })

        return Response({
            'count': paginator.count,
            'total_pages': paginator.num_pages,
            'current_page': page,
            'page_size': page_size,
            'results': templates_data,
        })

    elif request.method == 'POST':
        template = ConfigTemplate.objects.create(
            name=request.data.get('name'),
            description=request.data.get('description', ''),
            template_type=request.data.get('template_type', 'device_commands'),
            device_types=request.data.get('device_types', []),
            template_content=request.data.get('template_content', ''),
            variables_schema=request.data.get('variables_schema', {}),
            created_by=request.user,
        )
        return Response({
            'id': template.id,
            'name': template.name,
            'message': '模板创建成功',
        }, status=201)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def config_template_detail_api(request, pk):
    # 配置模板详情API：GET获取，PUT更新，DELETE删除
    try:
        template = ConfigTemplate.objects.get(pk=pk)
    except ConfigTemplate.DoesNotExist:
        return Response({'error': '模板不存在'}, status=404)

    if request.method == 'GET':
        return Response({
            'id': template.id,
            'name': template.name,
            'description': template.description,
            'template_type': template.template_type,
            'device_types': template.device_types,
            'template_content': template.template_content,
            'variables_schema': template.variables_schema,
            'created_by': template.created_by.username if template.created_by else None,
            'created_at': template.created_at.isoformat(),
            'updated_at': template.updated_at.isoformat(),
        })

    elif request.method == 'PUT':
        template.name = request.data.get('name', template.name)
        template.description = request.data.get('description', template.description)
        template.template_type = request.data.get('template_type', template.template_type)
        template.device_types = request.data.get('device_types', template.device_types)
        template.template_content = request.data.get('template_content', template.template_content)
        template.variables_schema = request.data.get('variables_schema', template.variables_schema)
        template.save()
        return Response({
            'id': template.id,
            'name': template.name,
            'message': '模板更新成功',
        })

    elif request.method == 'DELETE':
        template.delete()
        return Response(status=204)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def validate_template_api(request):
    # 验证配置模板API
    template_content = request.data.get('template_content', '')
    template_type = request.data.get('template_type', 'device_commands')
    variables = request.data.get('variables', {})

    if template_type == 'device_commands':
        return Response({
            'valid': True,
            'rendered': template_content,
        })

    try:
        from jinja2 import Template
        template = Template(template_content)
        rendered = template.render(**variables)
        return Response({
            'valid': True,
            'rendered': rendered,
        })
    except Exception as e:
        return Response({
            'valid': False,
            'error': str(e),
        })


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def config_task_list_api(request):
    # 配置任务列表API：GET获取列表，POST创建任务
    if request.method == 'GET':
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))

        tasks = ConfigTask.objects.select_related('template', 'created_by').all().order_by('-created_at')
        paginator = Paginator(tasks, page_size)

        try:
            tasks_page = paginator.page(page)
        except PageNotAnInteger:
            tasks_page = paginator.page(1)
        except EmptyPage:
            tasks_page = paginator.page(paginator.num_pages)

        tasks_data = []
        for task in tasks_page:
            tasks_data.append({
                'id': task.id,
                'name': task.name,
                'template_id': task.template_id,
                'template_name': task.template.name if task.template else None,
                'status': task.status,
                'status_display': task.get_status_display(),
                'device_count': task.devices.count(),
                'created_by': task.created_by.username if task.created_by else None,
                'created_at': task.created_at.isoformat(),
                'executed_at': task.executed_at.isoformat() if task.executed_at else None,
            })

        return Response({
            'count': paginator.count,
            'total_pages': paginator.num_pages,
            'current_page': page,
            'page_size': page_size,
            'results': tasks_data,
        })

    elif request.method == 'POST':
        from .services import ConfigManagementService

        template_id = request.data.get('template_id')
        device_ids = request.data.get('device_ids', [])
        variables = request.data.get('variables', {})
        config_content = request.data.get('config_content', '')

        template = None
        if template_id:
            try:
                template = ConfigTemplate.objects.get(pk=template_id)
            except ConfigTemplate.DoesNotExist:
                return Response({'error': '模板不存在'}, status=404)

        devices = Device.objects.filter(pk__in=device_ids)

        if template:
            try:
                config_content = template.render(variables)
            except Exception as e:
                return Response({'error': f'模板渲染失败: {e}'}, status=400)

        task = ConfigTask.objects.create(
            name=request.data.get('name', f'配置任务'),
            template=template,
            variables=variables,
            config_content=config_content,
            status='pending',
            created_by=request.user,
        )
        task.devices.set(devices)

        return Response({
            'id': task.id,
            'name': task.name,
            'status': task.status,
            'message': '任务创建成功',
        }, status=201)


@api_view(['GET', 'DELETE'])
@permission_classes([IsAuthenticated])
def config_task_detail_api(request, pk):
    # 配置任务详情API
    try:
        task = ConfigTask.objects.prefetch_related('results__device', 'devices', 'template').get(pk=pk)
    except ConfigTask.DoesNotExist:
        return Response({'error': '任务不存在'}, status=404)

    if request.method == 'GET':
        latest_results = {}
        ordered_results = task.results.select_related('device').all().order_by('device_id', '-executed_at', '-id')
        for result in ordered_results:
            if result.device_id in latest_results:
                continue
            latest_results[result.device_id] = result

        results = []
        for result in latest_results.values():
            results.append({
                'device_id': result.device.id,
                'device_name': result.device.name,
                'success': result.success,
                'error_message': result.error_message,
                'executed_at': result.executed_at.isoformat(),
            })

        return Response({
            'id': task.id,
            'name': task.name,
            'template': {
                'id': task.template.id,
                'name': task.template.name,
            } if task.template else None,
            'status': task.status,
            'status_display': task.get_status_display(),
            'variables': task.variables,
            'config_content': task.config_content,
            'devices': [{'id': d.id, 'name': d.name} for d in task.devices.all()],
            'results': results,
            'created_by': task.created_by.username if task.created_by else None,
            'created_at': task.created_at.isoformat(),
            'executed_at': task.executed_at.isoformat() if task.executed_at else None,
        })

    elif request.method == 'DELETE':
        task.delete()
        return Response(status=204)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def config_task_execute_api(request, pk):
    # 执行配置任务API
    from .tasks import execute_config_task

    try:
        task = ConfigTask.objects.get(pk=pk)
    except ConfigTask.DoesNotExist:
        return Response({'error': '任务不存在'}, status=404)

    if task.status == 'executing':
        return Response({'error': '任务正在执行中'}, status=400)

    # Update state immediately so UI won't flip-flop to "pending" upon early refresh
    if task.status != 'executing':
        task.status = 'executing'
        task.save(update_fields=['status'])

    job = execute_config_task.delay(task.id)

    return Response({
        'id': task.id,
        'job_id': job.id,
        'message': '任务已开始执行',
    })


# ==================== 备份 API ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def config_backup_trigger_api(request):
    # 触发配置备份API：单设备或全量备份
    device_id = request.data.get('device_id')
    schedule, _ = _get_or_create_backup_schedule(request.user)
    
    if device_id:
        # 单设备备份
        from .tasks import backup_single_device_config
        job = backup_single_device_config.delay(device_id, schedule.id)
        return Response({
            'job_id': job.id,
            'message': f'设备 {device_id} 备份任务已触发',
            'device_id': device_id,
            'schedule_id': schedule.id,
        })
    else:
        # 全量备份
        from .tasks import backup_all_devices_configs
        job = backup_all_devices_configs.delay(schedule.id)
        return Response({
            'job_id': job.id,
            'message': '备份任务已触发',
            'schedule_id': schedule.id,
        })


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def config_backup_schedule_api(request):
    # 配置备份调度API：GET获取，POST更新
    from datetime import datetime
    
    if request.method == 'GET':
        schedule, _ = _get_or_create_backup_schedule(request.user)
        
        return Response({
            'id': schedule.id,
            'task_type': schedule.task_type,
            'backup_time': schedule.exec_time.strftime('%H:%M'),
            'is_active': schedule.enabled,
            'exec_mode': schedule.exec_mode,
            'exec_days': schedule.exec_days,
            'target_all_devices': schedule.target_all_devices,
            'only_online_devices': schedule.only_online_devices,
            'last_run_time': schedule.last_run_time.isoformat() if schedule.last_run_time else None,
            'last_run_status': schedule.last_run_status,
            'total_run_count': schedule.total_run_count,
        })
    
    elif request.method == 'POST':
        backup_time = request.data.get('backup_time', '02:00')
        is_active = request.data.get('is_active', True)
        
        # 更新或创建备份调度
        schedule, created = ConfigFetchSchedule.objects.update_or_create(
            name='配置备份任务',
            task_type='backup',
            defaults={
                'task_type': 'backup',
                'enabled': is_active,
                'exec_mode': 'cron',
                'exec_time': datetime.strptime(backup_time, '%H:%M').time(),
                'exec_days': '*',
                'target_all_devices': True,
                'device_selection_mode': 'multiple',
                'only_online_devices': True,
                'created_by': request.user,
            }
        )
        
        return Response({
            'success': True,
            'id': schedule.id,
            'backup_time': backup_time,
            'message': f'备份时间已设置为每天 {backup_time}',
        })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def config_backup_status_api(request):
    # 配置备份状态API：返回各设备备份时间
    from .services import ConfigManagementService

    service = ConfigManagementService()
    devices = Device.objects.all()

    devices_status = []
    for device in devices:
        running_time = service.get_config_cache_time(device.id, 'running')
        startup_time = service.get_config_cache_time(device.id, 'startup')

        devices_status.append({
            'device_id': device.id,
            'device_name': device.name,
            'device_ip': device.ip_address,
            'running_config_backup_time': running_time,
            'startup_config_backup_time': startup_time,
            'has_cached_config': bool(running_time or startup_time),
        })

    return Response({
        'devices': devices_status,
    })


# ==================== 定时任务 API ====================

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def schedule_list_api(request):
    # 定时任务列表API
    if request.method == 'GET':
        task_type = request.GET.get('task_type')
        schedules = ConfigFetchSchedule.objects.prefetch_related('target_devices', 'logs').all().order_by('-created_at')
        if task_type:
            schedules = schedules.filter(task_type=task_type)

        schedules_data = [_serialize_schedule(schedule) for schedule in schedules]
        return Response({'schedules': schedules_data})

    elif request.method == 'POST':
        task_type = request.data.get('task_type', 'preload')
        default_name = '定时备份任务' if task_type == 'backup' else '设备配置预加载'
        schedule = ConfigFetchSchedule.objects.create(
            name=request.data.get('name', default_name),
            task_type=task_type,
            created_by=request.user,
        )

        is_valid, error_response = _save_schedule_from_request(schedule, request)
        if not is_valid:
            schedule.delete()
            return error_response

        return Response({
            'success': True,
            'id': schedule.id,
            'schedule': _serialize_schedule(schedule),
            'message': '定时任务已创建',
        }, status=201)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def schedule_detail_api(request, pk):
    # 定时任务详情API
    try:
        schedule = ConfigFetchSchedule.objects.get(pk=pk)
    except ConfigFetchSchedule.DoesNotExist:
        return Response({'error': '定时任务不存在'}, status=404)

    if request.method == 'GET':
        return Response(_serialize_schedule(schedule))

    elif request.method == 'PUT':
        is_valid, error_response = _save_schedule_from_request(schedule, request)
        if not is_valid:
            return error_response

        return Response({
            'success': True,
            'id': schedule.id,
            'schedule': _serialize_schedule(schedule),
            'message': '定时任务已更新',
        })

    elif request.method == 'DELETE':
        schedule.delete()
        return Response(status=204)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def schedule_run_api(request, pk):
    # 立即执行定时任务API
    from .tasks import backup_all_devices_configs, preload_device_configs_task
    from celery.result import AsyncResult

    try:
        schedule = ConfigFetchSchedule.objects.get(pk=pk)
    except ConfigFetchSchedule.DoesNotExist:
        return Response({'error': '定时任务不存在'}, status=404)

    if schedule.task_type == 'backup':
        job = backup_all_devices_configs.delay(schedule.id)
    else:
        job = preload_device_configs_task.delay(schedule.id)

    return Response({
        'in_line': True,
        'job_id': job.id,
        'task_type': schedule.task_type,
        'message': '任务已提交，正在执行中',
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def task_status_api(request, job_id):
    # 查询Celery任务状态API
    from celery.result import AsyncResult
    from network_management.celery import app

    result = AsyncResult(job_id, app=app)

    response_data = {
        'job_id': job_id,
        'status': result.state,
        'is_finish': result.ready(),
    }

    if result.ready():
        # 任务已完成
        if result.successful():
            response_data['success'] = True
            response_data['result'] = result.result
        else:
            response_data['success'] = False
            try:
                response_data['error'] = str(result.result)
            except Exception:
                response_data['error'] = '任务执行失败'
    else:
        # 任务还在执行中或排队中
        response_data['in_line'] = True
        if result.state == 'PENDING':
            response_data['message'] = '任务在队列中等待执行'
        elif result.state == 'STARTED':
            response_data['message'] = '任务正在执行中'
        else:
            response_data['message'] = f'任务状态: {result.state}'

    return Response(response_data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def schedule_logs_api(request, pk):
    # 定时任务执行日志API
    try:
        schedule = ConfigFetchSchedule.objects.get(pk=pk)
    except ConfigFetchSchedule.DoesNotExist:
        return Response({'error': '定时任务不存在'}, status=404)

    logs = schedule.logs.all()[:20]
    logs_data = []
    for log in logs:
        logs_data.append({
            'id': log.id,
            'start_time': log.start_time.isoformat(),
            'end_time': log.end_time.isoformat() if log.end_time else None,
            'status': log.status,
            'total_devices': log.total_devices,
            'success_count': log.success_count,
            'failed_count': log.failed_count,
            'error_message': log.error_message,
            'result_detail': log.result_detail,
        })

    return Response({'logs': logs_data})


def _format_exec_plan(schedule):
    # 格式化执行计划显示
    if schedule.exec_mode == 'interval':
        choices = dict(ConfigFetchSchedule.INTERVAL_CHOICES)
        return choices.get(schedule.interval_seconds, f'每{schedule.interval_seconds}秒')
    else:
        days_map = {
            '*': '每天',
            '1-5': '工作日',
            '0,6': '周末',
        }
        days = days_map.get(schedule.exec_days, schedule.exec_days)
        time_str = schedule.exec_time.strftime('%H:%M') if schedule.exec_time else ''
        return f'{days} {time_str}'
