"""
系统日志页面视图

包含 LogListView（日志列表页面）和API视图。
"""

from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from .models import SystemLog


class LogListView(LoginRequiredMixin, ListView):
    """Display list of all system logs."""

    model = SystemLog
    template_name = 'logs/log_list.html'
    context_object_name = 'logs'
    login_url = 'homepage:login'
    paginate_by = 50

    def get_queryset(self):
        """Return all logs ordered by timestamp."""
        return SystemLog.objects.all().order_by('-timestamp')

    def get_context_data(self, **kwargs):
        """Add user info and log statistics to context."""
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
    """
    日志查询API端点

    支持关键字搜索、时间范围筛选、日志类型筛选

    """
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
    )

    return Response(result)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def log_detail_api(request, pk):
    """
    日志详情API端点

    """
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
    """
    日志统计API端点

    按日志类型、时间段统计日志数量

    """
    from .services import LogService

    service = LogService()

    days = int(request.GET.get('days', 7))
    log_type = request.GET.get('log_type')

    statistics = service.get_statistics(days=days, log_type=log_type)

    return Response(statistics)
