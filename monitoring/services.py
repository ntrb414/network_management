"""
性能监控服务

提供监控数据采集、存储、查询等功能。
"""

import json
import logging
import re
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from django_redis import get_redis_connection
from django.utils import timezone

logger = logging.getLogger(__name__)


class MonitoringService:
    """性能监控服务类"""

    # 监控指标阈值配置
    THRESHOLDS = {
        'packet_loss': 5.0, # 丢包率阈值 (%)
        'interface_in_drops': 100,  # 入向丢包阈值 (个/分钟)
        'interface_out_drops': 100, # 出向丢包阈值 (个/分钟)
        'interface_bandwidth': 80.0, # 带宽利用率阈值 (%)
    }

    # 实例变量保存上次采集的接口流量数据用于计算Mbps (避免类变量共享导致并发问题)
    _interface_traffic_cache = None

    def __init__(self):
        
        self._interface_traffic_cache = {}

    def _default_metrics_payload(self) -> Dict[str, Any]:
        return {
            'traffic': [],
            'packet_loss': None,
            'connections': None,
            'interfaces': [],
            'ospf_neighbors': [],
            'cpu_usage': None,
            'memory_usage': None,
        }

    def _merge_interfaces(
        self,
        previous_interfaces: Optional[List[Dict[str, Any]]],
        current_interfaces: Optional[List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}

        for interface in previous_interfaces or []:
            if not isinstance(interface, dict):
                continue
            name = interface.get('name')
            if not name:
                continue
            merged[name] = dict(interface)

        for interface in current_interfaces or []:
            if not isinstance(interface, dict):
                continue
            name = interface.get('name')
            if not name:
                continue
            existing = merged.get(name, {})
            existing.update(interface)
            merged[name] = existing

        return list(merged.values())

    def _merge_metrics_payload(self, previous_metrics: Any, current_metrics: Any) -> Dict[str, Any]:
        previous = previous_metrics if isinstance(previous_metrics, dict) else {}
        current = current_metrics if isinstance(current_metrics, dict) else {}
        partial_update = bool(current.get('_partial_update'))

        merged = self._default_metrics_payload()

        if partial_update:
            merged['interfaces'] = self._merge_interfaces(
                previous.get('interfaces'),
                current.get('interfaces'),
            )
            merged['traffic'] = current.get('traffic') or previous.get('traffic') or []
            merged['ospf_neighbors'] = current.get('ospf_neighbors') or previous.get('ospf_neighbors') or []

            for scalar_key in ('packet_loss', 'connections', 'cpu_usage', 'memory_usage'):
                scalar_value = current.get(scalar_key)
                if scalar_value is None:
                    scalar_value = previous.get(scalar_key)
                merged[scalar_key] = scalar_value

            extra_sources = (previous, current)
        else:
            merged['interfaces'] = list(current.get('interfaces') or [])
            merged['traffic'] = list(current.get('traffic') or [])
            merged['ospf_neighbors'] = list(current.get('ospf_neighbors') or [])

            for scalar_key in ('packet_loss', 'connections', 'cpu_usage', 'memory_usage'):
                merged[scalar_key] = current.get(scalar_key)

            extra_sources = (current,)

        # 保留非标准字段，避免兼容性回退。
        for source in extra_sources:
            for key, value in source.items():
                if key in merged or key.startswith('_'):
                    continue
                if value is not None:
                    merged[key] = value

        return merged

    def _get_redis_connection_safe(self):
        """在测试环境下允许无 Redis 后端运行。"""
        try:
            return get_redis_connection("default")
        except Exception as exc:
            logger.debug(f"Redis连接不可用，跳过Redis读写: {exc}")
            return None

    def collect_metrics(self, device) -> Dict[str, Any]:
        """
        采集设备性能指标，返监控指标数据
        """
        metrics = {}

        try:
            # 根据设备类型选择采集方式
            if device.device_type == 'ap':
                # AP设备 - 实时采集
                metrics = self._collect_ap_metrics(device)
            else:
                # 其他设备 - 标准采集
                metrics = self._collect_standard_metrics(device)

        except Exception as e:
            logger.error(f"采集设备 {device.ip_address} 监控数据失败: {e}")

        return metrics

    def _collect_standard_metrics(self, device) -> Dict[str, Any]:
        """
        采集标准设备监控指标，返监控指标数据
        """
        metrics = {
            'traffic': [],
            'packet_loss': None,
            'connections': None,
        }

        # 尝试通过gNMI采集
        try:
            gnmi_metrics = self._collect_via_gnmi(device)
            metrics.update(gnmi_metrics)
        except Exception as e:
            logger.warning(f"gNMI采集失败: {e}")

        return metrics

    def _collect_ap_metrics(self, device) -> Dict[str, Any]:
        """
        采集AP设备监控指标

        Args:
            device: 设备对象

        Returns:
            监控指标数据
        """
        # AP设备需要更频繁的采集
        # 实际实现需要通过SSH或gNMI获取
        metrics = {
            'traffic': [],
            'packet_loss': None,
            'connections': None,
        }

        try:
            gnmi_metrics = self._collect_via_gnmi(device)
            metrics.update(gnmi_metrics)
        except Exception as e:
            logger.warning(f"gNMI采集失败: {e}")

        return metrics


    def _collect_via_gnmi(self, device) -> Dict[str, Any]:
        """
        通过 gNMI 采集设备监控指标
        """
        metrics = {
            'traffic': [],
            'packet_loss': None,
            'connections': None,
            'interfaces': [],
            'ospf_neighbors': [],
            'cpu_usage': None,
            'memory_usage': None,
        }
        
        try:
            from pygnmi.client import gNMIclient
            from monitoring.gnmi_parser import parse_gnmi_notification, format_metrics_from_map
        except ImportError:
            logger.warning("pygnmi未安装或解析器缺失，无法通过gNMI采集")
            return metrics

        if not device.ip_address or not device.ssh_username or not device.ssh_password:
            logger.warning(f"设备 {device.name} gNMI配置不完整，跳过采集")
            return metrics
        
        try:
            with gNMIclient(
                target=(str(device.ip_address), getattr(device, 'gnmi_port', 50000)),
                username=device.ssh_username,
                password=device.ssh_password,
                insecure=getattr(device, 'gnmi_insecure', True)
            ) as gc:
                result = gc.get(path=["/interfaces/interface/state"])
                interface_map: Dict[str, Dict[str, Any]] = {}

                notifications = []
                if isinstance(result, dict):
                    notifications = result.get('notification') or result.get('notifications') or []

                for notification in notifications:
                    if not isinstance(notification, dict):
                        continue
                    parse_gnmi_notification(notification, interface_map)

                parsed_metrics = format_metrics_from_map(interface_map)
                metrics.update(parsed_metrics)
                
        except Exception as e:
            logger.warning(f"gNMI采集异常，返回空实时数据: {e}")
        
        return metrics

    def _cleanup_traffic_cache(self):
        """清理过期的流量缓存数据"""
        try:
            from django.utils import timezone
            current_time = timezone.now()
            expired_keys = []

            for device_key, interfaces in self._interface_traffic_cache.items():
                # 检查该设备所有接口的最后更新时间
                max_age = timedelta(minutes=30)
                is_expired = True

                for idx, data in interfaces.items():
                    last_timestamp = data.get('timestamp', current_time)
                    # 确保时间戳是 aware datetime
                    if timezone.is_naive(last_timestamp):
                        from django.utils.timezone import make_aware
                        last_timestamp = make_aware(last_timestamp)
                    if current_time - last_timestamp < max_age:
                        is_expired = False
                        break

                if is_expired:
                    expired_keys.append(device_key)

            for key in expired_keys:
                del self._interface_traffic_cache[key]

        except Exception as e:
            logger.debug(f"清理流量缓存失败: {e}")

    def _get_connections_via_ssh(self, device) -> Optional[int]:
        """
        通过SSH获取华为设备TCP连接数

        Args:
            device: 设备对象

        Returns:
            连接数，失败返回None
        """
        try:
            import paramiko
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                hostname=str(device.ip_address),
                port=device.ssh_port or 22,
                username=device.ssh_username,
                password=device.ssh_password,
                timeout=10,
                # 兼容旧设备：启用 ssh-rsa 主机密钥算法
                disabled_algorithms={'pubkeys': ['rsa-sha2-256', 'rsa-sha2-512']},
            )
            stdin, stdout, stderr = client.exec_command('display tcp statistics')
            output = stdout.read().decode('utf-8', errors='ignore')
            client.close()

            # 解析华为 display tcp statistics 输出
            # 格式: "Established: 12"
            import re
            match = re.search(r'Established\s*:\s*(\d+)', output, re.IGNORECASE)
            if match:
                return int(match.group(1))
            # 备用：统计 ESTABLISHED 行数
            established = len(re.findall(r'ESTABLISHED', output, re.IGNORECASE))
            return established if established > 0 else None
        except Exception as e:
            logger.debug(f"SSH连接数采集失败 [{device.name}]: {e}")
            return None

    def store_metrics(self, device, metrics: Dict[str, Any]) -> int:
        """
        存储监控数据到 Redis（TTL 10 分钟）

        Args:
            device: 设备对象
            metrics: 监控指标数据

        Returns:
            存储的记录数

        """
        latest_snapshot = self.get_latest_metrics_from_redis(device.id)
        previous_metrics = latest_snapshot.get('metrics', {}) if latest_snapshot else {}
        metrics = self._merge_metrics_payload(previous_metrics, metrics)

        stored_count = 0

        # 计算记录数（与旧逻辑保持一致，用于任务返回值）
        for traffic in metrics.get('traffic', []):
            if traffic.get('in_octets', 0) > 0:
                stored_count += 1
            if traffic.get('out_octets', 0) > 0:
                stored_count += 1

        if metrics.get('packet_loss') is not None:
            stored_count += 1

        if metrics.get('connections') is not None:
            stored_count += 1

        if metrics.get('cpu_usage') is not None:
            stored_count += 1

        if metrics.get('memory_usage') is not None:
            stored_count += 1

        for interface in metrics.get('interfaces', []):
            stored_count += 1
            if interface.get('in_mbps') is not None:
                stored_count += 1
            if interface.get('out_mbps') is not None:
                stored_count += 1
            if interface.get('in_drop_rate') is not None:
                stored_count += 1
            if interface.get('out_drop_rate') is not None:
                stored_count += 1

        for neighbor in metrics.get('ospf_neighbors', []):
            stored_count += 1

        # 写入 Redis：每个设备一个 List，保留最近 100 条，TTL 600 秒
        redis_conn = self._get_redis_connection_safe()
        if redis_conn is None:
            return stored_count
        key = f"metrics:device:{device.id}"
        payload = json.dumps({
            "timestamp": timezone.now().isoformat(),
            "metrics": metrics,
            "stored_count": stored_count,
        }, default=str)
        redis_conn.lpush(key, payload)
        redis_conn.ltrim(key, 0, 99)
        redis_conn.expire(key, 600)

        return stored_count

    def _decode_metrics_snapshot(self, raw_data: Any, device_id: int) -> Optional[Dict[str, Any]]:
        """解析 Redis 中存储的监控快照。"""
        if raw_data is None:
            return None

        try:
            if isinstance(raw_data, bytes):
                raw_data = raw_data.decode('utf-8')
            data = json.loads(raw_data)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
            logger.error(f"解析设备 {device_id} 的Redis监控数据失败: {exc}")
            return None

        timestamp = data.get('timestamp')
        timestamp_dt = None
        if timestamp:
            try:
                timestamp_dt = datetime.fromisoformat(timestamp)
            except ValueError:
                logger.debug(f"设备 {device_id} 的时间戳格式不合法: {timestamp}")

        return {
            'timestamp': timestamp,
            'timestamp_dt': timestamp_dt,
            'metrics': data.get('metrics', {}),
            'stored_count': data.get('stored_count', 0),
        }

    def get_latest_metrics_from_redis(self, device_id: int) -> Optional[Dict[str, Any]]:
        """
        从Redis获取设备最新监控数据。

        Args:
            device_id: 设备ID

        Returns:
            包含 timestamp/metrics/stored_count 的字典；无数据返回 None
        """
        redis_conn = self._get_redis_connection_safe()
        if redis_conn is None:
            return None

        key = f"metrics:device:{device_id}"
        raw_data = redis_conn.lindex(key, 0)
        return self._decode_metrics_snapshot(raw_data, device_id)

    def get_device_snapshots_from_redis(
        self,
        device_id: int,
        duration: Optional[timedelta] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取设备在时间窗口内的监控快照（按时间倒序）。

        Args:
            device_id: 设备ID
            duration: 时间窗口，None 表示不过滤
            limit: 返回条数上限，None 表示全部

        Returns:
            快照列表（最新在前）
        """
        redis_conn = self._get_redis_connection_safe()
        if redis_conn is None:
            return []

        key = f"metrics:device:{device_id}"
        end_index = -1 if limit is None else max(0, limit - 1)
        raw_items = redis_conn.lrange(key, 0, end_index)

        start_time = timezone.now() - duration if duration else None
        snapshots = []
        for raw in raw_items:
            snapshot = self._decode_metrics_snapshot(raw, device_id)
            if snapshot is None:
                continue

            snapshot_ts = snapshot.get('timestamp_dt')
            if start_time and snapshot_ts:
                if timezone.is_naive(snapshot_ts):
                    snapshot_ts = timezone.make_aware(snapshot_ts)
                if snapshot_ts < start_time:
                    continue

            snapshots.append(snapshot)

        return snapshots

    def flatten_snapshots_to_metric_rows(self, snapshots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        将 Redis 快照扁平化为统一监控行结构。

        Returns:
            [{metric_type, metric_name, value, unit, timestamp}, ...]
        """
        rows: List[Dict[str, Any]] = []

        for snapshot in snapshots:
            ts = snapshot.get('timestamp')
            metrics = snapshot.get('metrics', {}) or {}

            for traffic in metrics.get('traffic', []):
                iface = traffic.get('interface', 'unknown')
                in_octets = traffic.get('in_octets')
                out_octets = traffic.get('out_octets')

                if in_octets is not None:
                    rows.append({
                        'metric_type': 'traffic',
                        'metric_name': f'{iface}_in',
                        'value': in_octets,
                        'unit': 'octets',
                        'timestamp': ts,
                    })
                if out_octets is not None:
                    rows.append({
                        'metric_type': 'traffic',
                        'metric_name': f'{iface}_out',
                        'value': out_octets,
                        'unit': 'octets',
                        'timestamp': ts,
                    })

            for interface in metrics.get('interfaces', []):
                iface_name = interface.get('name', 'unknown')

                status = interface.get('status')
                if status is not None:
                    rows.append({
                        'metric_type': 'interface_status',
                        'metric_name': f'{iface_name}_status',
                        'value': status,
                        'unit': '',
                        'timestamp': ts,
                    })

                in_mbps = interface.get('in_mbps')
                if in_mbps is not None:
                    rows.append({
                        'metric_type': 'interface_in_traffic',
                        'metric_name': f'{iface_name}_in_mbps',
                        'value': in_mbps,
                        'unit': 'Mbps',
                        'timestamp': ts,
                    })

                out_mbps = interface.get('out_mbps')
                if out_mbps is not None:
                    rows.append({
                        'metric_type': 'interface_out_traffic',
                        'metric_name': f'{iface_name}_out_mbps',
                        'value': out_mbps,
                        'unit': 'Mbps',
                        'timestamp': ts,
                    })

                in_drops = interface.get('in_drop_rate')
                if in_drops is not None:
                    rows.append({
                        'metric_type': 'interface_in_drops',
                        'metric_name': f'{iface_name}_in_drops',
                        'value': in_drops,
                        'unit': 'pkt/min',
                        'timestamp': ts,
                    })

                out_drops = interface.get('out_drop_rate')
                if out_drops is not None:
                    rows.append({
                        'metric_type': 'interface_out_drops',
                        'metric_name': f'{iface_name}_out_drops',
                        'value': out_drops,
                        'unit': 'pkt/min',
                        'timestamp': ts,
                    })

            packet_loss = metrics.get('packet_loss')
            if packet_loss is not None:
                rows.append({
                    'metric_type': 'packet_loss',
                    'metric_name': 'packet_loss_rate',
                    'value': packet_loss,
                    'unit': '%',
                    'timestamp': ts,
                })

            connections = metrics.get('connections')
            if connections is not None:
                rows.append({
                    'metric_type': 'connections',
                    'metric_name': 'active_connections',
                    'value': connections,
                    'unit': 'count',
                    'timestamp': ts,
                })

            cpu_usage = metrics.get('cpu_usage')
            if cpu_usage is not None:
                rows.append({
                    'metric_type': 'cpu',
                    'metric_name': 'cpu_usage',
                    'value': cpu_usage,
                    'unit': '%',
                    'timestamp': ts,
                })

            memory_usage = metrics.get('memory_usage')
            if memory_usage is not None:
                rows.append({
                    'metric_type': 'memory',
                    'metric_name': 'memory_usage',
                    'value': memory_usage,
                    'unit': '%',
                    'timestamp': ts,
                })

            for neighbor in metrics.get('ospf_neighbors', []):
                neighbor_ip = neighbor.get('neighbor_ip', 'unknown')
                rows.append({
                    'metric_type': 'ospf_neighbor',
                    'metric_name': f'ospf_nbr_{neighbor_ip}',
                    'value': neighbor.get('state'),
                    'unit': '',
                    'timestamp': ts,
                })

        return rows

    def get_metrics_history(
        self,
        device,
        metric_name: str,
        duration: timedelta
    ) -> List[Dict[str, Any]]:
        """
        获取历史监控数据（从 Redis 读取）

        Args:
            device: 设备对象
            metric_name: 指标名称
            duration: 时间范围

        Returns:
            按时间排序的监控数据字典列表，每个字典包含 timestamp 和 value

        """
        start_time = timezone.now() - duration
        redis_conn = self._get_redis_connection_safe()
        if redis_conn is None:
            return []
        key = f"metrics:device:{device.id}"
        raw_items = redis_conn.lrange(key, 0, -1)

        results = []
        for raw in raw_items:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            ts_str = data.get("timestamp")
            if not ts_str:
                continue
            try:
                ts = datetime.fromisoformat(ts_str)
            except ValueError:
                continue
            if ts < start_time:
                continue

            metrics = data.get("metrics", {})
            value = None

            # traffic
            for traffic in metrics.get('traffic', []):
                iface = traffic.get('interface', 'unknown')
                if f"{iface}_in" == metric_name:
                    value = traffic.get('in_octets', 0)
                    break
                if f"{iface}_out" == metric_name:
                    value = traffic.get('out_octets', 0)
                    break

            # interfaces
            if value is None:
                for interface in metrics.get('interfaces', []):
                    iface_name = interface.get('name', 'unknown')
                    if f"{iface_name}_status" == metric_name:
                        value = interface.get('status', 0)
                        break
                    if f"{iface_name}_in_mbps" == metric_name:
                        value = interface.get('in_mbps')
                        break
                    if f"{iface_name}_out_mbps" == metric_name:
                        value = interface.get('out_mbps')
                        break
                    if f"{iface_name}_in_drops" == metric_name:
                        value = interface.get('in_drop_rate')
                        break
                    if f"{iface_name}_out_drops" == metric_name:
                        value = interface.get('out_drop_rate')
                        break

            # simple metrics
            if value is None:
                if metric_name == 'packet_loss_rate' and metrics.get('packet_loss') is not None:
                    value = metrics['packet_loss']
                elif metric_name == 'active_connections' and metrics.get('connections') is not None:
                    value = metrics['connections']
                elif metric_name == 'cpu_usage' and metrics.get('cpu_usage') is not None:
                    value = metrics['cpu_usage']
                elif metric_name == 'memory_usage' and metrics.get('memory_usage') is not None:
                    value = metrics['memory_usage']

            # ospf neighbors
            if value is None:
                for neighbor in metrics.get('ospf_neighbors', []):
                    neighbor_ip = neighbor.get('neighbor_ip', 'unknown')
                    if f"ospf_nbr_{neighbor_ip}" == metric_name:
                        value = neighbor.get('state', 0)
                        break

            if value is not None:
                results.append({"timestamp": ts, "value": value})

        return sorted(results, key=lambda x: x["timestamp"])

    def check_thresholds(self, device, metrics: Dict[str, Any]) -> List:
        """
        检查监控指标是否超过阈值

        Args:
            device: 设备对象
            metrics: 监控指标数据

        Returns:
            告警列表

        """
        alerts = []

        # 检查丢包率
        if metrics.get('packet_loss') and metrics['packet_loss'] > self.THRESHOLDS['packet_loss']:
            alerts.append({
                'metric_type': 'packet_loss',
                'value': metrics['packet_loss'],
                'threshold': self.THRESHOLDS['packet_loss'],
                'severity': 'important',
                'message': f"丢包率超过阈值: {metrics['packet_loss']:.2f}% > {self.THRESHOLDS['packet_loss']}%",
            })

        # 检查接口指标
        for interface in metrics.get('interfaces', []):
            iface_name = interface.get('name', 'unknown')
            
            # 检查接口状态 (1=up, 2=down)
            if interface.get('status') == 2:  # down
                alerts.append({
                    'metric_type': 'interface_status',
                    'value': 0,
                    'threshold': 1,
                    'severity': 'critical',
                    'message': f"接口 {iface_name} 状态为 DOWN",
                    'interface': iface_name,
                })
            
            # 检查带宽利用率 (>80%)
            bandwidth_usage = interface.get('bandwidth_usage', 0)
            if bandwidth_usage > self.THRESHOLDS['interface_bandwidth']:
                alerts.append({
                    'metric_type': 'interface_bandwidth',
                    'value': bandwidth_usage,
                    'threshold': self.THRESHOLDS['interface_bandwidth'],
                    'severity': 'important',
                    'message': f"接口 {iface_name} 带宽利用率超过阈值: {bandwidth_usage:.1f}% > {self.THRESHOLDS['interface_bandwidth']}%",
                    'interface': iface_name,
                })
            
            # 检查入向丢包 (>100个/分钟)
            in_drop_rate = interface.get('in_drop_rate', 0)
            if in_drop_rate > self.THRESHOLDS['interface_in_drops']:
                alerts.append({
                    'metric_type': 'interface_in_drops',
                    'value': in_drop_rate,
                    'threshold': self.THRESHOLDS['interface_in_drops'],
                    'severity': 'warning',
                    'message': f"接口 {iface_name} 入向丢包超过阈值: {in_drop_rate} 个/分钟 > {self.THRESHOLDS['interface_in_drops']}",
                    'interface': iface_name,
                })
            
            # 检查出向丢包 (>100个/分钟)
            out_drop_rate = interface.get('out_drop_rate', 0)
            if out_drop_rate > self.THRESHOLDS['interface_out_drops']:
                alerts.append({
                    'metric_type': 'interface_out_drops',
                    'value': out_drop_rate,
                    'threshold': self.THRESHOLDS['interface_out_drops'],
                    'severity': 'warning',
                    'message': f"接口 {iface_name} 出向丢包超过阈值: {out_drop_rate} 个/分钟 > {self.THRESHOLDS['interface_out_drops']}",
                    'interface': iface_name,
                })

        # 检查OSPF邻居状态 (8=Full是正常)
        for neighbor in metrics.get('ospf_neighbors', []):
            neighbor_ip = neighbor.get('neighbor_ip', 'unknown')
            state = neighbor.get('state', 0)
            state_name = neighbor.get('state_name', f'unknown({state})')
            
            if not neighbor.get('is_full', False):
                alerts.append({
                    'metric_type': 'ospf_neighbor',
                    'value': state,
                    'threshold': 8,
                    'severity': 'important',
                    'message': f"OSPF邻居 {neighbor_ip} 状态异常: {state_name} (expected: full)",
                    'neighbor_ip': neighbor_ip,
                })

        # 生成告警
        for alert_info in alerts:
            self._create_metric_alert(device, alert_info)

        return alerts

    def _create_metric_alert(self, device, alert_info: Dict[str, Any]):
        """
        创建指标异常告警

        Args:
            device: 设备对象
            alert_info: 告警信息
        """
        try:
            from alerts.models import Alert

            # 根据告警类型确定告警类型
            metric_type = alert_info.get('metric_type', 'metric_abnormal')
            alert_type_map = {
                'packet_loss': 'metric_abnormal',
                'interface_status': 'interface_down',
                'interface_bandwidth': 'interface_high_load',
                'interface_in_drops': 'interface_drops',
                'interface_out_drops': 'interface_drops',
                'ospf_neighbor': 'routing_abnormal',
            }
            alert_type = alert_type_map.get(metric_type, 'metric_abnormal')

            # 构建告警消息
            message = alert_info.get('message')
            if not message:
                message = f"{metric_type} 超过阈值: {alert_info['value']} > {alert_info['threshold']}"

            alert = Alert.objects.create(
                device=device,
                alert_type=alert_type,
                severity=alert_info['severity'],
                message=message,
                status='active',
            )

            # 记录到系统日志
            self._record_metric_alert_log(alert, alert_info)

        except Exception as e:
            logger.error(f"创建指标告警失败: {e}")

    def _record_metric_alert_log(self, alert, alert_info: Dict[str, Any]) -> None:
        """
        记录指标告警到系统日志

        Args:
            alert: 告警对象
            alert_info: 告警信息
        """
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
                    'metric_type': alert_info.get('metric_type'),
                    'value': alert_info.get('value'),
                    'threshold': alert_info.get('threshold'),
                    'interface': alert_info.get('interface'),
                    'neighbor_ip': alert_info.get('neighbor_ip'),
                }
            )
        except Exception as e:
            logger.warning(f"记录指标告警日志失败: {e}")

    def cleanup_old_metrics(self, retention_hours: int = 24):
        """
        清理过期的监控数据

        监控数据已迁移至 Redis 并使用 TTL 自动过期，此方法不再操作 PostgreSQL。

        Args:
            retention_hours: 保留时间（小时），仅用于兼容旧接口

        """
        return {
            'success': True,
            'deleted_count': 0,
            'note': '监控数据已存储在 Redis 并由 TTL 自动过期',
        }
