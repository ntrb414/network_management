"""
性能监控页面视图和API

包含监控数据列表、实时监控、历史监控等视图。
需求引用：4.4, 4.5
"""

from django.views.generic import ListView, TemplateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.utils import timezone
from datetime import timedelta
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import MetricData
from devices.models import Device
from django.db import models


EXCLUDED_METRIC_TYPES = {
    'packet_loss',
    'connections',
    'interface_in_traffic',
    'interface_out_traffic',
}
DISPLAY_METRIC_TYPES = [
    (mt, label) for mt, label in MetricData.METRIC_TYPES if mt not in EXCLUDED_METRIC_TYPES
]
OSPF_STATE_MAP = {
    1: 'Down',
    2: 'Attempt',
    3: 'Init',
    4: 'TwoWay',
    5: 'ExStart',
    6: 'Exchange',
    7: 'Loading',
    8: 'Full',
}


def _get_interface_name(metric_name):
    if not metric_name:
        return ''
    return metric_name[:-7] if metric_name.endswith('_status') else metric_name


def _get_ospf_neighbor_ip(metric_name):
    if not metric_name:
        return ''

    neighbor_value = metric_name.replace('ospf_nbr_', '', 1)
    if not neighbor_value:
        return ''

    if all(char.isdigit() or char == '.' for char in neighbor_value):
        return neighbor_value

    if len(neighbor_value) == 4:
        return '.'.join(str(ord(char)) for char in neighbor_value)

    return neighbor_value

def _get_metric_display_name(metric_type, metric_name):
    if not metric_name:
        return ''

    if metric_type == 'interface_status':
        return _get_interface_name(metric_name)

    if metric_type == 'ospf_neighbor':
        neighbor_ip = _get_ospf_neighbor_ip(metric_name)
        return f"OSPF邻居 {neighbor_ip}" if neighbor_ip else 'OSPF邻居'

    if metric_type == 'interface_in_traffic' and metric_name.endswith('_in_mbps'):
        return f"{metric_name[:-8]} 入向流量"

    if metric_type == 'interface_out_traffic' and metric_name.endswith('_out_mbps'):
        return f"{metric_name[:-9]} 出向流量"

    if metric_type == 'interface_in_drops' and metric_name.endswith('_in_drops'):
        return f"{metric_name[:-9]} 入向丢包"

    if metric_type == 'interface_out_drops' and metric_name.endswith('_out_drops'):
        return f"{metric_name[:-10]} 出向丢包"

    if metric_type == 'traffic':
        if metric_name.endswith('_in'):
            return f"{metric_name[:-3]} 入向流量"
        if metric_name.endswith('_out'):
            return f"{metric_name[:-4]} 出向流量"

    if metric_type == 'packet_loss' and metric_name == 'packet_loss_rate':
        return '丢包率'

    if metric_type == 'connections' and metric_name == 'active_connections':
        return '活动连接数'

    return metric_name


def _is_interface_up(value):
    try:
        return int(value) == 1
    except (TypeError, ValueError):
        return False


def _get_latest_interface_status_metrics(device):
    return MetricData.objects.filter(
        device=device,
        metric_type='interface_status'
    ).order_by('metric_name', '-timestamp').distinct('metric_name')


def _get_latest_ospf_neighbor_metrics(device):
    return MetricData.objects.filter(
        device=device,
        metric_type='ospf_neighbor'
    ).order_by('metric_name', '-timestamp').distinct('metric_name')


def _get_interface_status_display(value):
    try:
        status_value = int(value)
    except (TypeError, ValueError):
        return f'状态({value})'

    if status_value == 1:
        return '开启(UP)'
    if status_value == 2:
        return '关闭(DOWN)'
    return f'状态({status_value})'


