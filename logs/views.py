# 系统日志页面视图和API
from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from .models import SystemLog


def _to_bool(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}



class RuntimeLogListView(LoginRequiredMixin, ListView):
    # 运行日志列表页面（已废弃，重定向到日志中心）
    model = SystemLog
    template_name = 'logs/runtime_log_list.html'
    context_object_name = 'logs'
    login_url = 'homepage:login'

    def get_queryset(self):
        return SystemLog.objects.filter(log_type='system', details__source='syslog').order_by('-timestamp')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        from devices.models import Device
        context['devices'] = Device.objects.all().order_by('name')
        return context


class LogListView(LoginRequiredMixin, ListView):
    # 系统日志列表页面
    model = SystemLog
    template_name = 'logs/log_list.html'
    context_object_name = 'logs'
    login_url = 'homepage:login'
    paginate_by = 50

    def get_queryset(self):
        # 返回按时间倒序的所有日志
        return SystemLog.objects.all().order_by('-timestamp')

    def get_context_data(self, **kwargs):
        # 添加用户信息和日志类型到上下文
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        context['log_types'] = SystemLog.LOG_TYPES
        # 获取所有设备列表供筛选
        from devices.models import Device
        context['devices'] = Device.objects.all().order_by('name')
        return context


# ==================== API视图 ====================


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def log_list_api(request):
    # 日志查询API：支持关键字搜索、时间范围、类型、来源筛选
    from .services import LogService

    service = LogService()

    # 获取查询参数
    keyword = request.GET.get('keyword')
    log_type = request.GET.get('log_type')
    device_id = request.GET.get('device_id')
    user_id = request.GET.get('user_id')
    start_time = request.GET.get('start_time')
    end_time = request.GET.get('end_time')
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 50))
    source = request.GET.get('source')
    severity = request.GET.get('severity')
    source_ip = request.GET.get('source_ip')

    # 转换时间参数
    from django.utils.dateparse import parse_datetime
    if start_time:
        start_time = parse_datetime(start_time)
    if end_time:
        end_time = parse_datetime(end_time)

    result = service.query_logs(
        keyword=keyword,
        log_type=log_type,
        device_id=device_id,
        user_id=user_id,
        start_time=start_time,
        end_time=end_time,
        page=page,
        page_size=page_size,
        source=source,
        severity=severity,
        source_ip=source_ip,
    )

    return Response(result)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def log_detail_api(request, pk):
    # 日志详情API端点
    try:
        log = SystemLog.objects.get(pk=pk)
    except SystemLog.DoesNotExist:
        return Response({'error': 'Log not found'}, status=404)

    # 获取设备名称
    device_name = None
    if log.device:
        device_name = log.device.name

    # 获取用户名称
    user_name = None
    if log.user:
        user_name = log.user.username

    return Response({
        'id': log.id,
        'log_type': log.log_type,
        'message': log.message,
        'details': log.details,
        'timestamp': log.timestamp,
        'device_id': log.device_id,
        'device_name': device_name,
        'user_id': log.user_id,
        'user_name': user_name,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def log_statistics_api(request):
    # 日志统计API端点
    # 按日志类型、时间段统计日志数量
    from .services import LogService
    from django.utils.dateparse import parse_datetime

    service = LogService()

    days = int(request.GET.get('days', 7))
    log_type = request.GET.get('log_type')
    source = request.GET.get('source')
    device_id = request.GET.get('device_id')
    keyword = request.GET.get('keyword')
    severity = request.GET.get('severity')
    source_ip = request.GET.get('source_ip')

    start_time = request.GET.get('start_time')
    end_time = request.GET.get('end_time')
    if start_time:
        start_time = parse_datetime(start_time)
    if end_time:
        end_time = parse_datetime(end_time)

    if device_id:
        device_id = int(device_id)

    statistics = service.get_statistics(
        days=days,
        log_type=log_type,
        source=source,
        device_id=device_id,
        start_time=start_time,
        end_time=end_time,
        severity=severity,
        source_ip=source_ip,
        keyword=keyword,
    )

    return Response(statistics)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def log_cleanup_api(request):
    # 手动清理旧日志API端点
    # 参数: days-保留天数(默认7)
    # 返回: 清理结果
    from .services import LogService

    service = LogService()
    days = int(request.data.get('days', 7))
    result = service.cleanup_old_logs(days=days)
    return Response(result)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def runtime_log_list_api(request):
    # 设备运行日志(Syslog)查询接口，兼容入口内部转发到统一查询
    from .services import LogService

    service = LogService()

    keyword = request.GET.get('keyword')
    device_id = request.GET.get('device_id')
    source_ip = request.GET.get('source_ip')
    severity = request.GET.get('severity')
    start_time = request.GET.get('start_time')
    end_time = request.GET.get('end_time')
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 50))

    from django.utils.dateparse import parse_datetime
    if start_time:
        start_time = parse_datetime(start_time)
    if end_time:
        end_time = parse_datetime(end_time)

    result = service.query_logs(
        source='syslog',
        keyword=keyword,
        device_id=device_id,
        source_ip=source_ip,
        severity=severity,
        start_time=start_time,
        end_time=end_time,
        page=page,
        page_size=page_size,
    )
    return Response(result)


@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def device_syslog_config_api(request, device_id):
    # 设备Syslog参数读取/保存接口，支持可选一键下发
    from devices.models import Device
    from .services import LogService

    try:
        device = Device.objects.get(pk=device_id)
    except Device.DoesNotExist:
        return Response({'error': '设备不存在'}, status=404)

    if request.method == 'GET':
        return Response(
            {
                'device_id': device.id,
                'device_name': device.name,
                'syslog_enabled': device.syslog_enabled,
                'syslog_server_ip': device.syslog_server_ip,
                'syslog_server_port': device.syslog_server_port,
                'syslog_protocol': device.syslog_protocol,
                'syslog_severity_threshold': device.syslog_severity_threshold,
            }
        )

    enabled = _to_bool(request.data.get('enabled'))
    server_ip = request.data.get('server_ip')
    server_port = request.data.get('server_port')
    protocol = request.data.get('protocol')
    severity_threshold = request.data.get('severity_threshold')
    push_to_device = _to_bool(request.data.get('push_to_device')) or False

    if server_port in (None, ''):
        server_port = None

    result = LogService().save_device_syslog_settings(
        device=device,
        enabled=enabled,
        server_ip=server_ip,
        server_port=server_port,
        protocol=protocol,
        severity_threshold=severity_threshold,
        push_to_device=push_to_device,
    )
    return Response(result)
