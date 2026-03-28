"""
IP Management Views
"""
import ipaddress
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import models
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.urls import reverse_lazy
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Subnet, IPScanTask, IPAddress, AllocationLog
from .services import IPScanService, IPAMService, NetworkDiscoveryService
from .tasks import enqueue_scan_task
from devices.models import Device


# ============ 网段管理视图 ============

class SubnetListView(LoginRequiredMixin, ListView):
    """网段列表视图"""
    model = Subnet
    template_name = 'ipmanagement/subnet_list.html'
    context_object_name = 'subnets'
    login_url = 'homepage:login'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        return context


class SubnetCreateView(LoginRequiredMixin, CreateView):
    """创建网段视图"""
    model = Subnet
    template_name = 'ipmanagement/subnet_form.html'
    fields = ['cidr', 'name', 'vlan_id', 'description', 'is_active']
    success_url = reverse_lazy('ipmanagement:subnet_list')
    login_url = 'homepage:login'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        context['title'] = '添加网段'
        return context

    def form_valid(self, form):
        form.instance.source = 'manual'
        return super().form_valid(form)


class SubnetUpdateView(LoginRequiredMixin, UpdateView):
    """编辑网段视图"""
    model = Subnet
    template_name = 'ipmanagement/subnet_form.html'
    fields = ['cidr', 'name', 'vlan_id', 'description', 'is_active']
    success_url = reverse_lazy('ipmanagement:subnet_list')
    login_url = 'homepage:login'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        context['title'] = '编辑网段'
        return context


class SubnetDetailView(LoginRequiredMixin, DetailView):
    """网段详情视图 - 显示网段内所有IP地址"""
    model = Subnet
    template_name = 'ipmanagement/subnet_detail.html'
    context_object_name = 'subnet'
    login_url = 'homepage:login'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        context['devices'] = Device.objects.all().order_by('name')
        allowed_status = {'available', 'allocated', 'reserved'}

        ip_list = self.object.ip_addresses.all()

        status_filter = self.request.GET.get('status')
        if status_filter and status_filter != 'all' and status_filter in allowed_status:
            ip_list = ip_list.filter(status=status_filter)

        search = self.request.GET.get('search', '').strip()
        if search:
            ip_list = ip_list.filter(
                models.Q(ip_address__icontains=search) |
                models.Q(hostname__icontains=search) |
                models.Q(description__icontains=search)
            )

        paginator = Paginator(ip_list, 50)
        page = self.request.GET.get('page', 1)
        try:
            context['ip_list'] = paginator.page(page)
        except PageNotAnInteger:
            context['ip_list'] = paginator.page(1)
        except EmptyPage:
            context['ip_list'] = paginator.page(paginator.num_pages)

        context['total_count'] = ip_list.count()
        context['status_filter'] = status_filter if status_filter in allowed_status else 'all'
        context['search'] = search

        from django.db.models import Count
        status_stats = ip_list.values('status').annotate(count=Count('status'))
        context['status_stats'] = {item['status']: item['count'] for item in status_stats}

        return context


class SubnetDeleteView(LoginRequiredMixin, DeleteView):
    """删除网段视图"""
    model = Subnet
    template_name = 'ipmanagement/subnet_confirm_delete.html'
    success_url = reverse_lazy('ipmanagement:subnet_list')
    login_url = 'homepage:login'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        return context


# ============ IP扫描视图 ============

class IPScanView(LoginRequiredMixin, ListView):
    """IP扫描页面视图"""
    template_name = 'ipmanagement/ip_scan.html'
    model = IPScanTask
    context_object_name = 'scan_tasks'
    paginate_by = 10
    login_url = 'homepage:login'

    def get_queryset(self):
        return IPScanTask.objects.all()[:20]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        context['subnets'] = Subnet.objects.filter(is_active=True)
        return context


# ============ 分配历史视图 ============

class AllocationHistoryView(LoginRequiredMixin, ListView):
    """IP分配历史视图"""
    model = AllocationLog
    template_name = 'ipmanagement/allocation_history.html'
    context_object_name = 'logs'
    paginate_by = 50
    login_url = 'homepage:login'

    def get_queryset(self):
        queryset = AllocationLog.objects.all()

        ip_filter = self.request.GET.get('ip')
        if ip_filter:
            queryset = queryset.filter(ip_address__icontains=ip_filter)

        action_filter = self.request.GET.get('action')
        if action_filter and action_filter != 'all':
            queryset = queryset.filter(action=action_filter)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        context['ip_filter'] = self.request.GET.get('ip', '')
        context['action_filter'] = self.request.GET.get('action', 'all')
        return context


