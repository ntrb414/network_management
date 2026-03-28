"""权限检查中间件。"""

from django.http import JsonResponse
from django.shortcuts import render

from .permissions import get_user_role, is_readonly_request_allowed


class PermissionMiddleware:
    """权限检查中间件类"""

    # 不需要权限检查的路径
    EXEMPT_URLS = [
        '/static/',  # 静态文件
        '/media/',   # 媒体文件
        '/api/auth/',  # 认证相关API
        '/api/auth/login/',
        '/api/auth/logout/',
        '/admin/',  # Django admin
        '/login/',  # 登录页面
        '/logout/',  # 退出页面
    ]

    # 只读模块（只允许GET请求）
    READONLY_MODULES = ['logs', 'monitoring']

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 检查是否需要权限检查
        if self._is_exempt(request):
            return self.get_response(request)

        # 检查是否是API请求（通过URL模式判断）
        is_api_request = self._is_api_path(request.path)

        # 检查用户是否已认证
        user = request.user
        if not user.is_authenticated:
            # 检查是否是AJAX请求（通过HTTP_X_REQUESTED_WITH header判断）
            is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

            if is_api_request or is_ajax:
                # API请求和AJAX请求返回401 JSON，让前端处理跳转
                return JsonResponse({'error': 'Authentication required'}, status=401)
            else:
                # 普通页面请求重定向到登录页面
                from django.urls import reverse
                from django.http import HttpResponseRedirect
                login_url = reverse('homepage:login')
                return HttpResponseRedirect(login_url)

        role = get_user_role(request.user)

        if role == 'readonly':
            if not is_readonly_request_allowed(request):
                return self._permission_denied_response(
                    request,
                    '只读用户仅可访问设备管理中的测试、配置查看与 SSH 相关功能'
                )
            return self.get_response(request)

        if role == 'admin':
            return self.get_response(request)

        # 普通用户根据permissions字段检查权限
        if request.method == 'GET':
            # GET请求通常不需要额外权限
            return self.get_response(request)

        # 检查模块权限
        module = self._get_module_from_path(request.path)
        if module:
            if not self._has_permission(request.user, module, request.method):
                return self._permission_denied_response(
                    request,
                    f'Permission denied: {request.method} not allowed for {module}'
                )

        return self.get_response(request)

    def _is_exempt(self, request):
        """检查路径是否免于权限检查"""
        for url in self.EXEMPT_URLS:
            if request.path.startswith(url):
                return True
        return False

    def _is_api_path(self, path):
        """检查路径是否为API请求"""
        # 检查常见API路径模式
        api_prefixes = [
            '/api/',
            '/devices/api/',
            '/configs/api/',
            '/monitoring/api/',
            '/alerts/api/',
            '/logs/api/',
            '/backups/api/',
            '/accounts/api/',
        ]
        for prefix in api_prefixes:
            if path.startswith(prefix):
                return True
        return False

    def _get_user_role(self, user):
        """获取用户角色"""
        return get_user_role(user)

    def _get_module_from_path(self, path):
        """从请求路径提取模块名"""
        # 例如: /devices/api/ -> devices
        parts = path.strip('/').split('/')
        if len(parts) >= 1:
            module = parts[0]
            # 映射到权限模块名
            module_map = {
                'devices': 'devices',
                'configs': 'configs',
                'monitoring': 'monitoring',
                'alerts': 'alerts',
                'logs': 'logs',
                'backups': 'backups',
                'accounts': 'accounts',
            }
            return module_map.get(module)
        return None

    def _has_permission(self, user, module, method):
        """检查用户是否有权限"""
        try:
            permissions = user.profile.permissions
        except (AttributeError, Exception):
            return False

        # 获取模块权限
        module_permissions = permissions.get(module, [])

        # 方法到权限的映射
        method_permission_map = {
            'GET': 'view',
            'POST': 'create',
            'PUT': 'edit',
            'PATCH': 'edit',
            'DELETE': 'delete',
        }

        required_permission = method_permission_map.get(method)
        if required_permission:
            return required_permission in module_permissions

        return False

    def _permission_denied_response(self, request, message):
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        if self._is_api_path(request.path) or is_ajax:
            return JsonResponse({'error': message}, status=403)
        return render(request, 'errors/permission_denied.html', {
            'permission': message,
        }, status=403)


def has_permission(user, module, action):
    """
    检查用户是否有特定权限的辅助函数

    Args:
        user: 用户对象
        module: 模块名 (devices, configs, etc.)
        action: 操作 (view, create, edit, delete)

    Returns:
        bool: 是否有权限
    """
    if not user.is_authenticated:
        return False

    try:
        profile = user.profile
    except (AttributeError, Exception):
        return False

    # 管理员拥有全部权限
    if profile.is_admin:
        return True

    # 只读用户只有view权限
    if profile.is_readonly:
        return action == 'view'

    # 普通用户根据permissions字段检查
    permissions = profile.permissions
    module_permissions = permissions.get(module, [])

    return action in module_permissions
