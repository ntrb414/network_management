# 权限检查装饰器
from functools import wraps
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.contrib.auth.decorators import login_required


def permission_required(permissions, logic='AND', redirect_to_login=True):
    # 装饰器：检查用户权限
    # 参数: permissions-权限字符串或列表, logic-AND/OR逻辑
    if isinstance(permissions, str):
        permissions = [permissions]
    
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # 检查用户是否已登录
            if not request.user.is_authenticated:
                if redirect_to_login:
                    return redirect(reverse('homepage:login'))
                return HttpResponseForbidden('Unauthorized')
            
            # 检查用户权限
            if has_permission(request.user, permissions, logic):
                return view_func(request, *args, **kwargs)
            
            # 无权限，返回权限拒绝页面
            permission_str = ', '.join(permissions) if permissions else 'view'
            return render(request, 'errors/permission_denied.html', {
                'permission': permission_str,
            }, status=403)
        
        return wrapper
    
    return decorator


def has_permission(user, permissions, logic='AND'):
    # 检查用户是否有指定权限
    # 参数: user-用户对象, permissions-权限列表, logic-AND/OR逻辑
    try:
        if user.profile.is_admin:
            return True
    except AttributeError:
        pass
    
    # 检查细粒度权限
    try:
        user_permissions = user.profile.permissions
    except AttributeError:
        user_permissions = {}
    
    # 检查每个权限
    permission_results = []
    for perm in permissions:
        if '.' in perm:
            app, action = perm.split('.', 1)
            # 检查用户是否有该应用的该操作权限
            has_perm = (
                app in user_permissions and
                action in user_permissions[app]
            )
            permission_results.append(has_perm)
        else:
            permission_results.append(False)
    
    # 根据逻辑返回结果
    if logic.upper() == 'AND':
        return all(permission_results)
    elif logic.upper() == 'OR':
        return any(permission_results)
    else:
        return False