# ============ API接口 ============

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_subnets(request):
    """API: 列出所有子网 / 创建子网"""
    if request.method == 'GET':
        subnets = Subnet.objects.all().order_by('cidr')
        data = []
        for subnet in subnets:
            data.append({
                'id': subnet.id,
                'cidr': subnet.cidr,
                'name': subnet.name,
                'vlan_id': subnet.vlan_id,
                'description': subnet.description,
                'source': subnet.source,
                'is_active': subnet.is_active,
                'total_ips': subnet.total_ips,
                'available_ips': subnet.available_ips,
                'used_ips': subnet.used_ips,
                'usage_rate': subnet.usage_rate,
                'created_at': subnet.created_at,
                'updated_at': subnet.updated_at,
            })
        return Response({'success': True, 'subnets': data})

    elif request.method == 'POST':
        cidr = request.data.get('cidr')
        name = request.data.get('name', '')
        vlan_id = request.data.get('vlan_id')
        description = request.data.get('description', '')
        is_active = request.data.get('is_active', True)
        source = request.data.get('source', 'manual')

        if not cidr:
            return Response({'success': False, 'error': '请提供CIDR'}, status=400)

        try:
            ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            return Response({'success': False, 'error': '无效的CIDR格式'}, status=400)

        if source not in dict(Subnet.SOURCE_CHOICES):
            return Response({'success': False, 'error': '无效的网段来源'}, status=400)

        if Subnet.objects.filter(cidr=cidr).exists():
            return Response({'success': False, 'error': 'CIDR已存在'}, status=400)

        subnet = Subnet.objects.create(
            cidr=cidr,
            name=name,
            vlan_id=vlan_id,
            description=description,
            is_active=is_active,
            source=source
        )

        return Response({
            'success': True,
            'subnet': {
                'id': subnet.id,
                'cidr': subnet.cidr,
                'name': subnet.name,
            }
        }, status=201)