def _get_metric_display_value(metric_type, value, unit):
    if value is None:
        return None

    if metric_type == 'interface_status':
        return _get_interface_status_display(value)
    if metric_type == 'ospf_neighbor':
        try:
            state_value = int(value)
            return OSPF_STATE_MAP.get(state_value, f'Unknown({state_value})')
        except (TypeError, ValueError):
            return f'Unknown({value})'
    return f'{value} {unit}'.strip()


# ==================== 页面视图 ====================

class MonitoringListView(LoginRequiredMixin, ListView):
    """Display list of all monitoring metrics."""

    model = MetricData
    template_name = 'monitoring/monitoring_list.html'
    context_object_name = 'metrics'
    login_url = 'homepage:login'
    paginate_by = 20

    def get_queryset(self):
        """Return all metrics ordered by timestamp, with optional type filter."""
        qs = MetricData.objects.exclude(metric_type__in=EXCLUDED_METRIC_TYPES).order_by('-timestamp')
        metric_type = self.request.GET.get('metric_type')
        if metric_type and metric_type not in EXCLUDED_METRIC_TYPES:
            qs = qs.filter(metric_type=metric_type)
        return qs

    def get_context_data(self, **kwargs):
        """Add user info and metric summary to context."""
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        context['metric_types'] = DISPLAY_METRIC_TYPES
        return context


class MonitoringDashboardView(LoginRequiredMixin, TemplateView):
    """Display monitoring dashboard with device list."""

    template_name = 'monitoring/monitoring_dashboard.html'
    login_url = 'homepage:login'

    def get_context_data(self, **kwargs):
        """Add user info and device list to context."""
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user

        # 统计当前监控指标数：同一设备下同一个 metric_type + metric_name 的最新值记为 1 个指标。
        context['total_metrics'] = MetricData.objects.order_by(
            'device_id', 'metric_type', 'metric_name', '-timestamp'
        ).distinct('device_id', 'metric_type', 'metric_name').count()
        context['metric_types'] = DISPLAY_METRIC_TYPES

        # 统计被监控的设备数量
        context['monitored_devices_count'] = Device.objects.count()

        # 获取所有设备
        devices = Device.objects.all().order_by('name')
        device_ids = [d.id for d in devices]

        # 基于每个接口最新状态进行统计，避免历史数据累计导致显示失真
        from django.db.models import Count, Case, When
        latest_interface_status = MetricData.objects.filter(
            device_id__in=device_ids,
            metric_type='interface_status'
        ).order_by('device_id', 'metric_name', '-timestamp').distinct('device_id', 'metric_name')

        interface_counts_by_device = {}
        latest_intf_ts_by_device = {}
        for metric in latest_interface_status:
            stats = interface_counts_by_device.setdefault(metric.device_id, {'up_count': 0, 'down_count': 0})
            if int(metric.value) == 1:
                stats['up_count'] += 1
            else:
                stats['down_count'] += 1

            latest_ts = latest_intf_ts_by_device.get(metric.device_id)
            if latest_ts is None or metric.timestamp > latest_ts:
                latest_intf_ts_by_device[metric.device_id] = metric.timestamp

        # 批量获取所有设备的 OSPF 邻居状态统计
        ospf_counts = MetricData.objects.filter(
            device_id__in=device_ids,
            metric_type='ospf_neighbor'
        ).values('device_id').annotate(
            full_count=Count(Case(When(value=8, then=1))),
            total_count=Count('id')
        )
        ospf_counts_by_device = {item['device_id']: item for item in ospf_counts}

        # 批量获取所有设备的最新 OSPF timestamp
        latest_ospf_timestamps = MetricData.objects.filter(
            device_id__in=device_ids,
            metric_type='ospf_neighbor'
        ).order_by('device_id', '-timestamp').distinct('device_id').values('device_id', 'timestamp')
        latest_ospf_ts_by_device = {item['device_id']: item['timestamp'] for item in latest_ospf_timestamps}

        # 构建设备列表
        device_list = []
        for device in devices:
            item = {
                'device': device,
                'summary': {
                    'interface_status': None,
                    'ospf': None,
                },
                'last_metric_time': None,
            }

            # 接口状态统计
            intf_counts = interface_counts_by_device.get(device.id)
            if intf_counts:
                up_count = intf_counts['up_count']
                down_count = intf_counts['down_count']
                item['summary']['interface_status'] = f"{up_count} UP / {down_count} DOWN"
                item['last_metric_time'] = latest_intf_ts_by_device.get(device.id)

            # OSPF邻居状态
            ospf_stats = ospf_counts_by_device.get(device.id)
            if ospf_stats:
                full_count = ospf_stats['full_count']
                total_count = ospf_stats['total_count']
                item['summary']['ospf'] = f"{full_count}/{total_count} Full"
                if not item['last_metric_time']:
                    item['last_metric_time'] = latest_ospf_ts_by_device.get(device.id)

            device_list.append(item)

        context['device_list'] = device_list

        return context


