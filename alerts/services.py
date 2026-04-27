"""
告警服务

提供告警生成、通知、管理等功能。
"""

import logging
from typing import List, Dict, Any, Optional
from django.utils import timezone

logger = logging.getLogger(__name__)


class AlertService:
    """告警服务类"""

    def create_alert(
        self,
        device,
        alert_type: str,
        severity: str,
        message: str
    ) -> 'Alert':
        """
        创建告警

        Args:
            device: 设备对象
            alert_type: 告警类型
            severity: 严重程度
            message: 告警消息

        Returns:
            创建的Alert对象

        """
        from alerts.models import Alert

        alert = Alert.objects.create(
            device=device,
            alert_type=alert_type,
            severity=severity,
            message=message,
            status='active',
        )

        # 触发通知
        self.notify_users(alert)

        # 记录设备日志
        self._record_alert_log(alert)

        return alert

    def create_device_offline_alert(self, device) -> 'Alert':
        """
        创建设备离线告警

        如果该设备已存在未解决的离线告警（active 或 acknowledged），
        则不再重复创建，直接返回已存在的告警。

        Args:
            device: 设备对象

        Returns:
            告警对象
        """
        from alerts.models import Alert

        existing = Alert.objects.filter(
            device=device,
            alert_type='device_offline',
            status__in=['active', 'acknowledged'],
        ).first()
        if existing:
            return existing

        return self.create_alert(
            device=device,
            alert_type='device_offline',
            severity='critical',
            message=f"设备 {device.name} ({device.ip_address}) 已离线",
        )

    def create_device_fault_alert(self, device) -> 'Alert':
        """
        创建设备故障告警

        如果该设备已存在未解决的故障告警（active 或 acknowledged），
        则不再重复创建，直接返回已存在的告警。

        Args:
            device: 设备对象

        Returns:
            告警对象
        """
        from alerts.models import Alert

        existing = Alert.objects.filter(
            device=device,
            alert_type='device_fault',
            status__in=['active', 'acknowledged'],
        ).first()
        if existing:
            return existing

        return self.create_alert(
            device=device,
            alert_type='device_fault',
            severity='critical',
            message=f"设备 {device.name} ({device.ip_address}) 发生故障",
        )

    def create_config_failed_alert(self, device, error_message: str) -> 'Alert':
        """
        创建配置失败告警

        Args:
            device: 设备对象
            error_message: 错误消息

        Returns:
            告警对象
        """
        return self.create_alert(
            device=device,
            alert_type='config_failed',
            severity='important',
            message=f"设备 {device.name} 配置下发失败: {error_message}",
        )

    def create_metric_abnormal_alert(
        self,
        device,
        metric_type: str,
        value: float,
        threshold: float
    ) -> 'Alert':
        """
        创建指标异常告警

        Args:
            device: 设备对象
            metric_type: 指标类型
            value: 当前值
            threshold: 阈值

        Returns:
            告警对象
        """
        severity = 'important' if value < 90 else 'critical'

        return self.create_alert(
            device=device,
            alert_type='metric_abnormal',
            severity=severity,
            message=f"设备 {device.name} {metric_type} 超过阈值: {value}% > {threshold}%",
        )

    def create_topology_changed_alert(self, change_info: Dict[str, Any]) -> Optional['Alert']:
        """
        创建拓扑变更告警

        Args:
            change_info: 变更信息

        Returns:
            告警对象，如果没有关联设备则返回None
        """
        from devices.models import Device

        # 尝试获取关联设备
        device_id = change_info.get('device_id')
        if not device_id:
            return None

        try:
            device = Device.objects.get(id=device_id)
        except Device.DoesNotExist:
            return None

        change_type = change_info.get('change_type', 'unknown')
        description = change_info.get('description', '')

        return self.create_alert(
            device=device,
            alert_type='topology_changed',
            severity='normal',
            message=f"拓扑变更: {change_type} - {description}",
        )

    def notify_users(self, alert) -> bool:
        """
        通知用户

        Args:
            alert: 告警对象

        Returns:
            是否发送成功
        """
        # 实现系统内弹窗通知
        # 可以通过WebSocket或轮询实现
        # 这里记录日志表示通知已发送

        logger.info(
            f"告警通知已发送: {alert.get_severity_display()} - {alert.message}"
        )

        # 可以在此实现:
        # 1. 邮件通知
        # 2. 短信通知
        # 3. WebSocket推送

        return True

    def _record_alert_log(self, alert) -> None:
        #alert: 告警对象
        try:
            from logs.services import LogService
            service = LogService()
            service.collect_device_log(
                device=alert.device,
                log_type='alert',
                message=alert.message,
                details={
                    'alert_id': alert.id,
                    'alert_type': alert.alert_type,
                    'severity': alert.severity,
                }
            )
        except Exception as e:
            logger.warning(f"记录告警日志失败: {e}")

    def acknowledge_alert(self, alert, user) -> bool:
        """
        确认告警

        Args:
            alert: 告警对象
            user: 确认用户

        Returns:
            是否成功
        """
        if alert.status != 'active':
            return False

        alert.status = 'acknowledged'
        alert.handled_by = user
        alert.handled_at = timezone.now()
        alert.save()

        return True

    def ignore_alert(self, alert, user) -> bool:
        """
        忽略告警

        Args:
            alert: 告警对象
            user: 忽略用户

        Returns:
            是否成功
        """
        if alert.status != 'active':
            return False

        alert.status = 'ignored'
        alert.handled_by = user
        alert.handled_at = timezone.now()
        alert.save()

        return True

    def acknowledge_all_active_alerts(self, user) -> int:
        """确认全部活动告警，返回处理数量。"""
        alerts = self.get_active_alerts()
        handled_count = 0

        for alert in alerts:
            if self.acknowledge_alert(alert, user):
                handled_count += 1

        return handled_count

    def delete_alerts(self, alert_ids: List[int]) -> int:
        """删除指定告警，返回删除数量。"""
        if not alert_ids:
            return 0

        from alerts.models import Alert

        queryset = Alert.objects.filter(id__in=alert_ids)
        deleted_count = queryset.count()
        queryset.delete()
        return deleted_count

    def delete_all_alerts(self) -> int:
        """删除全部告警，返回删除数量。"""
        from alerts.models import Alert

        queryset = Alert.objects.all()
        deleted_count = queryset.count()
        queryset.delete()
        return deleted_count

    def get_active_alerts(self) -> List:
        """
        获取活动告警列表

        Returns:
            活动告警查询集
        """
        from alerts.models import Alert

        return Alert.objects.filter(status='active').order_by('-created_at')

    def get_alerts_by_device(self, device) -> List:
        """
        获取设备的告警列表

        Args:
            device: 设备对象

        Returns:
            告警查询集
        """
        from alerts.models import Alert

        return Alert.objects.filter(device=device).order_by('-created_at')

    def get_alert_statistics(self, days: int = 7) -> Dict[str, Any]:
        """
        获取告警统计信息

        Args:
            days: 统计天数

        Returns:
            统计信息字典
        """
        from alerts.models import Alert
        from django.db.models import Count
        from datetime import timedelta

        start_date = timezone.now() - timedelta(days=days)

        # 按类型统计
        by_type = Alert.objects.filter(
            created_at__gte=start_date
        ).values('alert_type').annotate(
            count=Count('id')
        ).order_by('-count')

        # 按严重程度统计
        by_severity = Alert.objects.filter(
            created_at__gte=start_date
        ).values('severity').annotate(
            count=Count('id')
        ).order_by('-count')

        # 按状态统计
        by_status = Alert.objects.filter(
            created_at__gte=start_date
        ).values('status').annotate(
            count=Count('id')
        ).order_by('-count')

        total = Alert.objects.filter(created_at__gte=start_date).count()

        return {
            'total': total,
            'by_type': list(by_type),
            'by_severity': list(by_severity),
            'by_status': list(by_status),
        }

    def cleanup_old_alerts(self, days: int = 30):
        """
        清理已处理的老旧告警

        Args:
            days: 保留天数
        """
        from alerts.models import Alert
        from datetime import timedelta

        cutoff_date = timezone.now() - timedelta(days=days)

        deleted_count = Alert.objects.filter(
            created_at__lt=cutoff_date,
            status__in=['acknowledged', 'ignored']
        ).delete()[0]

        return {
            'success': True,
            'deleted_count': deleted_count,
        }