@api_view(['GET', 'DELETE'])
@permission_classes([IsAuthenticated])
def api_subnet_detail(request, subnet_id):
    """API: 获取/删除子网详情"""
    try:
        subnet = Subnet.objects.get(id=subnet_id)
    except Subnet.DoesNotExist:
        return Response({'success': False, 'error': '子网不存在'}, status=404)

    if request.method == 'GET':
        service = IPAMService()
        usage = service.get_subnet_usage(subnet_id)

        return Response({
            'success': True,
            'subnet': {
                'id': subnet.id,
                'cidr': subnet.cidr,
                'name': subnet.name,
                'vlan_id': subnet.vlan_id,
                'description': subnet.description,
                'source': subnet.source,
                'is_active': subnet.is_active,
                'total_ips': subnet.total_ips,
                'available_ips': subnet.available_ips,
                'used_ips': subnet.used_ips,
                'usage_rate': subnet.usage_rate,
                'created_at': subnet.created_at,
                'updated_at': subnet.updated_at,
                'usage_detail': usage,
            }
        })

    elif request.method == 'DELETE':
        subnet.delete()
        return Response({'success': True, 'message': '子网已删除'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_subnet_available(request, subnet_id):
    """API: 获取网段内可用IP"""
    try:
        subnet = Subnet.objects.get(id=subnet_id)
    except Subnet.DoesNotExist:
        return Response({'success': False, 'error': '子网不存在'}, status=404)

    count = int(request.GET.get('count', 10))
    count = min(count, 100)

    service = IPAMService()
    ips = service.get_available_ips(subnet_id, count)

    return Response({
        'success': True,
        'subnet_id': subnet_id,
        'cidr': subnet.cidr,
        'available_ips': [{'ip_address': ip.ip_address, 'status': ip.status} for ip in ips]
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_subnet_allocate(request, subnet_id):
    """API: 批量分配IP"""
    try:
        subnet = Subnet.objects.get(id=subnet_id)
    except Subnet.DoesNotExist:
        return Response({'success': False, 'error': '子网不存在'}, status=404)

    start_ip = request.data.get('start_ip')
    end_ip = request.data.get('end_ip')
    device_id = request.data.get('device_id')
    description = request.data.get('description', '')

    if not start_ip or not end_ip:
        return Response({'success': False, 'error': '请提供起始IP和结束IP'}, status=400)

    device = None
    if device_id:
        try:
            device = Device.objects.get(id=device_id)
        except Device.DoesNotExist:
            return Response({'success': False, 'error': '设备不存在'}, status=404)

    service = IPAMService()
    result = service.bulk_allocate(
        subnet_id=subnet_id,
        start_ip=start_ip,
        end_ip=end_ip,
        device=device,
        user=request.user,
        description=description
    )

    if result['success']:
        return Response(result)
    else:
        return Response(result, status=400)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_subnet_release(request, subnet_id):
    """API: 批量释放IP"""
    ip_list = request.data.get('ip_list', [])
    reason = request.data.get('reason', '')

    if not ip_list:
        return Response({'success': False, 'error': '请提供IP列表'}, status=400)

    service = IPAMService()
    result = service.bulk_release(ip_list=ip_list, user=request.user, reason=reason)

    if result['success']:
        return Response(result)
    else:
        return Response(result, status=400)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_ips(request):
    """API: IP列表（支持过滤）"""
    subnet_id = request.GET.get('subnet_id')
    status = request.GET.get('status')
    search = request.GET.get('search', '')

    queryset = IPAddress.objects.select_related('subnet', 'device', 'allocated_by').all()

    if subnet_id:
        queryset = queryset.filter(subnet_id=subnet_id)
    if status and status != 'all':
        queryset = queryset.filter(status=status)
    if search:
        queryset = queryset.filter(
            models.Q(ip_address__icontains=search) |
            models.Q(hostname__icontains=search) |
            models.Q(description__icontains=search)
        )

    limit = int(request.GET.get('limit', 100))
    limit = min(limit, 500)
    queryset = queryset[:limit]

    ips = []
    for ip in queryset:
        ips.append({
            'id': ip.id,
            'ip_address': ip.ip_address,
            'subnet_id': ip.subnet_id,
            'subnet_cidr': ip.subnet.cidr,
            'hostname': ip.hostname,
            'mac_address': ip.mac_address,
            'description': ip.description,
            'status': ip.status,
            'status_display': ip.get_status_display(),
            'device_id': ip.device_id,
            'device_name': ip.device.name if ip.device else None,
            'allocated_at': ip.allocated_at,
            'allocated_by': ip.allocated_by.username if ip.allocated_by else None,
        })

    return Response({'success': True, 'count': len(ips), 'ips': ips})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_ip_detail(request, ip_address):
    """API: 获取IP详细信息"""
    service = IPAMService()
    result = service.get_ip_info(ip_address)

    if result['success']:
        return Response(result)
    else:
        return Response(result, status=404)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_ip_allocate(request, ip_address):
    """API: 分配单个IP"""
    device_id = request.data.get('device_id')
    hostname = request.data.get('hostname', '')
    description = request.data.get('description', '')

    device = None
    if device_id:
        try:
            device = Device.objects.get(id=device_id)
        except Device.DoesNotExist:
            return Response({'success': False, 'error': '设备不存在'}, status=404)

    service = IPAMService()
    result = service.allocate_ip(
        ip_address=ip_address,
        device=device,
        user=request.user,
        hostname=hostname,
        description=description
    )

    if result['success']:
        return Response(result)
    else:
        return Response(result, status=400)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_ip_release(request, ip_address):
    """API: 释放单个IP"""
    reason = request.data.get('reason', '')

    service = IPAMService()
    result = service.release_ip(ip_address=ip_address, user=request.user, reason=reason)

    if result['success']:
        return Response(result)
    else:
        return Response(result, status=400)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_ip_reserve(request, ip_address):
    """API: 预留单个IP"""
    description = request.data.get('description', '')
    device_id = request.data.get('device_id')

    device = None
    if device_id:
        try:
            device = Device.objects.get(id=device_id)
        except Device.DoesNotExist:
            return Response({'success': False, 'error': '设备不存在'}, status=404)

    service = IPAMService()
    result = service.reserve_ip(ip_address=ip_address, user=request.user, description=description, device=device)

    if result['success']:
        return Response(result)
    else:
        return Response(result, status=400)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_ip_update_status(request, ip_address):
    """API: 更新单个IP状态（仅支持可用/已分配/预留）"""
    new_status = request.data.get('status')
    allowed_status = {'available', 'allocated', 'reserved'}

    if new_status not in allowed_status:
        return Response({'success': False, 'error': '状态值无效，仅支持: available/allocated/reserved'}, status=400)

    try:
        ip = IPAddress.objects.get(ip_address=ip_address)
    except IPAddress.DoesNotExist:
        return Response({'success': False, 'error': 'IP地址不存在'}, status=404)

    old_status = ip.status
    if old_status == new_status:
        return Response({
            'success': True,
            'message': '状态未变化',
            'ip': {
                'ip_address': ip.ip_address,
                'status': ip.status,
                'status_display': ip.get_status_display(),
            }
        })

    ip.status = new_status
    ip.save(update_fields=['status', 'updated_at'])

    AllocationLog.objects.create(
        ip_address=ip.ip_address,
        hostname=ip.hostname,
        action='update',
        old_value={'status': old_status},
        new_value={'status': new_status},
        performed_by=request.user,
        notes='手动修改IP状态'
    )

    return Response({
        'success': True,
        'message': 'IP状态更新成功',
        'ip': {
            'ip_address': ip.ip_address,
            'status': ip.status,
            'status_display': ip.get_status_display(),
        }
    })


@csrf_exempt
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_scan_subnet(request):
    """API: 执行网段扫描（异步）"""
    cidr = request.data.get('cidr')
    subnet_id = request.data.get('subnet_id')

    if not cidr:
        return Response({'success': False, 'error': '请提供网段CIDR'}, status=400)

    try:
        ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return Response({'success': False, 'error': '无效的CIDR格式'}, status=400)

    if subnet_id:
        try:
            subnet = Subnet.objects.get(id=subnet_id)
            if subnet.cidr != cidr:
                return Response({'success': False, 'error': '网段ID与CIDR不匹配'}, status=400)
        except Subnet.DoesNotExist:
            return Response({'success': False, 'error': '网段不存在'}, status=404)

    task_id = enqueue_scan_task(cidr, subnet_id)

    return Response({
        'success': True,
        'task_id': task_id,
        'cidr': cidr,
        'status': 'pending',
        'message': '扫描任务已加入队列'
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_scan_status(request, task_id):
    """API: 获取扫描任务状态"""
    try:
        task = IPScanTask.objects.get(id=task_id)
    except IPScanTask.DoesNotExist:
        return Response({'success': False, 'error': '任务不存在'}, status=404)

    progress = round(task.scanned_ips / task.total_ips * 100, 1) if task.total_ips > 0 else 0

    return Response({
        'success': True,
        'task_id': task.id,
        'cidr': task.cidr,
        'status': task.status,
        'total_ips': task.total_ips,
        'scanned_ips': task.scanned_ips,
        'alive_ips': task.alive_ips,
        'progress': progress,
        'created_at': task.created_at,
        'completed_at': task.completed_at,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_scan_result(request, task_id):
    """API: 获取扫描任务结果（包含alive_hosts）"""
    try:
        task = IPScanTask.objects.get(id=task_id)
    except IPScanTask.DoesNotExist:
        return Response({'success': False, 'error': '任务不存在'}, status=404)

    service = IPScanService()
    result = service.get_scan_result(task_id)

    return Response(result)


@csrf_exempt
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_quick_scan(request):
    """API: 快速扫描（同步返回结果，仅适用于小网段）"""
    cidr = request.data.get('cidr')
    subnet_id = request.data.get('subnet_id')

    if not cidr:
        return Response({'success': False, 'error': '请提供网段CIDR'}, status=400)

    try:
        network = ipaddress.ip_network(cidr, strict=False)
        total = len(list(network.hosts()))

        if total > 256:
            return Response({
                'success': False,
                'error': '网段过大，请使用异步扫描接口',
                'max_hosts': 256,
                'requested_hosts': total
            }, status=400)

    except ValueError:
        return Response({'success': False, 'error': '无效的CIDR格式'}, status=400)

    if subnet_id:
        try:
            subnet = Subnet.objects.get(id=subnet_id)
            if subnet.cidr != cidr:
                return Response({'success': False, 'error': '网段ID与CIDR不匹配'}, status=400)
        except Subnet.DoesNotExist:
            return Response({'success': False, 'error': '网段不存在'}, status=404)

    scanner = IPScanService()
    all_results = scanner.scan_subnet(cidr, return_all=True)
    alive_hosts = [result for result in all_results if result.get('alive')]

    if subnet_id:
        service = IPAMService()
        service.sync_scan_results(subnet_id, all_results)

    return Response({
        'success': True,
        'cidr': cidr,
        'total': total,
        'alive_count': len(alive_hosts),
        'alive_hosts': alive_hosts,
        'status': 'completed',
        'message': '扫描完成'
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_sync_scan(request, task_id):
    """API: 将扫描结果同步到IPAM"""
    try:
        task = IPScanTask.objects.get(id=task_id)
    except IPScanTask.DoesNotExist:
        return Response({'success': False, 'error': '任务不存在'}, status=404)

    if not task.subnet:
        return Response({'success': False, 'error': '任务未关联网段，无法同步'}, status=400)

    scan_results = request.data.get('scan_results', [])

    service = IPAMService()
    result = service.sync_scan_results(task.subnet_id, scan_results)

    return Response(result)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_allocation_history(request):
    """API: 获取IP分配历史"""
    ip_address = request.GET.get('ip')
    limit = int(request.GET.get('limit', 100))
    limit = min(limit, 500)

    service = IPAMService()
    logs = service.get_allocation_history(ip_address=ip_address, limit=limit)

    return Response({
        'success': True,
        'count': len(logs),
        'logs': logs
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_subnet_usage(request, subnet_id):
    """API: 获取网段IP使用情况"""
    try:
        subnet = Subnet.objects.get(id=subnet_id)
    except Subnet.DoesNotExist:
        return Response({'success': False, 'error': '网段不存在'}, status=404)
    
    # 统计各状态IP数量（只统计：可用、已分配、预留）
    from django.db.models import Count
    stats = subnet.ip_addresses.filter(
        status__in=['available', 'allocated', 'reserved']
    ).values('status').annotate(count=Count('status'))
    status_counts = {item['status']: item['count'] for item in stats}
    
    # 计算使用率
    total_ips = subnet.total_ips
    allocated_ips = status_counts.get('allocated', 0)
    reserved_ips = status_counts.get('reserved', 0)
    available_ips = status_counts.get('available', 0)
    used_ips = allocated_ips + reserved_ips
    usage_rate = round(used_ips / total_ips * 100, 1) if total_ips > 0 else 0
    
    return Response({
        'success': True,
        'subnet': {
            'id': subnet.id,
            'cidr': subnet.cidr,
            'name': subnet.name,
            'total_ips': total_ips,
            'allocated_ips': allocated_ips,
            'reserved_ips': reserved_ips,
            'available_ips': available_ips,
            'used_ips': used_ips,
            'usage_rate': usage_rate,
            'status_breakdown': status_counts,
        }
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_batch_ip_operations(request, subnet_id):
    """API: 批量IP操作（分配/释放/预留）"""
    try:
        subnet = Subnet.objects.get(id=subnet_id)
    except Subnet.DoesNotExist:
        return Response({'success': False, 'error': '网段不存在'}, status=404)
    
    operation = request.data.get('operation')  # allocate/release/reserve
    ip_list = request.data.get('ip_list', [])
    
    if not ip_list:
        return Response({'success': False, 'error': '请提供IP列表'}, status=400)
    
    if operation not in ['allocate', 'release', 'reserve']:
        return Response({'success': False, 'error': '无效的操作类型'}, status=400)
    
    service = IPAMService()
    
    if operation == 'allocate':
        # 批量分配 - 需要设备信息
        device_id = request.data.get('device_id')
        description = request.data.get('description', '')
        
        if not device_id:
            return Response({'success': False, 'error': '批量分配需要提供设备ID'}, status=400)
            
        try:
            from devices.models import Device
            device = Device.objects.get(id=device_id)
        except Device.DoesNotExist:
            return Response({'success': False, 'error': '设备不存在'}, status=404)
        
        result = service.bulk_allocate(
            subnet_id=subnet_id,
            start_ip=ip_list[0] if ip_list else None,
            end_ip=ip_list[-1] if ip_list else None,
            device=device,
            user=request.user,
            description=description
        )
        
    elif operation == 'release':
        result = service.bulk_release(
            ip_list=ip_list, 
            user=request.user, 
            reason=request.data.get('reason', '批量释放')
        )
        
    elif operation == 'reserve':
        result = service.bulk_reserve(
            ip_list=ip_list,
            user=request.user,
            description=request.data.get('description', '批量预留')
        )
    
    if result['success']:
        return Response(result)
    else:
        return Response(result, status=400)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_auto_subnets(request):
    """API: 返回从设备表IP推导出的可添加网段"""
    discovery_service = NetworkDiscoveryService()
    subnets = [item for item in discovery_service.discover_network_subnet_details() if not item['exists']]

    return Response({
        'success': True,
        'subnets': subnets,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_discover_subnets(request):
    """API: 触发网段自动发现"""
    from .tasks import discover_subnets

    discover_subnets.delay()
    return Response({
        'success': True,
        'message': '网段自动发现任务已启动，请稍后刷新网段列表查看结果'
    })
