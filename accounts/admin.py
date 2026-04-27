from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.utils.html import format_html

from .models import UserProfile


admin.site.unregister(User)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'staff_status_badge')
    list_filter = ()

    @admin.display(description='工作人员状态', ordering='is_staff')
    def staff_status_badge(self, obj):
        if obj.is_staff:
            return format_html('<span class="admin-status-badge yes">是</span>')
        return format_html('<span class="admin-status-badge no">否</span>')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role']
    list_filter = ['role']
    search_fields = ['user__username']


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ['formatted_name', 'formatted_content_type', 'codename', 'permission_badge']
    list_filter = ()
    search_fields = ['name', 'codename', 'content_type__app_label', 'content_type__model']
    ordering = ['content_type__app_label', 'content_type__model', 'codename']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('content_type')

    @admin.display(description='权限名称', ordering='name')
    def formatted_name(self, obj):
        # 将英文权限名称转换为更友好的显示
        name_mapping = {
            'Can add': '添加',
            'Can change': '修改',
            'Can delete': '删除',
            'Can view': '查看',
        }
        display_name = obj.name
        for eng, chn in name_mapping.items():
            if display_name.startswith(eng):
                display_name = display_name.replace(eng, chn)
                break
        return format_html('<span class="permission-name">{}</span>', display_name)

    @admin.display(description='内容类型', ordering='content_type')
    def formatted_content_type(self, obj):
        # 格式化内容类型显示
        app_label = obj.content_type.app_label
        model = obj.content_type.model

        # 应用名称映射
        app_names = {
            'accounts': '账户',
            'admin': '管理',
            'alerts': '告警',
            'auth': '认证',
            'backups': '备份',
            'configs': '配置',
            'devices': '设备',
            'django_celery_beat': '定时任务',
            'ipmanagement': 'IP管理',
            'logs': '日志',
            'monitoring': '监控',
            'sessions': '会话',
        }

        # 模型名称映射
        model_names = {
            'user': '用户',
            'group': '用户组',
            'permission': '权限',
            'logentry': '日志记录',
            'userprofile': '用户配置',
            'device': '设备',
            'devicetype': '设备类型',
            'interfacemonitor': '接口监控',
            'metric': '指标',
            'alert': '告警',
            'alertrule': '告警规则',
            'subnet': '子网',
            'ipaddress': 'IP地址',
            'backupschedule': '备份计划',
            'backuphistory': '备份历史',
            'configbackup': '配置备份',
            'crontabschedule': 'Crontab计划',
            'intervalschedule': '间隔计划',
            'periodictask': '定时任务',
            'solarschedule': '太阳计划',
            'clockedschedule': '定点计划',
        }

        app_display = app_names.get(app_label, app_label)
        model_display = model_names.get(model, model)

        return format_html(
            '<span style="display:inline-flex;align-items:center;gap:0.5rem;">'
            '<span style="padding:0.125rem 0.5rem;background:#f3f4f6;border-radius:4px;'
            'font-size:0.75rem;color:#6b7280;font-weight:500;">{}</span>'
            '<span style="color:#374151;">{}</span></span>',
            app_display, model_display
        )

    @admin.display(description='权限类型')
    def permission_badge(self, obj):
        # 根据权限类型返回不同颜色的标签
        action_colors = {
            'add': ('#10b981', '#d1fae5', '添加'),
            'change': ('#f59e0b', '#fef3c7', '修改'),
            'delete': ('#ef4444', '#fee2e2', '删除'),
            'view': ('#3b82f6', '#dbeafe', '查看'),
        }

        action = obj.codename.split('_')[0] if '_' in obj.codename else 'other'
        color, bg, label = action_colors.get(action, ('#6b7280', '#f3f4f6', '其他'))

        return format_html(
            '<span style="display:inline-flex;align-items:center;gap:0.375rem;padding:0.25rem 0.75rem;'
            'border-radius:999px;font-size:0.75rem;font-weight:600;background:{};color:{};white-space:nowrap;">'
            '<span style="width:6px;height:6px;border-radius:50%;background:{};"></span>{}</span>',
            bg, color, color, label
        )
