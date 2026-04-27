# 告警管理页面视图和API
from django.views.generic import ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.utils import timezone
from datetime import timedelta
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Alert
from devices.models import Device


# ==================== 页面视图 ====================

class AlertListView(LoginRequiredMixin, ListView):
    # 告警列表页面
    model = Alert
    template_name = 'alerts/alert_list.html'
    context_object_name = 'alerts'
    login_url = 'homepage:login'
    paginate_by = 20

    def get_queryset(self):
        # 返回按创建时间倒序的告警
        return Alert.objects.all().order_by('-created_at')

    def get_context_data(self, **kwargs):
        # 添加用户信息到上下文
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        return context


class AlertDetailView(LoginRequiredMixin, DetailView):
    # 告警详情页面
    model = Alert
    template_name = 'alerts/alert_detail.html'
    context_object_name = 'alert'
    login_url = 'homepage:login'

    def get_context_data(self, **kwargs):
        # 添加用户信息到上下文
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        return context


# ==================== API视图 ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def alert_list_api(request):
    # 告警列表API：支持状态、严重程度、类型筛选
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 20))
    status = request.GET.get('status')
    severity = request.GET.get('severity')
    alert_type = request.GET.get('alert_type')

    queryset = Alert.objects.select_related('device', 'handled_by').all().order_by('-created_at')

    # 筛选
    if status:
        queryset = queryset.filter(status=status)
    if severity:
        queryset = queryset.filter(severity=severity)
    if alert_type:
        queryset = queryset.filter(alert_type=alert_type)

    # 分页
    paginator = Paginator(queryset, page_size)

    try:
        alerts_page = paginator.page(page)
    except PageNotAnInteger:
        alerts_page = paginator.page(1)
    except EmptyPage:
        alerts_page = paginator.page(paginator.num_pages)

    alerts_data = []
    for alert in alerts_page:
        alerts_data.append({
            'id': alert.id,
            'device': {
                'id': alert.device.id,
                'name': alert.device.name,
                'ip_address': alert.device.ip_address,
            },
            'alert_type': alert.alert_type,
            'alert_type_display': alert.get_alert_type_display(),
            'severity': alert.severity,
            'severity_display': alert.get_severity_display(),
            'message': alert.message,
            'status': alert.status,
            'status_display': alert.get_status_display(),
            'created_at': alert.created_at.isoformat(),
            'handled_by': alert.handled_by.username if alert.handled_by else None,
            'handled_at': alert.handled_at.isoformat() if alert.handled_at else None,
        })

    return Response({
        'count': paginator.count,
        'total_pages': paginator.num_pages,
        'current_page': page,
        'results': alerts_data,
    })


