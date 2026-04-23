"""
性能监控页面视图和API

包含监控数据列表、实时监控、历史监控等视图。
"""

from django.views.generic import ListView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.conf import settings
from django.utils import timezone
from datetime import timedelta, datetime
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import MetricData
from .services import MonitoringService
from devices.models import Device


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
METRIC_TYPE_LABELS = dict(MetricData.METRIC_TYPES)


def _extract_metric_types(metrics):
    monitored_metric_types = set()

    interfaces = metrics.get('interfaces', [])
    if interfaces:
        if any(interface.get('status') is not None for interface in interfaces):
            monitored_metric_types.add('interface_status')
        if any(interface.get('in_mbps') is not None for interface in interfaces):
            monitored_metric_types.add('interface_in_traffic')
        if any(interface.get('out_mbps') is not None for interface in interfaces):
            monitored_metric_types.add('interface_out_traffic')
        if any(interface.get('in_drop_rate') is not None for interface in interfaces):
            monitored_metric_types.add('interface_in_drops')
        if any(interface.get('out_drop_rate') is not None for interface in interfaces):
            monitored_metric_types.add('interface_out_drops')

    if metrics.get('traffic'):
        monitored_metric_types.add('traffic')
    if metrics.get('packet_loss') is not None:
        monitored_metric_types.add('packet_loss')
    if metrics.get('connections') is not None:
        monitored_metric_types.add('connections')
    if metrics.get('ospf_neighbors'):
        monitored_metric_types.add('ospf_neighbor')
    if metrics.get('cpu_usage') is not None or metrics.get('cpu_utilization') is not None:
        monitored_metric_types.add('cpu')
    if metrics.get('memory_usage') is not None or metrics.get('memory_utilization') is not None:
        monitored_metric_types.add('memory')

    return monitored_metric_types


def _build_metric_type_items(monitored_metric_types):
    return [
        {
            'metric_type': metric_type,
            'label': METRIC_TYPE_LABELS.get(metric_type, metric_type),
        }
        for metric_type, _ in MetricData.METRIC_TYPES
        if metric_type in monitored_metric_types
    ]


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

    if metric_type == 'cpu' and metric_name == 'cpu_usage':
        return 'CPU利用率'

    if metric_type == 'memory' and metric_name == 'memory_usage':
        return '内存利用率'

    return metric_name


def _is_interface_up(value):
    try:
        return int(value) == 1
    except (TypeError, ValueError):
        return False


def _parse_snapshot_timestamp(timestamp):
    if not timestamp:
        return None

    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return None

    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed)

    return parsed


