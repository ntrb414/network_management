"""
管理后台视图

提供自定义的管理后台界面，与项目其他模块 UI 风格保持一致。
"""

from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import User, Group, Permission
from django.apps import apps
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.shortcuts import redirect
from django.contrib import messages
import platform
import django


@method_decorator(staff_member_required, name='dispatch')
class ScheduledTasksView(TemplateView):
    """
    Celery 定时任务视图

    显示所有已配置的定时任务（Periodic Tasks），
    包括任务名称、调度计划、上次执行时间、下次执行时间等。
    """
    template_name = 'admin_panel/scheduled_tasks.html'
    login_url = 'homepage:login'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        from django_celery_beat.models import PeriodicTask, IntervalSchedule, CrontabSchedule
        from celery import app as celery_app

        # 获取过滤参数
        filter_type = self.request.GET.get('filter', '')

        # 获取所有定时任务
        periodic_tasks = PeriodicTask.objects.select_related(
            'interval', 'crontab'
        ).all().order_by('name')

        tasks_data = []
        for task in periodic_tasks:
            # 获取任务描述
            task_info = self._get_task_info(task.task)

            # 获取调度信息
            schedule_info = self._get_schedule_info(task)

            # 获取最近执行的任务结果
            last_run = self._get_last_run_info(task)

            tasks_data.append({
                'id': task.id,
                'name': task.name,
                'task': task.task,
                'task_name': task_info['name'],
                'task_description': task_info['description'],
                'task_queue_label': task_info['queue_label'],
                'enabled': task.enabled,
                'schedule_type': schedule_info['type'],
                'schedule_desc': schedule_info['desc'],
                'schedule_human': schedule_info.get('human', schedule_info['desc']),
                'interval': task.interval,
                'crontab': task.crontab,
                'last_run_time': last_run.get('time'),
                'last_run_result': last_run.get('result'),
                'last_run_status': last_run.get('status'),
                'last_run_detail': last_run.get('detail'),
                'total_run_count': task.total_run_count,
                'date_changed': task.date_changed,
                'kwargs': task.kwargs,
            })

        # 按启用状态分组
        enabled_tasks = [t for t in tasks_data if t['enabled']]
        disabled_tasks = [t for t in tasks_data if not t['enabled']]

        # 根据过滤条件筛选任务
        if filter_type == 'enabled':
            filtered_tasks = enabled_tasks
        elif filter_type == 'disabled':
            filtered_tasks = disabled_tasks
        else:
            filtered_tasks = tasks_data

        # 获取 Celery Worker 状态
        try:
            from celery.app.control import Inspect
            inspector = Inspect(app=celery_app)
            stats = inspector.stats() or {}
            active_tasks = inspector.active() or {}
            worker_count = len(stats)
            active_task_count = sum(len(tasks) for tasks in active_tasks.values())
        except Exception:
            stats = {}
            active_tasks = {}
            worker_count = 0
            active_task_count = 0

        context.update({
            'periodic_tasks': filtered_tasks,
            'enabled_count': len(enabled_tasks),
            'disabled_count': len(disabled_tasks),
            'total_count': len(tasks_data),
            'worker_count': worker_count,
            'active_task_count': active_task_count,
            'user': self.request.user,
            'filter': filter_type,
        })

        return context

    def _get_task_info(self, func_name):
        """获取任务名称和描述"""
        from .templatetags.admin_panel_tags import get_task_metadata

        return get_task_metadata(func_name)

    def _get_schedule_info(self, task):
        """获取调度信息"""
        interval_seconds = self._estimate_interval_seconds(task)
        if interval_seconds is not None:
            return {
                'type': 'interval',
                'desc': f"每{interval_seconds}秒",
                'human': self._to_human_interval(interval_seconds),
            }

        if task.crontab:
            return {
                'type': 'crontab',
                'desc': 'Cron',
                'human': self._to_human_crontab(task.crontab),
            }
        elif task.solar:
            return {'type': 'solar', 'desc': 'Solar Schedule', 'human': '太阳事件触发'}
        elif task.clocked:
            return {
                'type': 'clocked',
                'desc': f"Clocked: {task.clocked.clocked_time}",
                'human': f"单次执行：{task.clocked.clocked_time}",
            }
        else:
            return {'type': 'unknown', 'desc': '无调度', 'human': '无调度'}

    def _to_human_interval(self, seconds):
        if seconds < 60:
            return f"每 {seconds} 秒"
        if seconds % 86400 == 0:
            days = seconds // 86400
            return f"每 {days} 天"
        if seconds % 3600 == 0:
            hours = seconds // 3600
            return f"每 {hours} 小时"
        if seconds % 60 == 0:
            minutes = seconds // 60
            return f"每 {minutes} 分钟"
        return f"每 {seconds} 秒"

    def _to_human_crontab(self, crontab):
        minute = str(crontab.minute)
        hour = str(crontab.hour)
        dom = str(crontab.day_of_month)
        moy = str(crontab.month_of_year)
        dow = str(crontab.day_of_week)

        if minute.isdigit() and hour.isdigit() and dom == '*' and moy == '*' and dow == '*':
            return f"每天 {int(hour):02d}:{int(minute):02d}"
        if minute.isdigit() and hour == '*' and dom == '*' and moy == '*' and dow == '*':
            return f"每小时第 {int(minute)} 分"
        if minute == '0' and hour == '*' and dom == '*' and moy == '*' and dow == '*':
            return '每小时整点'
        if minute == '0' and hour == '0' and dom == '*' and moy == '*' and dow == '*':
            return '每天 00:00'
        if minute.isdigit() and hour.isdigit() and dom == '*' and moy == '*' and dow != '*':
            return f"每周 {dow} {int(hour):02d}:{int(minute):02d}"
        return f"Cron: {minute} {hour} {dom} {moy} {dow}"

    def _estimate_interval_seconds(self, task):
        """估算任务触发间隔（秒）"""
        if task.interval:
            period_map = {
                'seconds': 1,
                'minutes': 60,
                'hours': 3600,
                'days': 86400,
                'microseconds': 0,
            }
            base = period_map.get(task.interval.period)
            if base is None:
                return None
            if base == 0:
                return max(1, task.interval.every // 1000000)
            return max(1, task.interval.every * base)

        if task.crontab:
            # 使用 celery crontab schedule 估算连续两次触发间隔。
            from django.utils import timezone

            try:
                schedule = task.crontab.schedule
                t1 = timezone.now()
                d1 = schedule.remaining_estimate(t1)
                if d1.total_seconds() <= 0:
                    return None

                t2 = t1 + d1
                d2 = schedule.remaining_estimate(t2)
                if d2.total_seconds() <= 0:
                    return int(d1.total_seconds())

                return int(max(1, d2.total_seconds()))
            except Exception:
                return None

        return None

    def _get_last_run_info(self, task):
        """获取最近一次执行信息"""
        try:
            result_detail = '暂无执行结果数据'
            result_status = 'unknown'
            if task.last_run_at:
                result_status = 'success'
                result_detail = f"最近一次触发时间：{task.last_run_at}"

            return {
                'time': task.last_run_at or task.date_changed,
                'result': result_detail,
                'status': result_status,
                'detail': result_detail,
            }
        except Exception:
            return {
                'time': None,
                'result': '无法读取执行结果',
                'status': 'unknown',
                'detail': '无法读取执行结果',
            }

@staff_member_required
def toggle_periodic_task(request, task_id):
    """
    启用或禁用定时任务
    """
    if request.method == 'POST':
        from django_celery_beat.models import PeriodicTask

        try:
            task = PeriodicTask.objects.get(pk=task_id)
            task.enabled = not task.enabled
            task.save()
            status = '已启用' if task.enabled else '已禁用'
            messages.success(request, f'任务 "{task.name}" {status}')
        except PeriodicTask.DoesNotExist:
            messages.error(request, '定时任务不存在')

    return redirect('admin_panel:scheduled_tasks')


@staff_member_required
def update_task_interval(request, task_id):
    """
    更新定时任务的执行间隔

    仅支持 IntervalSchedule 类型任务。
    请求体 JSON: {"every": int, "period": str}
    """
    import json
    from django.http import JsonResponse
    from django_celery_beat.models import PeriodicTask, IntervalSchedule

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': '仅支持 POST 请求'}, status=405)

    try:
        data = json.loads(request.body)
        every = data.get('every')
        period = data.get('period')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': '无效的 JSON 数据'}, status=400)

    # 验证输入
    valid_periods = ['seconds', 'minutes', 'hours', 'days']
    if not every or not isinstance(every, int) or every < 1:
        return JsonResponse({'success': False, 'error': '间隔数值必须是大于 0 的整数'}, status=400)
    if period not in valid_periods:
        return JsonResponse({'success': False, 'error': '时间单位必须是 seconds/minutes/hours/days 之一'}, status=400)

    # 最小间隔验证（至少 10 秒）
    period_map = {'seconds': 1, 'minutes': 60, 'hours': 3600, 'days': 86400}
    total_seconds = every * period_map[period]
    if total_seconds < 10:
        return JsonResponse({'success': False, 'error': '间隔时间不能小于 10 秒'}, status=400)

    try:
        task = PeriodicTask.objects.get(pk=task_id)
    except PeriodicTask.DoesNotExist:
        return JsonResponse({'success': False, 'error': '任务不存在'}, status=404)

    if not task.interval:
        return JsonResponse({'success': False, 'error': '该任务使用非间隔调度，无法通过此接口修改'}, status=400)

    # 获取或创建 IntervalSchedule
    interval, _ = IntervalSchedule.objects.get_or_create(every=every, period=period)
    task.interval = interval
    task.save()

    period_names = {'seconds': '秒', 'minutes': '分钟', 'hours': '小时', 'days': '天'}
    return JsonResponse({
        'success': True,
        'message': f'执行间隔已更新为每 {every} {period_names[period]}'
    })


@staff_member_required
def get_task_detail(request, task_id):
    """
    获取定时任务详情

    返回 JSON 格式的任务详细信息。
    """
    from django.http import JsonResponse
    from django_celery_beat.models import PeriodicTask

    if request.method != 'GET':
        return JsonResponse({'error': '仅支持 GET 请求'}, status=405)

    try:
        task = PeriodicTask.objects.get(pk=task_id)
    except PeriodicTask.DoesNotExist:
        return JsonResponse({'error': '任务不存在'}, status=404)

    # 获取任务元数据
    from .templatetags.admin_panel_tags import get_task_metadata
    task_info = get_task_metadata(task.task)

    # 构建调度详情
    schedule_detail = None
    if task.interval:
        period_names = {'seconds': '秒', 'minutes': '分钟', 'hours': '小时', 'days': '天'}
        schedule_detail = {
            'every': task.interval.every,
            'period': task.interval.period,
            'human_readable': f"每 {task.interval.every} {period_names.get(task.interval.period, task.interval.period)}"
        }
    elif task.crontab:
        schedule_detail = {
            'minute': str(task.crontab.minute),
            'hour': str(task.crontab.hour),
            'day_of_month': str(task.crontab.day_of_month),
            'month_of_year': str(task.crontab.month_of_year),
            'day_of_week': str(task.crontab.day_of_week),
            'human_readable': f"Cron: {task.crontab.minute} {task.crontab.hour} {task.crontab.day_of_month} {task.crontab.month_of_year} {task.crontab.day_of_week}"
        }

    # 确定调度类型
    schedule_type = 'unknown'
    if task.interval:
        schedule_type = 'interval'
    elif task.crontab:
        schedule_type = 'crontab'
    elif task.solar:
        schedule_type = 'solar'
    elif task.clocked:
        schedule_type = 'clocked'

    data = {
        'id': task.id,
        'name': task_info.get('name', task.name),
        'task': task.task,
        'description': task_info.get('description', ''),
        'category': task_info.get('category', '其他'),
        'enabled': task.enabled,
        'schedule_type': schedule_type,
        'schedule_detail': schedule_detail,
        'last_run_at': task.last_run_at.strftime('%Y-%m-%d %H:%M:%S') if task.last_run_at else None,
        'total_run_count': task.total_run_count,
        'date_changed': task.date_changed.strftime('%Y-%m-%d %H:%M:%S') if task.date_changed else None,
        'kwargs': task.kwargs,
    }

    return JsonResponse(data)


class AdminDashboardView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """管理后台仪表盘"""
    template_name = 'admin_panel/dashboard.html'
    login_url = 'homepage:login'

    def test_func(self):
        """仅允许超级用户访问"""
        return self.request.user.is_superuser

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user

        # 获取各模型统计
        context['stats'] = self._get_model_stats()

        # 获取系统信息
        context['system_info'] = self._get_system_info()

        # 获取 Celery 状态
        context['celery_info'] = self._get_celery_info()

        # 最近注册的用户
        context['recent_users'] = User.objects.order_by('-date_joined')[:5]

        return context

    def _get_model_stats(self):
        """获取各模型统计信息"""
        stats = {
            'total_users': User.objects.count(),
            'active_users': User.objects.filter(is_active=True).count(),
            'total_groups': Group.objects.count(),
            'total_permissions': Permission.objects.count(),
        }

        # 统计各app的模型数量
        app_stats = {}
        for app in ['devices', 'configs', 'monitoring', 'alerts', 'backups', 'logs', 'ipmanagement']:
            try:
                app_config = apps.get_app_config(app)
                model_count = sum(1 for _ in app_config.get_models()) if hasattr(app_config, 'get_models') else 0
                app_stats[app] = model_count
            except LookupError:
                app_stats[app] = 0

        stats['app_stats'] = app_stats
        return stats

    def _get_system_info(self):
        """获取系统信息"""
        info = {
            'django_version': f"{django.VERSION[0]}.{django.VERSION[1]}.{django.VERSION[2]}",
            'python_version': platform.python_version(),
            'platform': platform.platform(),
        }
        return info

    def _get_celery_info(self):
        """获取 Celery 状态信息"""
        from network_management.celery import app
        from celery.app.control import Inspect
        from django_celery_beat.models import PeriodicTask, IntervalSchedule, CrontabSchedule

        inspector = Inspect(app=app)
        try:
            stats = inspector.stats() or {}
        except Exception:
            stats = {}

        return {
            'worker_count': len(stats),
            'periodic_task_count': PeriodicTask.objects.filter(enabled=True).count(),
            'interval_count': IntervalSchedule.objects.count(),
            'crontab_count': CrontabSchedule.objects.count(),
        }
