# 设备管理页面视图和API
import logging
from django.views.generic import ListView, DetailView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.http import JsonResponse
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import has_module_permission

logger = logging.getLogger(__name__)

from .models import Device
from .utils import ping_host


# ==================== 页面视图 ====================

class DeviceListView(LoginRequiredMixin, ListView):
    # 设备列表页面
    model = Device
    template_name = 'devices/device_list.html'
    context_object_name = 'devices'
    login_url = 'homepage:login'
    paginate_by = 20

    def get_queryset(self):
        # 返回按名称排序的所有设备
        return Device.objects.all().order_by('name')

    def get_context_data(self, **kwargs):
        # 添加用户权限信息到上下文
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        context["can_manage_devices"] = has_module_permission(self.request.user, "devices", "edit")
        context["is_readonly_user"] = not context["can_manage_devices"]
        
        return context


class DeviceDetailView(LoginRequiredMixin, DetailView):
    # 设备详情页面
    model = Device
    template_name = 'devices/device_detail.html'
    context_object_name = 'device'
    login_url = 'homepage:login'

    def get_context_data(self, **kwargs):
        # 添加用户权限和端口信息到上下文
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        context["can_manage_devices"] = has_module_permission(self.request.user, "devices", "edit")
        context["is_readonly_user"] = not context["can_manage_devices"]
        
        context['ports'] = self.object.ports.all()
        return context


class DeviceSSHTerminalView(LoginRequiredMixin, TemplateView):
    # SSH终端专用页面，在新窗口中打开
    template_name = 'devices/ssh_terminal.html'
    login_url = 'homepage:login'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        device_id = kwargs.get('pk')

        try:
            device = Device.objects.get(pk=device_id)
            context['device'] = device

            # 从URL参数获取连接信息
            context['username'] = self.request.GET.get('username', device.ssh_username or '')
            context['password'] = self.request.GET.get('password', device.ssh_password or '')
            context['port'] = int(self.request.GET.get('port', device.ssh_port or 22))

        except Device.DoesNotExist:
            context['device'] = None
            context['username'] = ''
            context['password'] = ''
            context['port'] = 22

        return context


class DeviceConfigView(LoginRequiredMixin, DetailView):
    # 设备配置页面，显示运行配置和启动配置
    model = Device
    template_name = 'devices/device_config_view.html'
    context_object_name = 'device'
    login_url = 'homepage:login'

    def get_context_data(self, **kwargs):
        # 添加配置数据到上下文
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        context["can_manage_devices"] = has_module_permission(self.request.user, "devices", "edit")
        context["is_readonly_user"] = not context["can_manage_devices"]
        

        # 获取设备列表（用于垂直滚动切换）
        context['device_list'] = Device.objects.all().order_by('name')

        # 获取运行配置和启动配置
        from configs.services import ConfigManagementService
        service = ConfigManagementService()

        device = self.object

        # 获取运行配置缓存时间
        running_cache_time = service.get_config_cache_time(device.id, 'running')
        startup_cache_time = service.get_config_cache_time(device.id, 'startup')

        # 获取运行配置（优先从Redis缓存读取）
        try:
            running_config = service.get_current_config(device)
            if running_config:
                context['running_config'] = running_config
                context['running_cache_status'] = f'缓存' if running_cache_time else '缓存(无时间)'
            else:
                context['running_config'] = '配置为空\n暂无缓存数据，请点击"实时读取"获取配置。'
                context['running_cache_status'] = '无缓存'
        except Exception as e:
            context['running_config'] = f"无法获取运行配置\n错误: {str(e)}"
            context['running_cache_status'] = '获取失败'

        # 获取启动配置（优先从Redis缓存读取）
        try:
            startup_config = service.get_startup_config(device)
            if startup_config:
                context['startup_config'] = startup_config
                context['startup_cache_status'] = f'缓存' if startup_cache_time else '缓存(无时间)'
            else:
                context['startup_config'] = '配置为空\n暂无缓存数据，请点击"实时读取"获取配置。'
                context['startup_cache_status'] = '无缓存'
        except Exception as e:
            context['startup_config'] = f"无法获取启动配置\n错误: {str(e)}"
            context['startup_cache_status'] = '获取失败'

        # 获取最后备份时间
        context['running_backup_time'] = running_cache_time
        context['startup_backup_time'] = startup_cache_time

        return context


