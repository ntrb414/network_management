from django.contrib import admin
from .models import Subnet, IPScanTask, IPAddress, AllocationLog


@admin.register(Subnet)
class SubnetAdmin(admin.ModelAdmin):
    list_display = ['cidr', 'name', 'vlan_id', 'source', 'is_active', 'usage_rate_display', 'created_at']
    list_filter = ['source', 'is_active']
    search_fields = ['cidr', 'name']
    ordering = ['cidr']
    readonly_fields = ['created_at', 'updated_at']

    def usage_rate_display(self, obj):
        return f"{obj.usage_rate}%"
    usage_rate_display.short_description = '使用率'


@admin.register(IPScanTask)
class IPScanTaskAdmin(admin.ModelAdmin):
    list_display = ['cidr', 'status', 'total_ips', 'scanned_ips', 'alive_ips', 'created_at']
    list_filter = ['status']
    search_fields = ['cidr']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'completed_at']


@admin.register(IPAddress)
class IPAddressAdmin(admin.ModelAdmin):
    list_display = ['ip_address', 'subnet', 'status', 'hostname', 'device', 'allocated_by', 'updated_at']
    list_filter = ['status', 'subnet']
    search_fields = ['ip_address', 'hostname', 'mac_address', 'description']
    raw_id_fields = ['device', 'allocated_by']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['ip_address']


@admin.register(AllocationLog)
class AllocationLogAdmin(admin.ModelAdmin):
    list_display = ['ip_address', 'action', 'hostname', 'performed_by', 'performed_at']
    list_filter = ['action']
    search_fields = ['ip_address', 'hostname', 'notes']
    raw_id_fields = ['performed_by']
    readonly_fields = ['performed_at']
    ordering = ['-performed_at']