def _normalize_ospf_neighbors(neighbors):
    """Normalize legacy H3C OSPF state values for display/API output."""
    normalized_neighbors = []

    for neighbor in neighbors or []:
        if not isinstance(neighbor, dict):
            continue

        normalized = dict(neighbor)

        try:
            state_value = int(normalized.get('state'))
        except (TypeError, ValueError):
            state_value = None

        state_name = str(normalized.get('state_name') or '').strip().lower()

        # Legacy H3C snapshots may store zero-based state 7 as "Loading" while
        # actual adjacency is Full. Convert it to the standard 1-based Full(8).
        if normalized.get('interface_index') is not None and state_value == 7 and state_name == 'loading':
            normalized['state'] = 8
            normalized['state_name'] = 'Full'
            normalized['is_full'] = True

        normalized_neighbors.append(normalized)

    return normalized_neighbors



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
    if metric_type in {'cpu', 'memory'}:
        try:
            return f"{float(value):.2f} %"
        except (TypeError, ValueError):
            return f'{value} %'
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
        """Return flattened Redis metrics ordered by timestamp, with optional type filter."""
        service = MonitoringService()
        rows = []
        metric_type = self.request.GET.get('metric_type')
        devices = Device.objects.all().order_by('name')
        fallback_ts = timezone.make_aware(datetime(1970, 1, 1))

        for device in devices:
            snapshots = service.get_device_snapshots_from_redis(device.id, limit=100)
            metric_rows = service.flatten_snapshots_to_metric_rows(snapshots)

            for row in metric_rows:
                row_type = row.get('metric_type')
                if row_type in EXCLUDED_METRIC_TYPES:
                    continue
                if metric_type and metric_type not in EXCLUDED_METRIC_TYPES and row_type != metric_type:
                    continue

                row_timestamp = _parse_snapshot_timestamp(row.get('timestamp'))
                rows.append({
                    'device': {
                        'id': device.id,
                        'name': device.name,
                    },
                    'metric_type': row_type,
                    'metric_type_display': METRIC_TYPE_LABELS.get(row_type, row_type),
                    'metric_name': row.get('metric_name', ''),
                    'value': row.get('value'),
                    'unit': row.get('unit', ''),
                    'timestamp': row_timestamp or row.get('timestamp'),
                    'timestamp_sort': row_timestamp or fallback_ts,
                })

        rows.sort(key=lambda item: item['timestamp_sort'], reverse=True)
        for row in rows:
            row.pop('timestamp_sort', None)

        return rows

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
        context['metric_types'] = DISPLAY_METRIC_TYPES
        context['reload_time'] = getattr(settings, 'MONITORING_RELOAD_TIME', 30)

        service = MonitoringService()
        monitored_metric_types = set()

        devices = Device.objects.all().order_by('name')
        device_list = []
        for device in devices:
            latest_snapshot = service.get_latest_metrics_from_redis(device.id)
            metrics = latest_snapshot.get('metrics', {}) if latest_snapshot else {}
            monitored_metric_types.update(_extract_metric_types(metrics))

            item = {
                'device': device,
                'summary': {
                    'interface_status': None,
                    'interface_traffic': None,
                    'ospf': None,
                    'cpu': None,
                    'memory': None,
                },
                'last_metric_time': None,
            }

            interfaces = metrics.get('interfaces', [])
            if device.status == 'online' and interfaces:
                up_count = sum(1 for iface in interfaces if _is_interface_up(iface.get('status')))
                down_count = max(0, len(interfaces) - up_count)
                item['summary']['interface_status'] = f"{up_count} UP / {down_count} DOWN"

            ospf_neighbors = metrics.get('ospf_neighbors', [])
            ospf_neighbors = _normalize_ospf_neighbors(ospf_neighbors)
            if device.status == 'online' and ospf_neighbors:
                full_count = sum(
                    1
                    for neighbor in ospf_neighbors
                    if neighbor.get('is_full') or str(neighbor.get('state')) == '8'
                )
                total_count = len(ospf_neighbors)
                item['summary']['ospf'] = f"{full_count}/{total_count} Full"

            traffic_rows = metrics.get('traffic', [])
            if device.status == 'online' and traffic_rows:
                top_traffic = max(
                    traffic_rows,
                    key=lambda row: (row.get('in_octets') or 0) + (row.get('out_octets') or 0),
                )
                iface_name = top_traffic.get('interface', '-')
                in_octets = int(top_traffic.get('in_octets') or 0)
                out_octets = int(top_traffic.get('out_octets') or 0)
                item['summary']['interface_traffic'] = f"{iface_name}: IN {in_octets} / OUT {out_octets}"

            cpu_usage = metrics.get('cpu_usage')
            if cpu_usage is not None:
                item['summary']['cpu'] = f"{float(cpu_usage):.1f}%"

            memory_usage = metrics.get('memory_usage')
            if memory_usage is not None:
                item['summary']['memory'] = f"{float(memory_usage):.1f}%"

            item['last_metric_time'] = _parse_snapshot_timestamp(
                latest_snapshot.get('timestamp') if latest_snapshot else None
            )

            device_list.append(item)

        context['monitored_metric_types'] = _build_metric_type_items(monitored_metric_types)
        context['monitored_metric_types_count'] = len(context['monitored_metric_types'])
        context['device_list'] = device_list

        return context


