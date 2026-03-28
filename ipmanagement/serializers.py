"""
IPAM Serializers - DRF序列化器
"""
from rest_framework import serializers
from .models import Subnet, IPAddress, AllocationLog, IPScanTask


class SubnetSerializer(serializers.ModelSerializer):
    """子网序列化器"""
    total_ips = serializers.IntegerField(read_only=True)
    available_ips = serializers.IntegerField(read_only=True)
    used_ips = serializers.IntegerField(read_only=True)
    usage_rate = serializers.FloatField(read_only=True)

    class Meta:
        model = Subnet
        fields = [
            'id', 'cidr', 'name', 'vlan_id', 'description',
            'source', 'is_active', 'total_ips', 'available_ips',
            'used_ips', 'usage_rate', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class IPAddressSerializer(serializers.ModelSerializer):
    """IP地址序列化器"""
    subnet_cidr = serializers.CharField(source='subnet.cidr', read_only=True)
    device_name = serializers.CharField(source='device.name', read_only=True, allow_null=True)
    allocated_by_username = serializers.CharField(source='allocated_by.username', read_only=True, allow_null=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = IPAddress
        fields = [
            'id', 'ip_address', 'subnet', 'subnet_cidr', 'hostname',
            'mac_address', 'description', 'status', 'status_display',
            'device', 'device_name', 'allocated_at', 'allocated_by',
            'allocated_by_username', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class AllocationLogSerializer(serializers.ModelSerializer):
    """分配日志序列化器"""
    performed_by_username = serializers.CharField(source='performed_by.username', read_only=True, allow_null=True)
    action_display = serializers.CharField(source='get_action_display', read_only=True)

    class Meta:
        model = AllocationLog
        fields = [
            'id', 'ip_address', 'hostname', 'action', 'action_display',
            'old_value', 'new_value', 'performed_by', 'performed_by_username',
            'performed_at', 'notes'
        ]
        read_only_fields = ['performed_at']


class IPScanTaskSerializer(serializers.ModelSerializer):
    """扫描任务序列化器"""
    progress = serializers.SerializerMethodField()
    alive_hosts = serializers.SerializerMethodField()

    class Meta:
        model = IPScanTask
        fields = [
            'id', 'subnet', 'cidr', 'status', 'total_ips',
            'scanned_ips', 'alive_ips', 'progress', 'alive_hosts',
            'message', 'created_at', 'completed_at'
        ]

    def get_progress(self, obj):
        if obj.total_ips == 0:
            return 0
        return round(obj.scanned_ips / obj.total_ips * 100, 1)

    def get_alive_hosts(self, obj):
        import json
        if not obj.message:
            return []
        try:
            return json.loads(obj.message)
        except json.JSONDecodeError:
            return []