class MonitoringDeviceDetailView(LoginRequiredMixin, TemplateView):
    """Display detailed monitoring data for a single device."""

    template_name = 'monitoring/monitoring_device_detail.html'
    login_url = 'homepage:login'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        device = get_object_or_404(Device, pk=self.kwargs['device_id'])
        context['user'] = self.request.user
        context['device'] = device

        # 各指标最新值
        metrics_latest = {}
        for mt, label in DISPLAY_METRIC_TYPES:
            if mt == 'interface_status':
                latest_status_metrics = list(_get_latest_interface_status_metrics(device))
                up_interfaces = [
                    _get_interface_name(metric.metric_name)
                    for metric in latest_status_metrics
                    if _is_interface_up(metric.value)
                ]
                metrics_latest[mt] = {
                    'label': label,
                    'value': len(up_interfaces) if latest_status_metrics else None,
                    'unit': 'ports',
                    'timestamp': latest_status_metrics[0].timestamp if latest_status_metrics else None,
                    'display_value': '、'.join(up_interfaces) if up_interfaces else ('暂无UP端口' if latest_status_metrics else None),
                }
                continue

            if mt == 'ospf_neighbor':
                latest_ospf_metrics = list(_get_latest_ospf_neighbor_metrics(device))
                neighbor_ips = []
                for metric in latest_ospf_metrics:
                    neighbor_ip = _get_ospf_neighbor_ip(metric.metric_name)
                    if neighbor_ip and neighbor_ip not in neighbor_ips:
                        neighbor_ips.append(neighbor_ip)
                latest_timestamp = max((metric.timestamp for metric in latest_ospf_metrics), default=None)
                metrics_latest[mt] = {
                    'label': label,
                    'value': len(neighbor_ips) if neighbor_ips else (len(latest_ospf_metrics) if latest_ospf_metrics else None),
                    'unit': 'neighbors',
                    'timestamp': latest_timestamp,
                    'display_value': '、'.join(neighbor_ips) if neighbor_ips else ('暂无邻居IP' if latest_ospf_metrics else None),
                }
                continue

            latest = MetricData.objects.filter(
                device=device, metric_type=mt
            ).order_by('-timestamp').first()
            metrics_latest[mt] = {
                'label': label,
                'value': latest.value if latest else None,
                'unit': latest.unit if latest else '',
                'timestamp': latest.timestamp if latest else None,
                'display_value': _get_metric_display_value(mt, latest.value, latest.unit) if latest else None,
            }
        context['metrics_latest'] = metrics_latest

        # 各指标历史记录（最近50条）
        metrics_history = {}
        for mt, label in DISPLAY_METRIC_TYPES:
            history = list(
                MetricData.objects.filter(device=device, metric_type=mt)
                .order_by('-timestamp')[:50]
                .values('value', 'unit', 'metric_name', 'timestamp')
            )
            history = [
                {
                    **row,
                    'display_metric_name': _get_metric_display_name(mt, row['metric_name']),
                }
                for row in history
                if mt != 'interface_status' or _is_interface_up(row['value'])
            ]
            metrics_history[mt] = history
        context['metrics_history'] = metrics_history

        # JSON序列化供JS使用
        import json
        from django.utils.timezone import localtime
        history_json = {}
        for mt, rows in metrics_history.items():
            history_json[mt] = [
                {
                    'metric_type': mt,
                    'metric_name': r['metric_name'],
                    'value': r['value'],
                    'unit': r['unit'],
                    'timestamp': localtime(r['timestamp']).isoformat(),
                }
                for r in rows
            ]
        context['metrics_history_json'] = json.dumps(history_json, ensure_ascii=False)

        # 该设备的告警
        try:
            from alerts.models import Alert
            context['device_alerts'] = Alert.objects.filter(
                device=device
            ).order_by('-timestamp')[:10]
        except Exception:
            context['device_alerts'] = []

        context['metric_types'] = DISPLAY_METRIC_TYPES
        return context


