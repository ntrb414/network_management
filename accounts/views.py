"""
用户账户管理页面视图

包含 AccountListView（用户列表页面）和 AccountDetailView（用户详情页面）。
需求引用：9.1, 9.4, 10.3
"""

from django.views.generic import ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework import status
from .models import UserProfile


class AccountListView(LoginRequiredMixin, ListView):
    """Display list of all user accounts."""

    model = User
    template_name = 'accounts/account_list.html'
    context_object_name = 'accounts'
    login_url = 'homepage:login'
    paginate_by = 20

    def get_queryset(self):
        """Return all UserProfiles, auto-creating for users without one."""
        # 批量获取所有用户和现有 profiles
        all_users = User.objects.all()
        existing_profiles = UserProfile.objects.filter(user__in=all_users).values_list('user_id', flat=True)

        # 找出没有 profile 的用户并批量创建
        missing_user_ids = set(u.id for u in all_users) - set(existing_profiles)
        if missing_user_ids:
            profiles_to_create = []
            for user in all_users:
                if user.id in missing_user_ids:
                    profiles_to_create.append(UserProfile(
                        user=user,
                        role='admin' if user.is_superuser else 'readonly'
                    ))
            UserProfile.objects.bulk_create(profiles_to_create)

        return UserProfile.objects.select_related('user').order_by('user__username')

    def get_context_data(self, **kwargs):
        """Add user info and account statistics to context."""
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        context['total_users'] = User.objects.count()
        context['active_users'] = User.objects.filter(is_active=True).count()
        return context


class AccountDetailView(LoginRequiredMixin, DetailView):
    """Display details of a specific user account."""

    model = User
    template_name = 'accounts/account_detail.html'
    context_object_name = 'account'
    login_url = 'homepage:login'

    def get_context_data(self, **kwargs):
        """Add user info and profile to context."""
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        try:
            context['profile'] = self.object.profile
        except UserProfile.DoesNotExist:
            context['profile'] = None
        return context


# ==================== API视图 ====================


def _is_admin_user(request):
    """检查是否为管理员用户"""
    if not request.user.is_authenticated:
        return False
    # Django superuser 直接放行
    if request.user.is_superuser or request.user.is_staff:
        return True
    try:
        return request.user.profile.role == 'admin'
    except UserProfile.DoesNotExist:
        return False


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def user_list_api(request):
    """
    用户列表API端点

    GET: 获取用户列表
    POST: 创建新用户

    Requirements: 9.1
    """
    # 权限检查：仅管理员可访问
    if not _is_admin_user(request):
        return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        # 获取用户列表（使用 select_related 预加载 profile 避免 N+1 查询）
        users = User.objects.select_related('profile').all().order_by('username')
        user_list = []

        for user in users:
            profile = getattr(user, 'profile', None)
            if profile:
                user_list.append({
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'is_active': user.is_active,
                    'date_joined': user.date_joined,
                    'role': profile.role,
                    'permissions': profile.permissions,
                })
            else:
                user_list.append({
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'is_active': user.is_active,
                    'date_joined': user.date_joined,
                    'role': 'readonly',
                    'permissions': {},
                })

        return Response({'users': user_list, 'total': len(user_list)})

    elif request.method == 'POST':
        # 创建新用户
        username = request.data.get('username')
        email = request.data.get('email')
        password = request.data.get('password')
        role = request.data.get('role', 'readonly')

        if not username or not password:
            return Response({'error': 'username and password are required'}, status=400)

        if User.objects.filter(username=username).exists():
            return Response({'error': 'Username already exists'}, status=400)

        # 创建用户
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
        )

        # 创建用户配置
        UserProfile.objects.create(
            user=user,
            role=role,
            permissions={},
        )

        return Response({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': role,
        }, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def user_detail_api(request, pk):
    """
    用户详情API端点

    GET: 获取用户详情
    PUT: 更新用户信息
    DELETE: 删除用户

    Requirements: 9.1
    """
    # 权限检查：仅管理员可访问
    if not _is_admin_user(request):
        return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

    try:
        user = User.objects.get(pk=pk)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=404)

    if request.method == 'GET':
        try:
            profile = user.profile
            return Response({
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'is_active': user.is_active,
                'date_joined': user.date_joined,
                'role': profile.role,
                'permissions': profile.permissions,
            })
        except UserProfile.DoesNotExist:
            return Response({
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'is_active': user.is_active,
                'date_joined': user.date_joined,
                'role': 'readonly',
                'permissions': {},
            })

    elif request.method == 'PUT':
        # 更新用户
        if 'email' in request.data:
            user.email = request.data['email']
        if 'is_active' in request.data:
            user.is_active = request.data['is_active']
        user.save()

        # 更新角色
        if 'role' in request.data:
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.role = request.data['role']
            profile.save()

        return Response({'success': True})

    elif request.method == 'DELETE':
        if user == request.user:
            return Response({'error': 'Cannot delete yourself'}, status=400)
        user.delete()
        return Response({'success': True})


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def user_permissions_api(request, pk):
    """
    用户权限设置API端点

    为普通用户授予细粒度权限

    Requirements: 9.4
    """
    # 权限检查：仅管理员可访问
    if not _is_admin_user(request):
        return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

    try:
        user = User.objects.get(pk=pk)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=404)

    permissions = request.data.get('permissions', {})

    # 获取或创建用户配置
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.permissions = permissions
    profile.save()

    return Response({
        'id': user.id,
        'username': user.username,
        'permissions': profile.permissions,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def audit_log_list_api(request):
    """
    审计日志查询API端点

    筛选操作日志类型的SystemLog

    Requirements: 10.3
    """
    from logs.models import SystemLog

    # 获取查询参数
    user_id = request.GET.get('user_id')
    keyword = request.GET.get('keyword')
    start_time = request.GET.get('start_time')
    end_time = request.GET.get('end_time')
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 50))

    # 查询系统日志
    queryset = SystemLog.objects.filter(log_type='system')

    if user_id:
        queryset = queryset.filter(user_id=user_id)

    if keyword:
        queryset = queryset.filter(message__icontains=keyword)

    if start_time:
        from django.utils.dateparse import parse_datetime
        start_time = parse_datetime(start_time)
        if start_time:
            queryset = queryset.filter(timestamp__gte=start_time)

    if end_time:
        from django.utils.dateparse import parse_datetime
        end_time = parse_datetime(end_time)
        if end_time:
            queryset = queryset.filter(timestamp__lte=end_time)

    # 分页
    total = queryset.count()
    offset = (page - 1) * page_size
    logs = list(queryset[offset:offset + page_size].values(
        'id', 'message', 'timestamp', 'user_id', 'device_id'
    ))

    return Response({
        'total': total,
        'page': page,
        'page_size': page_size,
        'logs': logs,
    })
