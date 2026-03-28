from django.contrib import admin
from .models import SystemLog


@admin.register(SystemLog)
class SystemLogAdmin(admin.ModelAdmin):
    """系统日志管理"""
    list_display = ['id', 'log_type', 'device', 'user', 'message', 'timestamp']
    list_filter = ['log_type', 'timestamp']
    search_fields = ['message', 'details']
    readonly_fields = ['timestamp']
    date_hierarchy = 'timestamp'
    ordering = ['-timestamp']

    fieldsets = (
        ('基本信息', {
            'fields': ('log_type', 'device', 'user', 'message')
        }),
        ('详细信息', {
            'fields': ('details', 'timestamp'),
            'classes': ('collapse',)
        }),
    )