# ==================== API视图 ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def monitoring_device_realtime_api(request, device_id):
    """
    实时监控数据API端点

    Requirements: 4.4
    """
    try:
        device = Device.objects.get(pk=device_id)
    except Device.DoesNotExist:
        return Response({'error': 'Device not found'}, status=404)

    latest_metrics = {}

    # 获取流量数据
    traffic_metrics = MetricData.objects.filter(
        device=device,
        metric_type='traffic'
    ).order_by('-timestamp')[:10]

    latest_metrics['traffic'] = [
        {
            'name': m.metric_name,
            'value': m.value,
            'unit': m.unit,
            'timestamp': m.timestamp.isoformat(),
        }
        for m in traffic_metrics
    ]
    
    # 获取接口状态
    interface_status_list = MetricData.objects.filter(
        device=device, metric_type='interface_status'
    ).order_by('-timestamp')[:20]
    
    latest_metrics['interfaces'] = []
    seen_interfaces = set()
    for m in interface_status_list:
        iface_name = _get_interface_name(m.metric_name)
        if iface_name not in seen_interfaces:
            seen_interfaces.add(iface_name)
            if not _is_interface_up(m.value):
                continue
            latest_metrics['interfaces'].append({
                'name': iface_name,
                'status': int(m.value),
                'status_display': _get_interface_status_display(m.value),
                'timestamp': m.timestamp.isoformat(),
            })
    
    # 获取OSPF邻居状态
    ospf_list = MetricData.objects.filter(
        device=device, metric_type='ospf_neighbor'
    ).order_by('-timestamp')[:10]
    
    latest_metrics['ospf_neighbors'] = []
    seen_ospf = set()
    for m in ospf_list:
        neighbor_ip = m.metric_name.replace('ospf_nbr_', '')
        neighbor_ip = _get_ospf_neighbor_ip(m.metric_name)
        if neighbor_ip not in seen_ospf:
            seen_ospf.add(neighbor_ip)
            state_value = int(m.value)
            latest_metrics['ospf_neighbors'].append({
                'neighbor_ip': neighbor_ip,
                'state': state_value,
                'state_name': OSPF_STATE_MAP.get(state_value, f'Unknown({state_value})'),
                'is_full': state_value == 8,
                'timestamp': m.timestamp.isoformat(),
            })

    return Response({
        'device': {
            'id': device.id,
            'name': device.name,
            'ip_address': device.ip_address,
        },
        'metrics': latest_metrics,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def monitoring_device_metrics_api(request, device_id):
    """
    历史监控数据API端点

    Requirements: 4.5
    """
    try:
        device = Device.objects.get(pk=device_id)
    except Device.DoesNotExist:
        return Response({'error': 'Device not found'}, status=404)

    # 获取查询参数
    metric_type = request.GET.get('metric_type')
    try:
        duration_minutes = int(request.GET.get('duration', 60))
    except (ValueError, TypeError):
        duration_minutes = 60
    try:
        page = int(request.GET.get('page', 1))
    except (ValueError, TypeError):
        page = 1
    try:
        page_size = int(request.GET.get('page_size', 100))
        # 限制 page_size 范围防止过大查询
        page_size = max(1, min(page_size, 1000))
    except (ValueError, TypeError):
        page_size = 100

    # 计算时间范围
    duration = timedelta(minutes=duration_minutes)
    start_time = timezone.now() - duration

    # 构建查询
    queryset = MetricData.objects.filter(
        device=device,
        timestamp__gte=start_time
    ).order_by('-timestamp')

    if metric_type and metric_type not in EXCLUDED_METRIC_TYPES:
        queryset = queryset.filter(metric_type=metric_type)
    else:
        queryset = queryset.exclude(metric_type__in=EXCLUDED_METRIC_TYPES)

    if metric_type == 'interface_status':
        queryset = queryset.filter(value=1)

    # 分页
    paginator = Paginator(queryset, page_size)

    try:
        metrics_page = paginator.page(page)
    except PageNotAnInteger:
        metrics_page = paginator.page(1)
    except EmptyPage:
        metrics_page = paginator.page(paginator.num_pages)

    metrics_data = []
    for metric in metrics_page:
        metrics_data.append({
            'id': metric.id,
            'metric_type': metric.metric_type,
            'metric_type_display': metric.get_metric_type_display(),
            'metric_name': metric.metric_name,
            'display_metric_name': _get_metric_display_name(metric.metric_type, metric.metric_name),
            'value': metric.value,
            'unit': metric.unit,
            'timestamp': metric.timestamp.isoformat(),
        })

    return Response({
        'device': {
            'id': device.id,
            'name': device.name,
            'ip_address': device.ip_address,
        },
        'count': paginator.count,
        'total_pages': paginator.num_pages,
        'current_page': page,
        'metrics': metrics_data,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def monitoring_statistics_api(request):
    """
    监控统计API端点
    """
    # 按设备统计（优化：使用批量查询避免 N+1）
    devices = Device.objects.all()
    device_ids = list(devices.values_list('id', flat=True))

    # 批量获取每个接口的最新状态，再按设备聚合 UP/DOWN
    latest_interface_status = MetricData.objects.filter(
        device_id__in=device_ids,
        metric_type='interface_status'
    ).order_by('device_id', 'metric_name', '-timestamp').distinct('device_id', 'metric_name')

    stats_by_device = {}
    for metric in latest_interface_status:
        stat = stats_by_device.setdefault(metric.device_id, {'up': 0, 'down': 0})
        if int(metric.value) == 1:
            stat['up'] += 1
        else:
            stat['down'] += 1

    device_stats = []
    for device in devices:
        stat = stats_by_device.get(device.id, {'up': 0, 'down': 0})
        device_stats.append({
            'device': {
                'id': device.id,
                'name': device.name,
                'ip_address': device.ip_address,
            },
            'interface_status': {
                'up': stat.get('up', 0),
                'down': stat.get('down', 0),
            },
        })

    return Response({
        'devices': device_stats,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def monitoring_collect_api(request, device_id):
    """
    手动触发监控数据采集API端点

    Requirements: 4.1
    """
    try:
        device = Device.objects.get(pk=device_id)
    except Device.DoesNotExist:
        return Response({'error': 'Device not found'}, status=404)

    try:
        # 同步执行采集任务，确保数据立即更新
        from .services import MonitoringService
        service = MonitoringService()
        
        # 采集指标
        metrics = service.collect_metrics(device)
        
        # 存储指标
        stored_count = service.store_metrics(device, metrics)
        
        # 检查阈值
        alerts = service.check_thresholds(device, metrics)

        return Response({
            'success': True,
            'device_id': device_id,
            'stored_count': stored_count,
            'alerts_count': len(alerts),
            'message': 'Metrics collection completed successfully',
        })
        
    except Exception as exc:
        return Response({
            'success': False,
            'error': str(exc),
        }, status=500)
