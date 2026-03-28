from django.views.generic import TemplateView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.http import HttpResponseNotFound
from django.views.decorators.csrf import csrf_exempt

from accounts.permissions import user_can_access_module


class HomepageView(LoginRequiredMixin, TemplateView):
    """Display the homepage with available feature modules."""
    
    template_name = 'homepage/homepage.html'
    login_url = 'homepage:login'
    
    # Define all 8 functional modules with their metadata
    ALL_MODULES = [
        {
            'key': 'devices',
            'name': '设备管理',
            'description': '管理路由器、交换机、AP等网络设备，查看设备状态与详情',
            'url': '/devices/',
            'permission': 'devices.view_device',
        },
        {
            'key': 'configs',
            'name': '配置管理',
            'description': '下发、审批和回滚设备配置，支持批量操作',
            'url': '/configs/',
            'permission': 'configs.view_config',
        },
        {
            'key': 'monitoring',
            'name': '性能监控',
            'description': '实时监控 CPU、内存、流量等性能指标',
            'url': '/monitoring/',
            'permission': 'monitoring.view_monitoring',
        },
        {
            'key': 'alerts',
            'name': '告警管理',
            'description': '查看和处理设备离线、故障、指标异常等告警',
            'url': '/alerts/',
            'permission': 'alerts.view_alert',
        },
        {
            'key': 'logs',
            'name': '系统日志',
            'description': '查看操作日志、设备日志和系统事件记录',
            'url': '/logs/',
            'permission': 'logs.view_log',
        },
        {
            'key': 'backups',
            'name': '配置备份',
            'description': '自动备份设备配置，支持版本对比与恢复',
            'url': '/backups/',
            'permission': 'backups.view_backup',
        },
        {
            'key': 'accounts',
            'name': '账户管理',
            'description': '管理系统用户账户、角色与访问权限',
            'url': '/accounts/',
            'permission': 'accounts.view_user',
        },
    ]
    
    def get_context_data(self, **kwargs):
        """Return context with available modules and dashboard stats."""
        context = super().get_context_data(**kwargs)
        context['modules'] = self.get_available_modules()
        context['stats'] = self.get_dashboard_stats()
        return context

    def get_available_modules(self):
        """Return all modules with optional record counts."""
        modules = []
        count_map = self._get_module_counts()
        for m in self.ALL_MODULES:
            if not user_can_access_module(self.request.user, m['key']):
                continue
            entry = dict(m)
            entry['count'] = count_map.get(m['key'])
            modules.append(entry)
        return modules

    def _get_module_counts(self):
        counts = {}
        try:
            from devices.models import Device
            counts['devices'] = Device.objects.count()
        except Exception:
            pass
        try:
            from configs.models import Config
            counts['configs'] = Config.objects.count()
        except Exception:
            pass
        try:
            from alerts.models import Alert
            counts['alerts'] = Alert.objects.filter(status='active').count()
        except Exception:
            pass
        try:
            from backups.models import ConfigBackup
            counts['backups'] = ConfigBackup.objects.count()
        except Exception:
            pass
        return counts

    def get_dashboard_stats(self):
        stats = {
            'total_devices': 0,
            'online_devices': 0,
            'active_alerts': 0,
            'total_backups': 0,
            'device_type_counts': [],
            'recent_alerts': [],
        }
        try:
            from devices.models import Device
            stats['total_devices'] = Device.objects.count()
            stats['online_devices'] = Device.objects.filter(status='online').count()
            type_labels = dict(Device.DEVICE_TYPES)
            for dtype, label in Device.DEVICE_TYPES:
                c = Device.objects.filter(device_type=dtype).count()
                if c:
                    stats['device_type_counts'].append({'label': label, 'count': c})
        except Exception:
            pass
        try:
            from alerts.models import Alert
            stats['active_alerts'] = Alert.objects.filter(status='active').count()
            stats['recent_alerts'] = list(
                Alert.objects.filter(status='active')
                .select_related('device')
                .order_by('-created_at')[:5]
            )
        except Exception:
            pass
        try:
            from backups.models import ConfigBackup
            stats['total_backups'] = ConfigBackup.objects.count()
        except Exception:
            pass
        return stats


class LoginView(TemplateView):
    """Display the login page and handle user authentication."""
    
    template_name = 'homepage/login.html'
    
    def get(self, request, *args, **kwargs):
        """Display login form."""
        # If user is already authenticated, redirect to homepage
        if request.user.is_authenticated:
            return redirect('homepage:homepage')
        return super().get(request, *args, **kwargs)
    
    def post(self, request, *args, **kwargs):
        """Handle login form submission."""
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        
        # Validate input
        if not username or not password:
            context = self.get_context_data()
            context['error'] = 'Username and password are required'
            return self.render_to_response(context)
        
        # Authenticate user
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('homepage:homepage')
        else:
            context = self.get_context_data()
            context['error'] = 'Invalid username or password'
            return self.render_to_response(context)


@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(require_http_methods(["GET", "POST"]), name='dispatch')
class LogoutView(View):
    """Handle user logout and session clearing."""
    
    def get(self, request, *args, **kwargs):
        """Handle logout via GET request."""
        logout(request)
        return redirect('homepage:login')
    
    def post(self, request, *args, **kwargs):
        """Handle logout via POST request."""
        logout(request)
        return redirect('homepage:login')


def permission_denied_view(request, exception=None):
    """Handle 403 permission denied errors."""
    permission = request.GET.get('permission', 'view')
    return render(request, 'errors/permission_denied.html', {
        'permission': permission,
    }, status=403)


def page_not_found_view(request, exception=None):
    """Handle 404 page not found errors."""
    return render(request, 'errors/404.html', {
        'request_path': request.path,
    }, status=404)