class MonitoringMetricTypesView(LoginRequiredMixin, TemplateView):
    """Display list of currently monitored metric categories."""

    template_name = 'monitoring/monitoring_metric_types.html'
    login_url = 'homepage:login'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user

        service = MonitoringService()
        devices = Device.objects.all().order_by('name')
        monitored_metric_types = set()

        for device in devices:
            latest_snapshot = service.get_latest_metrics_from_redis(device.id)
            metrics = latest_snapshot.get('metrics', {}) if latest_snapshot else {}
            monitored_metric_types.update(_extract_metric_types(metrics))

        context['metric_type_items'] = _build_metric_type_items(monitored_metric_types)
        context['metric_types_count'] = len(context['metric_type_items'])

        return context


class MonitoringDeviceDetailView(LoginRequiredMixin, TemplateView):
    """Display detailed monitoring data for a single device."""

    template_name = 'monitoring/monitoring_device_detail.html'
    login_url = 'homepage:login'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        device = get_object_or_404(Device, pk=self.kwargs['device_id'])
        service = MonitoringService()
        latest_snapshot = service.get_latest_metrics_from_redis(device.id)
        metrics = latest_snapshot.get('metrics', {}) if latest_snapshot else {}

        context['user'] = self.request.user
        context['device'] = device
        context['reload_time'] = getattr(settings, 'MONITORING_RELOAD_TIME', 30)

        # 该设备的告警
        try:
            from alerts.models import Alert
            context['device_alerts'] = Alert.objects.filter(
                device=device
            ).order_by('-timestamp')[:10]
        except Exception:
            context['device_alerts'] = []

        context['latest_ospf_neighbors'] = _normalize_ospf_neighbors(metrics.get('ospf_neighbors', []))
        context['latest_cpu_usage'] = metrics.get('cpu_usage')
        context['latest_memory_usage'] = metrics.get('memory_usage')

        context['metric_types'] = DISPLAY_METRIC_TYPES
        return context


