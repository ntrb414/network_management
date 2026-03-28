"""
权限检查装饰器

提供 permission_required 装饰器用于检查用户是否有权限访问视图。
支持多个权限的 AND/OR 逻辑检查。
"""

from functools import wraps
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.contrib.auth.decorators import login_required


def permission_required(permissions, logic='AND', redirect_to_login=True):
    """
    装饰器：检查用户是否有权限访问视图。
    
    参数：
        permissions (str or list): 权限字符串或列表，格式为 'app.action'，如 'devices.view'
        logic (str): 多个权限的检查逻辑，'AND' 表示需要所有权限，'OR' 表示只需一个权限
        redirect_to_login (bool): 未登录用户是否重定向到登录页
    
    返回：
        装饰器函数
    
    示例：
        @permission_required('devices.view')
        def my_view(request):
            pass
        
        @permission_required(['devices.view', 'devices.edit'], logic='OR')
        def my_view(request):
            pass
    """
    # 规范化权限为列表
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
    """
    检查用户是否有指定的权限。
    
    参数：
        user: Django User 对象
        permissions (list): 权限列表，格式为 'app.action'
        logic (str): 检查逻辑，'AND' 或 'OR'
    
    返回：
        bool: 用户是否有权限
    """
    # 管理员拥有所有权限
    try:
        if user.profile.is_admin:
            return True
    except AttributeError:
        pass
    
    # 只读用户无权限
    try:
        if user.profile.is_readonly:
            return False
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
