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
    list_display = ['name', 'content_type', 'codename']
    list_filter = ()
    search_fields = ['name', 'codename', 'content_type__app_label', 'content_type__model']
    ordering = ['content_type__app_label', 'content_type__model', 'codename']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('content_type')
