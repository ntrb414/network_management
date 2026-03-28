"""
配置备份页面视图

包含 BackupListView（备份列表页面）、BackupDetailView（备份详情页面）、
ConfigBackupView（手动备份页面）和备份相关API。
需求引用：8.1, 8.2, 8.3, 8.4, 8.5, 8.6
"""

from django.views.generic import ListView, DetailView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import ConfigBackup


class BackupListView(LoginRequiredMixin, ListView):
    """Display list of all configuration backups."""

    model = ConfigBackup
    template_name = 'backups/backup_list.html'
    context_object_name = 'backups'
    login_url = 'homepage:login'
    paginate_by = 20

    def get(self, request, *args, **kwargs):
        return redirect('configs:config_backup')

    def get_queryset(self):
        """Return all backups ordered by backup time."""
        return ConfigBackup.objects.all().order_by('-backed_up_at')

    def get_context_data(self, **kwargs):
        """Add user info and backup statistics to context."""
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        context['total_backups'] = ConfigBackup.objects.count()
        context['total_count'] = ConfigBackup.objects.count()
        context['success_count'] = ConfigBackup.objects.filter(status='success').count()
        context['failed_count'] = ConfigBackup.objects.filter(status='failed').count()
        from devices.models import Device
        context['device_count'] = Device.objects.count()
        return context


class BackupDetailView(LoginRequiredMixin, DetailView):
    """Display details of a specific configuration backup."""

    model = ConfigBackup
    template_name = 'backups/backup_detail.html'
    context_object_name = 'backup'
    login_url = 'homepage:login'

    def get_context_data(self, **kwargs):
        """Add user info to context."""
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        return context


class ConfigBackupView(LoginRequiredMixin, TemplateView):
    """手动选择设备并触发配置备份的页面。"""

    template_name = 'backups/config_backup.html'
    login_url = 'homepage:login'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        return context


# ==================== API视图 ====================


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def backup_list_api(request):
    """
    备份列表API端点

    Requirements: 8.2
    """
    from .services import BackupService

    service = BackupService()

    try:
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
    except (ValueError, TypeError):
        page, page_size = 1, 20

    result = service.get_all_backups(page=page, page_size=page_size)

    return Response(result)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def device_backup_list_api(request, device_id):
    """
    设备备份列表API端点

    Requirements: 8.2
    """
    from .services import BackupService

    service = BackupService()

    try:
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
    except (ValueError, TypeError):
        page, page_size = 1, 20

    result = service.get_device_backups(device_id=device_id, page=page, page_size=page_size)

    return Response(result)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def backup_detail_api(request, pk):
    """
    备份详情API端点
    """
    try:
        backup = ConfigBackup.objects.get(pk=pk)
    except ConfigBackup.DoesNotExist:
        return Response({'error': 'Backup not found'}, status=404)

    return Response({
        'id': backup.id,
        'device_id': backup.device_id,
        'device_name': backup.device.name,
        'config_content': backup.config_content,
        'git_commit_hash': backup.git_commit_hash,
        'commit_message': backup.commit_message,
        'backed_up_at': backup.backed_up_at,
        'backed_up_by': backup.backed_up_by.username if backup.backed_up_by else None,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def backup_create_api(request):
    """
    创建设备配置备份API端点

    Requirements: 8.1, 8.3, 8.4
    """
    from devices.models import Device
    from .services import BackupService

    service = BackupService()

    device_id = request.data.get('device_id')
    config_content = request.data.get('config_content')
    commit_message = request.data.get('commit_message', '')

    if not device_id or not config_content:
        return Response({'error': 'device_id and config_content are required'}, status=400)

    try:
        device = Device.objects.get(id=device_id)
    except Device.DoesNotExist:
        return Response({'error': 'Device not found'}, status=404)

    result = service.backup_device_config(
        device=device,
        config_content=config_content,
        commit_message=commit_message,
        user=request.user
    )

    if result.get('success'):
        return Response(result)
    else:
        return Response(result, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def backup_compare_api(request):
    """
    备份版本对比API端点

    Requirements: 8.5, 8.6
    """
    from .services import BackupService

    service = BackupService()

    backup1_id = request.GET.get('backup1_id')
    backup2_id = request.GET.get('backup2_id')

    if not backup1_id or not backup2_id:
        return Response({'error': 'backup1_id and backup2_id are required'}, status=400)

    try:
        result = service.compare_versions(int(backup1_id), int(backup2_id))
    except (ValueError, TypeError):
        return Response({'error': 'Invalid backup ID format'}, status=400)

    if result.get('success'):
        return Response(result)
    else:
        return Response(result, status=400)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def backup_trigger_api(request):
    """
    触发单个设备配置备份任务（异步）

    将备份任务投入 Celery 队列异步执行。

    Requirements: 8.1
    """
    from devices.models import Device
    from .tasks import backup_single_device

    device_id = request.data.get('device_id')
    commit_message = request.data.get('commit_message', '')

    if not device_id:
        return Response({'error': 'device_id is required'}, status=400)

    try:
        device = Device.objects.get(id=device_id)
    except Device.DoesNotExist:
        return Response({'error': 'Device not found'}, status=404)

    # 异步提交到 Celery 队列
    task = backup_single_device.delay(int(device_id), commit_message)

    return Response({
        'success': True,
        'task_id': task.id,
        'device_id': device_id,
        'device_name': device.name,
        'message': f'备份任务已提交，任务ID: {task.id}',
    })