@api_view(['GET', 'DELETE'])
@permission_classes([IsAuthenticated])
def alert_detail_api(request, pk):
    # 告警详情API：GET获取详情，DELETE删除
    try:
        alert = Alert.objects.get(pk=pk)
    except Alert.DoesNotExist:
        return Response({'error': 'Alert not found'}, status=404)

    if request.method == 'GET':
        return Response({
            'id': alert.id,
            'device': {
                'id': alert.device.id,
                'name': alert.device.name,
                'ip_address': alert.device.ip_address,
            },
            'alert_type': alert.alert_type,
            'alert_type_display': alert.get_alert_type_display(),
            'severity': alert.severity,
            'severity_display': alert.get_severity_display(),
            'message': alert.message,
            'status': alert.status,
            'status_display': alert.get_status_display(),
            'created_at': alert.created_at.isoformat(),
            'handled_by': alert.handled_by.username if alert.handled_by else None,
            'handled_at': alert.handled_at.isoformat() if alert.handled_at else None,
        })

    alert.delete()
    return Response(status=204)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def alert_acknowledge_api(request, pk):
    # 确认告警API
    try:
        alert = Alert.objects.get(pk=pk)
    except Alert.DoesNotExist:
        return Response({'error': 'Alert not found'}, status=404)

    from .services import AlertService
    service = AlertService()

    success = service.acknowledge_alert(alert, request.user)

    if success:
        return Response({
            'id': alert.id,
            'status': alert.status,
            'handled_by': alert.handled_by.username,
        })
    else:
        return Response(
            {'error': 'Alert cannot be acknowledged'},
            status=400
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def alert_ignore_api(request, pk):
    # 忽略告警API
    try:
        alert = Alert.objects.get(pk=pk)
    except Alert.DoesNotExist:
        return Response({'error': 'Alert not found'}, status=404)

    from .services import AlertService
    service = AlertService()

    success = service.ignore_alert(alert, request.user)

    if success:
        return Response({
            'id': alert.id,
            'status': alert.status,
            'handled_by': alert.handled_by.username,
        })
    else:
        return Response(
            {'error': 'Alert cannot be ignored'},
            status=400
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def alert_acknowledge_all_api(request):
    # 一键确认全部活动告警
    from .services import AlertService

    service = AlertService()
    handled_count = service.acknowledge_all_active_alerts(request.user)

    return Response({
        'success': True,
        'handled_count': handled_count,
        'message': f'已确认 {handled_count} 条待处理告警' if handled_count else '当前没有待处理告警',
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def alert_bulk_delete_api(request):
    # 批量删除告警
    alert_ids = request.data.get('alert_ids', [])
    if not isinstance(alert_ids, list):
        return Response({'error': 'alert_ids must be a list'}, status=400)

    normalized_ids = []
    for alert_id in alert_ids:
        try:
            normalized_ids.append(int(alert_id))
        except (TypeError, ValueError):
            continue

    if not normalized_ids:
        return Response({'error': '请选择要删除的告警'}, status=400)

    from .services import AlertService

    service = AlertService()
    deleted_count = service.delete_alerts(normalized_ids)

    return Response({
        'success': True,
        'deleted_count': deleted_count,
        'message': f'已删除 {deleted_count} 条告警',
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def alert_delete_all_api(request):
    # 删除全部告警
    from .services import AlertService

    service = AlertService()
    deleted_count = service.delete_all_alerts()

    return Response({
        'success': True,
        'deleted_count': deleted_count,
        'message': f'已删除全部告警，共 {deleted_count} 条',
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def alert_statistics_api(request):
    # 告警统计API
    days = int(request.GET.get('days', 7))

    from .services import AlertService
    service = AlertService()

    statistics = service.get_alert_statistics(days)

    return Response(statistics)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def alert_device_api(request, device_id):
    # 获取指定设备的告警列表
    try:
        device = Device.objects.get(pk=device_id)
    except Device.DoesNotExist:
        return Response({'error': 'Device not found'}, status=404)

    alerts = Alert.objects.filter(device=device).order_by('-created_at')

    alerts_data = []
    for alert in alerts:
        alerts_data.append({
            'id': alert.id,
            'alert_type': alert.alert_type,
            'alert_type_display': alert.get_alert_type_display(),
            'severity': alert.severity,
            'severity_display': alert.get_severity_display(),
            'message': alert.message,
            'status': alert.status,
            'created_at': alert.created_at.isoformat(),
        })

    return Response({
        'device': {
            'id': device.id,
            'name': device.name,
        },
        'alerts': alerts_data,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def alert_counts_api(request):
    # 告警计数API：返回活动/已处理/已忽略/总计数量
    active = Alert.objects.filter(status='active').count()
    acknowledged = Alert.objects.filter(status='acknowledged').count()
    ignored = Alert.objects.filter(status='ignored').count()
    total = Alert.objects.count()
    return Response({
        'active_count': active,
        'acknowledged_count': acknowledged,
        'ignored_count': ignored,
        'total_count': total,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def alert_active_api(request):
    # 获取活动告警列表（限制50条）
    from .services import AlertService
    service = AlertService()

    alerts = service.get_active_alerts()[:50]  # 限制返回数量

    alerts_data = []
    for alert in alerts:
        alerts_data.append({
            'id': alert.id,
            'device': {
                'id': alert.device.id,
                'name': alert.device.name,
                'ip_address': alert.device.ip_address,
            },
            'severity': alert.severity,
            'severity_display': alert.get_severity_display(),
            'message': alert.message,
            'created_at': alert.created_at.isoformat(),
        })

    return Response({
        'count': len(alerts_data),
        'alerts': alerts_data,
    })
