from django.urls import resolve, Resolver404


READONLY_ALLOWED_VIEWS = {
    'homepage:homepage': {'GET'},
    'homepage:logout': {'GET', 'POST'},
    'devices:device_list': {'GET'},
    'devices:device_detail': {'GET'},
    'devices:device_config': {'GET'},
    'devices:device_list_api': {'GET'},
    'devices:device_detail_api': {'GET'},
    'devices:device_statistics_api': {'GET'},
    'devices:device_config_api': {'GET'},
    'devices:device_ping_api': {'POST'},
    'devices:device_config_realtime_api': {'POST'},
}

READONLY_ALLOWED_WEBSOCKET_PREFIXES = [
    '/devices/webssh/',
]


def get_user_role(user):
    if not getattr(user, 'is_authenticated', False):
        return 'anonymous'

    if getattr(user, 'is_superuser', False):
        return 'admin'

    profile = getattr(user, 'profile', None)
    if profile and getattr(profile, 'is_admin', False):
        return 'admin'
    if profile and getattr(profile, 'role', None):
        return profile.role
    return 'user'


def is_readonly_user(user):
    return get_user_role(user) == 'readonly'


def is_admin_user(user):
    return get_user_role(user) == 'admin'


def user_can_access_module(user, module_key):
    role = get_user_role(user)
    if role == 'admin':
        return True
    if role == 'readonly':
        return module_key == 'devices'

    profile = getattr(user, 'profile', None)
    profile_permissions = getattr(profile, 'permissions', {}) or {}
    module_permissions = profile_permissions.get(module_key, [])
    if 'view' in module_permissions:
        return True

    permission_map = {
        'devices': 'devices.view_device',
        'configs': 'configs.view_config',
        'monitoring': 'monitoring.view_monitoring',
        'alerts': 'alerts.view_alert',
        'logs': 'logs.view_log',
        'backups': 'backups.view_backup',
        'accounts': 'accounts.view_user',
    }
    django_permission = permission_map.get(module_key)
    if django_permission:
        return user.has_perm(django_permission)

    return False


def is_readonly_request_allowed(request):
    if request.method == 'OPTIONS':
        return True

    try:
        match = resolve(request.path_info)
    except Resolver404:
        return False

    allowed_methods = READONLY_ALLOWED_VIEWS.get(match.view_name)
    if not allowed_methods:
        return False

    return request.method in allowed_methods


def is_readonly_websocket_allowed(path):
    return any(path.startswith(prefix) for prefix in READONLY_ALLOWED_WEBSOCKET_PREFIXES)