# ==================== API视图 ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def monitoring_device_realtime_api(request, device_id):
    """
    实时监控数据API端点
    """
    try:
        device = Device.objects.get(pk=device_id)
    except Device.DoesNotExist:
        return Response({'error': 'Device not found'}, status=404)

    service = MonitoringService()
    latest_snapshot = service.get_latest_metrics_from_redis(device_id)
    metrics_payload = latest_snapshot.get('metrics', {}) if latest_snapshot else {}
    if metrics_payload:
        metrics_payload = dict(metrics_payload)
        if metrics_payload.get('cpu_usage') is not None and metrics_payload.get('cpu_utilization') is None:
            metrics_payload['cpu_utilization'] = metrics_payload.get('cpu_usage')
        if metrics_payload.get('memory_usage') is not None and metrics_payload.get('memory_utilization') is None:
            metrics_payload['memory_utilization'] = metrics_payload.get('memory_usage')
    interfaces = metrics_payload.get('interfaces', []) if metrics_payload else []
    if interfaces:
        metrics_payload = dict(metrics_payload)
        metrics_payload['interfaces'] = [
            interface for interface in interfaces if _is_interface_up(interface.get('status'))
        ]

    ospf_neighbors = metrics_payload.get('ospf_neighbors', []) if metrics_payload else []
    if ospf_neighbors:
        metrics_payload = dict(metrics_payload)
        metrics_payload['ospf_neighbors'] = _normalize_ospf_neighbors(ospf_neighbors)

    return Response({
        'device': {
            'id': device.id,
            'name': device.name,
            'ip_address': device.ip_address,
        },
        'reload_time': getattr(settings, 'MONITORING_RELOAD_TIME', 30),
        'metrics': metrics_payload,
        'timestamp': latest_snapshot.get('timestamp') if latest_snapshot else None,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def monitoring_device_realtime_redis_api(request, device_id):
    """从 Redis 获取设备实时监控数据。"""
    try:
        device = Device.objects.get(pk=device_id)
    except Device.DoesNotExist:
        return Response({'error': 'Device not found'}, status=404)

    service = MonitoringService()
    latest_snapshot = service.get_latest_metrics_from_redis(device_id)
    metrics_payload = latest_snapshot.get('metrics', {}) if latest_snapshot else {}
    if metrics_payload:
        metrics_payload = dict(metrics_payload)
        if metrics_payload.get('cpu_usage') is not None and metrics_payload.get('cpu_utilization') is None:
            metrics_payload['cpu_utilization'] = metrics_payload.get('cpu_usage')
        if metrics_payload.get('memory_usage') is not None and metrics_payload.get('memory_utilization') is None:
            metrics_payload['memory_utilization'] = metrics_payload.get('memory_usage')
    interfaces = metrics_payload.get('interfaces', []) if metrics_payload else []
    if interfaces:
        metrics_payload = dict(metrics_payload)
        metrics_payload['interfaces'] = [
            interface for interface in interfaces if _is_interface_up(interface.get('status'))
        ]

    ospf_neighbors = metrics_payload.get('ospf_neighbors', []) if metrics_payload else []
    if ospf_neighbors:
        metrics_payload = dict(metrics_payload)
        metrics_payload['ospf_neighbors'] = _normalize_ospf_neighbors(ospf_neighbors)

    return Response({
        'device': {
            'id': device.id,
            'name': device.name,
            'ip_address': device.ip_address,
        },
        'reload_time': getattr(settings, 'MONITORING_RELOAD_TIME', 30),
        'metrics': metrics_payload,
        'timestamp': latest_snapshot.get('timestamp') if latest_snapshot else None,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def monitoring_device_metrics_api(request, device_id):
    """
    历史监控数据API端点

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

    duration = timedelta(minutes=duration_minutes)
    service = MonitoringService()
    snapshots = service.get_device_snapshots_from_redis(device.id, duration=duration, limit=200)
    metric_rows = service.flatten_snapshots_to_metric_rows(snapshots)

    if metric_type and metric_type not in EXCLUDED_METRIC_TYPES:
        metric_rows = [row for row in metric_rows if row.get('metric_type') == metric_type]
    else:
        metric_rows = [row for row in metric_rows if row.get('metric_type') not in EXCLUDED_METRIC_TYPES]

    if metric_type == 'interface_status':
        metric_rows = [row for row in metric_rows if _is_interface_up(row.get('value'))]

    paginator = Paginator(metric_rows, page_size)

    try:
        metrics_page = paginator.page(page)
    except PageNotAnInteger:
        metrics_page = paginator.page(1)
    except EmptyPage:
        metrics_page = paginator.page(paginator.num_pages)

    metrics_data = []
    start_index = (metrics_page.number - 1) * page_size
    for index, metric in enumerate(metrics_page.object_list, start=1):
        metric_type_value = metric.get('metric_type')
        metrics_data.append({
            'id': start_index + index,
            'metric_type': metric_type_value,
            'metric_type_display': METRIC_TYPE_LABELS.get(metric_type_value, metric_type_value),
            'metric_name': metric.get('metric_name', ''),
            'display_metric_name': _get_metric_display_name(
                metric_type_value,
                metric.get('metric_name', ''),
            ),
            'value': metric.get('value'),
            'unit': metric.get('unit', ''),
            'timestamp': metric.get('timestamp'),
        })

    return Response({
        'device': {
            'id': device.id,
            'name': device.name,
            'ip_address': device.ip_address,
        },
        'count': paginator.count,
        'total_pages': paginator.num_pages,
        'current_page': metrics_page.number,
        'metrics': metrics_data,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def monitoring_statistics_api(request):
    """
    监控统计API端点
    """
    service = MonitoringService()
    devices = Device.objects.all()

    device_stats = []
    for device in devices:
        latest_snapshot = service.get_latest_metrics_from_redis(device.id)
        interfaces = latest_snapshot.get('metrics', {}).get('interfaces', []) if latest_snapshot else []
        up_count = sum(1 for interface in interfaces if _is_interface_up(interface.get('status')))
        down_count = max(0, len(interfaces) - up_count)

        device_stats.append({
            'device': {
                'id': device.id,
                'name': device.name,
                'ip_address': device.ip_address,
            },
            'interface_status': {
                'up': up_count,
                'down': down_count,
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