# ==================== API视图 ====================

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def device_list_api(request):
    # 设备列表API：GET返回设备列表（支持分页筛选），POST创建设备
    if request.method == 'GET':
        # 获取查询参数
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        device_type = request.GET.get('device_type')
        status = request.GET.get('status')
        search = request.GET.get('search')

        # 构建查询集
        queryset = Device.objects.all().order_by('name')

        # 设备类型筛选
        if device_type:
            queryset = queryset.filter(device_type=device_type)

        # 设备状态筛选
        if status:
            queryset = queryset.filter(status=status)

        # 关键字搜索
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(ip_address__icontains=search) |
                Q(location__icontains=search)
            )

        # 分页
        paginator = Paginator(queryset, page_size)

        try:
            devices_page = paginator.page(page)
        except PageNotAnInteger:
            devices_page = paginator.page(1)
        except EmptyPage:
            devices_page = paginator.page(paginator.num_pages)

        # 构建响应数据
        devices_data = []
        for device in devices_page:
            devices_data.append({
                'id': device.id,
                'name': device.name,
                'device_type': device.device_type,
                'device_type_display': device.get_device_type_display(),
                'ip_address': device.ip_address,
                'status': device.status,
                'status_display': device.get_status_display(),
                'location': device.location,
                'layer': device.layer,
                'layer_display': device.get_layer_display() if device.layer else None,
                'model': device.model,
                'created_at': device.created_at.isoformat(),
                'updated_at': device.updated_at.isoformat(),
            })

        return Response({
            'count': paginator.count,
            'total_pages': paginator.num_pages,
            'current_page': page,
            'page_size': page_size,
            'results': devices_data,
        })

    elif request.method == 'POST':
        # 创建设备
        from .services import DeviceDiscoveryService
        service = DeviceDiscoveryService()

        try:
            device = service.add_device_manually(request.data)
            return Response({
                'id': device.id,
                'name': device.name,
                'ip_address': device.ip_address,
            }, status=201)
        except Exception as e:
            return Response({'error': str(e)}, status=400)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def device_detail_api(request, pk):
 
    try:
        device = Device.objects.get(pk=pk)
    except Device.DoesNotExist:
        return Response({'error': 'Device not found'}, status=404)

    if request.method == 'GET':
        # 获取设备详情
        from .services import DeviceDiscoveryService
        service = DeviceDiscoveryService()
        details = service.get_device_details(device)

        return Response(details)

    elif request.method == 'PUT':
        # 记录更新前的状态，用于检测状态变更
        old_status = device.status

        # 更新设备信息
        for field in ['name', 'device_type', 'ip_address', 'status',
                      'location', 'layer', 'model', 'ssh_port',
                      'ssh_username', 'ssh_password', 'snmp_community']:
            if field in request.data:
                setattr(device, field, request.data[field])

        device.save()

        # 状态变更为离线或故障时，立即创建告警
        new_status = device.status
        if old_status != new_status and new_status in ('offline', 'fault'):
            try:
                from alerts.services import AlertService
                alert_service = AlertService()
                if new_status == 'offline':
                    alert_service.create_device_offline_alert(device)
                else:
                    alert_service.create_device_fault_alert(device)
            except Exception as e:
                logger.warning(f"创建设备状态告警失败: {e}")

        return Response({
            'id': device.id,
            'name': device.name,
            'ip_address': device.ip_address,
        })

    elif request.method == 'DELETE':
        device.delete()
        return Response(status=204)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def device_statistics_api(request):
    # 设备统计API：返回按类型和状态的统计信息
    from django.db.models import Count

    # 按设备类型统计
    by_type = Device.objects.values('device_type').annotate(
        count=Count('id')
    ).order_by('-count')

    type_stats = []
    total_devices = Device.objects.count()

    for item in by_type:
        device_type = item['device_type']
        count = item['count']
        percentage = (count / total_devices * 100) if total_devices > 0 else 0

        type_stats.append({
            'device_type': device_type,
            'device_type_display': Device.get_device_type_display(Device(device_type=device_type)),
            'count': count,
            'percentage': round(percentage, 2),
        })

    # 按状态统计
    by_status = Device.objects.values('status').annotate(
        count=Count('id')
    ).order_by('-count')

    status_stats = []
    for item in by_status:
        status = item['status']
        count = item['count']
        percentage = (count / total_devices * 100) if total_devices > 0 else 0

        status_stats.append({
            'status': status,
            'status_display': Device.get_status_display(Device(status=status)),
            'count': count,
            'percentage': round(percentage, 2),
        })

    return Response({
        'total_devices': total_devices,
        'by_device_type': type_stats,
        'by_status': status_stats,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def device_discover_api(request):
    # 设备发现API：触发IP范围扫描
    start_ip = request.data.get('start_ip')
    end_ip = request.data.get('end_ip')

    if not start_ip or not end_ip:
        return Response(
            {'error': 'start_ip and end_ip are required'},
            status=400
        )

    # 触发异步任务
    from .tasks import scan_ip_range_task
    task = scan_ip_range_task.delay(start_ip, end_ip)

    return Response({
        'task_id': task.id,
        'message': 'Device discovery started',
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def device_export_api(request):
    #导出设备清单为Excel或JSON格式
   
    export_format = request.GET.get('format', 'json')

    # 获取所有设备
    devices = Device.objects.all().order_by('name')

    if export_format == 'json':
        # 导出为JSON
        import json
        from django.http import HttpResponse

        data = []
        for device in devices:
            data.append({
                'name': device.name,
                'device_type': device.device_type,
                'device_type_display': device.get_device_type_display(),
                'ip_address': device.ip_address,
                'status': device.status,
                'status_display': device.get_status_display(),
                'location': device.location,
                'layer': device.layer,
                'model': device.model,
            })

        return Response({
            'devices': data,
            'total_count': len(data),
        })

    elif export_format == 'excel':
        # 导出为Excel
        # 需要安装openpyxl库
        try:
            import openpyxl
            from io import BytesIO
            from django.http import HttpResponse

            workbook = openpyxl.Workbook()
            worksheet = workbook.active
            worksheet.title = 'Devices'

            # 添加表头
            headers = ['Name', 'Type', 'IP Address', 'Status', 'Location', 'Layer', 'Model']
            worksheet.append(headers)

            # 添加数据
            for device in devices:
                worksheet.append([
                    device.name,
                    device.get_device_type_display(),
                    device.ip_address,
                    device.get_status_display(),
                    device.location,
                    device.get_layer_display() if device.layer else '',
                    device.model,
                ])

            # 保存到响应
            buffer = BytesIO()
            workbook.save(buffer)
            buffer.seek(0)

            response = HttpResponse(
                buffer.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = 'attachment; filename=devices.xlsx'

            return response

        except ImportError:
            return Response(
                {'error': 'openpyxl library is required for Excel export'},
                status=500
            )

    else:
        return Response(
            {'error': 'Unsupported format. Use json or excel.'},
            status=400
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def device_config_api(request, pk):
    # 获取设备的运行配置和启动配置
    try:
        device = Device.objects.get(pk=pk)
    except Device.DoesNotExist:
        return Response({'error': 'Device not found'}, status=404)

    from configs.services import ConfigManagementService
    service = ConfigManagementService()

    # 获取运行配置
    try:
        running_config = service.get_current_config(device)
        running_config = running_config if running_config else "配置为空"
    except Exception as e:
        running_config = f"无法获取运行配置\n错误: {str(e)}"

    # 获取启动配置
    try:
        startup_config = service.get_startup_config(device)
        startup_config = startup_config if startup_config else "配置为空"
    except Exception as e:
        startup_config = f"无法获取启动配置\n错误: {str(e)}"

    # 获取最后备份时间
    running_backup_time = service.get_config_cache_time(device.id, 'running')
    startup_backup_time = service.get_config_cache_time(device.id, 'startup')

    return Response({
        'device_id': device.id,
        'device_name': device.name,
        'ip_address': device.ip_address,
        'running_config': running_config,
        'startup_config': startup_config,
        'running_backup_time': running_backup_time,
        'startup_backup_time': startup_backup_time,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def device_config_realtime_api(request, pk):
    # 通过SSH实时获取设备配置（不使用缓存）
    try:
        device = Device.objects.get(pk=pk)
    except Device.DoesNotExist:
        return Response({'error': 'Device not found'}, status=404)

    from configs.services import ConfigManagementService
    from django.utils import timezone

    service = ConfigManagementService()
    now = timezone.now()
    result = {
        'success': True,
        'device_id': device.id,
        'device_name': device.name,
        'ip_address': device.ip_address,
        'running_config': None,
        'startup_config': None,
        'running_backup_time': now.isoformat(),
        'startup_backup_time': now.isoformat(),
        'running_error': None,
        'startup_error': None,
    }

    # 实时获取运行配置（不使用缓存）
    try:
        running_config = service.get_current_config(device, use_cache=False)
        if running_config:
            result['running_config'] = running_config
        else:
            result['running_config'] = "配置为空"
            result['running_error'] = '设备返回空配置，请检查设备连接和配置'
    except Exception as e:
        logger.error(f"实时获取设备 {device.name} 运行配置失败: {e}")
        result['running_config'] = "获取失败"
        result['running_error'] = str(e)
        result['success'] = False

    # 实时获取启动配置（不使用缓存）
    try:
        startup_config = service.get_startup_config(device, use_cache=False)
        if startup_config:
            result['startup_config'] = startup_config
        else:
            result['startup_config'] = "配置为空"
            result['startup_error'] = '设备返回空配置，请检查设备连接和配置'
    except Exception as e:
        logger.error(f"实时获取设备 {device.name} 启动配置失败: {e}")
        result['startup_config'] = "获取失败"
        result['startup_error'] = str(e)
        result['success'] = False

    if not result['success']:
        return Response(result, status=500)
    return Response(result)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def device_ping_api(request, pk):
    # 对指定设备执行Ping测试，更新设备状态
    try:
        device = Device.objects.get(pk=pk)
    except Device.DoesNotExist:
        return Response({'error': 'Device not found'}, status=404)

    ip_address = device.ip_address

    if not ip_address:
        return Response({'error': 'Device has no IP address'}, status=400)

    try:
        result = ping_host(ip_address)

        # 检查ping结果
        if not isinstance(result, dict):
            device.status = 'fault'
            device.latency = None
            device.save(update_fields=['status', 'latency'])
            return Response({
                'success': False,
                'error': 'Ping test failed',
                'status': 'fault',
                'status_display': '故障',
                'message': 'Ping测试失败'
            }, status=500)

        is_reachable = result.get('reachable', False)

        if is_reachable:
            new_status = 'online'
            device.status = new_status
            device.latency = result.get('latency')
            device.save(update_fields=['status', 'latency'])

            return Response({
                'success': True,
                'device_id': device.id,
                'device_name': device.name,
                'ip_address': ip_address,
                'reachable': True,
                'latency': result.get('latency'),
                'status': 'online',
                'status_display': '在线',
                'message': f'设备 {device.name} ({ip_address}) 在线，延迟 {result.get("latency")}ms'
            })
        else:
            old_status = device.status
            device.status = 'fault'
            device.latency = None
            device.save(update_fields=['status', 'latency'])

            # 验证状态已更新
            device.refresh_from_db()

            # 状态从非故障变为故障时，创建告警
            _create_device_fault_alert_if_needed(device, old_status)

            error_msg = result.get('error', '')
            return Response({
                'success': True,
                'device_id': device.id,
                'device_name': device.name,
                'ip_address': ip_address,
                'reachable': False,
                'latency': None,
                'status': 'fault',
                'status_display': '故障',
                'message': f'设备 {device.name} ({ip_address}) 不可达' + (f': {error_msg}' if error_msg else '')
            })

    except Exception as e:
        old_status = device.status
        device.status = 'fault'
        device.latency = None
        device.save(update_fields=['status', 'latency'])
        _create_device_fault_alert_if_needed(device, old_status)
        return Response({
            'success': False,
            'error': str(e),
            'latency': None,
            'status': 'fault',
            'status_display': '故障',
            'message': f'Ping测试失败: {str(e)}'
        }, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def device_ping_all_api(request):
    # 对所有设备执行Ping测试，更新设备状态
    devices = Device.objects.all()

    results = []
    online_count = 0
    offline_count = 0

    for device in devices:
        ip_address = device.ip_address

        if not ip_address:
            results.append({
                'device_id': device.id,
                'device_name': device.name,
                'ip_address': None,
                'reachable': False,
                'status': 'unknown',
                'message': '设备无IP地址'
            })
            continue

        try:
            result = ping_host(ip_address)

            if result['reachable']:
                device.status = 'online'
                device.save(update_fields=['status'])
                online_count += 1
                results.append({
                    'device_id': device.id,
                    'device_name': device.name,
                    'ip_address': ip_address,
                    'reachable': True,
                    'latency': result.get('latency'),
                    'status': 'online',
                    'message': f'在线，延迟 {result.get("latency")}ms'
                })
            else:
                old_status = device.status
                device.status = 'fault'
                device.save(update_fields=['status'])
                offline_count += 1
                _create_device_fault_alert_if_needed(device, old_status)
                results.append({
                    'device_id': device.id,
                    'device_name': device.name,
                    'ip_address': ip_address,
                    'reachable': False,
                    'latency': None,
                    'status': 'fault',
                    'message': '不可达'
                })

        except Exception as e:
            old_status = device.status
            device.status = 'fault'
            device.save(update_fields=['status'])
            offline_count += 1
            _create_device_fault_alert_if_needed(device, old_status)
            results.append({
                'device_id': device.id,
                'device_name': device.name,
                'ip_address': ip_address,
                'reachable': False,
                'latency': None,
                'status': 'fault',
                'message': f'测试失败: {str(e)}'
            })

    return Response({
        'success': True,
        'total': devices.count(),
        'online': online_count,
        'offline': offline_count,
        'results': results
    })


def _create_device_fault_alert_if_needed(device, old_status):
    # 状态从非fault变为fault时创建故障告警
    if old_status == 'fault':
        return
    try:
        from alerts.services import AlertService
        AlertService().create_device_fault_alert(device)
    except Exception as e:
        logger.warning(f"创建设备故障告警失败: {e}")


def _create_device_offline_alert_if_needed(device, old_status):
    # 状态从非offline变为offline时创建离线告警
    if old_status == 'offline':
        return
    try:
        from alerts.services import AlertService
        AlertService().create_device_offline_alert(device)
    except Exception as e:
        logger.warning(f"创建设备离线告警失败: {e}")



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def check_all_devices_status_api(request):
    # 同步检查所有设备状态，返回在线/离线统计
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from django.utils import timezone
    from .utils import DEVICE_CHECK_MAX_WORKERS

    try:
        devices = list(Device.objects.all())
        total_devices = len(devices)
        online_count = 0
        offline_count = 0
        updated_devices = []

        def check_device(device):
            # 检查单个设备状态
            result = ping_host(device.ip_address, count=1, timeout=2)
            return device, result.get('reachable', False), result.get('latency')

        # 使用线程池并发检测
        max_workers = min(DEVICE_CHECK_MAX_WORKERS, total_devices) if total_devices > 0 else 1
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(check_device, device): device for device in devices}
            results = []
            for future in as_completed(futures):
                results.append(future.result())

        # 处理结果
        for device, is_online, latency in results:
            old_status = device.status
            if is_online:
                device.last_seen = timezone.now()
                device.latency = latency
                if device.status != 'online':
                    device.status = 'online'
                    device.save()
                    updated_devices.append({
                        'id': device.id,
                        'name': device.name,
                        'old_status': old_status,
                        'new_status': 'online'
                    })
                else:
                    device.save()
                online_count += 1
            else:
                if device.status != 'offline':
                    device.status = 'offline'
                    device.save()
                    updated_devices.append({
                        'id': device.id,
                        'name': device.name,
                        'old_status': old_status,
                        'new_status': 'offline'
                    })
                offline_count += 1
                _create_device_offline_alert_if_needed(device, old_status)

        return Response({
            'success': True,
            'total_devices': total_devices,
            'online_count': online_count,
            'offline_count': offline_count,
            'updated': updated_devices
        })

    except Exception as e:
        logger.error(f"检查设备状态失败: {e}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)
