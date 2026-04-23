from django.urls import resolve, Resolver404


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


def is_admin_user(user):
    return get_user_role(user) == 'admin'


def user_can_access_module(user, module_key):
    role = get_user_role(user)
    if role == 'admin':
        return True

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

def has_module_permission(user, module_key, action):
    role = get_user_role(user)
    if role == 'admin':
        return True
    profile = getattr(user, 'profile', None)
    profile_permissions = getattr(profile, 'permissions', {}) or {}
    module_permissions = profile_permissions.get(module_key, [])
    return action in module_permissions

def is_readonly_user(user):
    return not has_module_permission(user, 'devices', 'edit')

def is_readonly_websocket_allowed(path):
    # Only allow read-only operations
    return 'terminal' not in path and 'config' not in path
