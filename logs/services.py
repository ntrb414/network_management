"""
日志分析服务

提供日志收集、查询、统计分析等功能。
"""

import logging
import re
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, Q
from django.utils import timezone

logger = logging.getLogger(__name__)

_SYSLOG_PRI_RE = re.compile(r'^<(\d{1,3})>')
_SYSLOG_RFC3164_RE = re.compile(
    r'^(?P<ts>[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(?P<host>\S+)\s+(?P<body>.+)$'
)
_SYSLOG_ISO_RE = re.compile(
    r'^(?P<ts>\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:[\.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\s+(?P<host>\S+)\s+(?P<body>.+)$'
)
_SYSLOG_PROGRAM_RE = re.compile(r'^(?P<program>[\w\-./]+)(?:\[(?P<pid>\d+)\])?:\s*(?P<msg>.*)$')

_SYSLOG_SEVERITY_NUM_TO_NAME = {
    0: 'emergency',
    1: 'alert',
    2: 'critical',
    3: 'error',
    4: 'warning',
    5: 'notice',
    6: 'informational',
    7: 'debug',
}

_SYSLOG_FACILITY_NUM_TO_NAME = {
    0: 'kern',
    1: 'user',
    2: 'mail',
    3: 'daemon',
    4: 'auth',
    5: 'syslog',
    6: 'lpr',
    7: 'news',
    8: 'uucp',
    9: 'clock',
    10: 'authpriv',
    11: 'ftp',
    12: 'ntp',
    13: 'audit',
    14: 'alert',
    15: 'clock2',
    16: 'local0',
    17: 'local1',
    18: 'local2',
    19: 'local3',
    20: 'local4',
    21: 'local5',
    22: 'local6',
    23: 'local7',
}

_SYSLOG_ALERT_RULES = [
    {
        'id': 'interface_down',
        'severity': 'important',
        'message': '接口状态异常',
        'patterns': [
            r'interface\s+\S+\s+down',
            r'link\s+down',
            r'line protocol\s+is\s+down',
            r'ifnet.*down',
        ],
    },
    {
        'id': 'routing_neighbor_down',
        'severity': 'critical',
        'message': '路由邻居异常',
        'patterns': [
            r'bgp.*neighbor.*down',
            r'ospf.*neighbor.*down',
            r'peer\s+\S+\s+down',
            r'neighbor\s+\S+\s+state.*down',
        ],
    },
    {
        'id': 'auth_failed',
        'severity': 'important',
        'message': '认证失败',
        'patterns': [
            r'authentication\s+failed',
            r'login\s+failed',
            r'bad\s+password',
            r'password\s+error',
            r'failed\s+login',
        ],
    },
]


class LogService:
    """日志分析服务类"""

    def collect_device_log(
        self,
        device,
        log_type: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        user=None
    ):
        """
        收集设备日志

        Args:
            device: 设备对象
            log_type: 日志类型 (alert/system)
            message: 日志内容
            details: 详细信息
            user: 操作用户

        Returns:
            创建的日志对象

        """
        from .models import SystemLog

        log = SystemLog.objects.create(
            device=device,
            log_type=log_type,
            message=message,
            details=details,
            user=user
        )

        return log

    def create_alert_log(
        self,
        device,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        创建告警日志

        Args:
            device: 设备对象
            message: 日志内容
            details: 详细信息

        Returns:
            创建的日志对象
        """
        return self.collect_device_log(
            device=device,
            log_type='alert',
            message=message,
            details=details
        )

    def create_system_log(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        device=None
    ):
        """
        创建系统日志

        Args:
            message: 日志内容
            details: 详细信息
            device: 设备对象

        Returns:
            创建的日志对象
        """
        return self.collect_device_log(
            device=device,
            log_type='system',
            message=message,
            details=details
        )

    def process_syslog_message(self, source_ip: str, raw_message: str) -> Dict[str, Any]:
        """处理一条 Syslog 报文并写入设备运行日志。"""
        from devices.models import Device

        payload = (raw_message or '').strip()
        if not payload:
            return {
                'success': False,
                'ignored': True,
                'reason': 'empty_payload',
            }

        device = Device.objects.filter(ip_address=source_ip).first()
        if not device:
            logger.warning('收到未知设备的Syslog报文: source_ip=%s payload=%r', source_ip, payload[:160])
            return {
                'success': False,
                'ignored': True,
                'reason': 'unknown_device',
                'source_ip': source_ip,
            }

        if not getattr(device, 'syslog_enabled', False):
            return {
                'success': False,
                'ignored': True,
                'reason': 'syslog_disabled',
                'device_id': device.id,
                'device_name': device.name,
            }

        parsed = self._parse_syslog_line(source_ip=source_ip, raw_message=payload)
        details = {
            'source': 'syslog',
            'event_time': parsed.get('event_time'),
            'ingest_time': timezone.now().isoformat(),
            'source_ip': parsed.get('source_ip') or source_ip,
            'hostname': parsed.get('hostname'),
            'severity': parsed.get('severity'),
            'facility': parsed.get('facility'),
            'program': parsed.get('program'),
            'message': parsed.get('message'),
        }

        log_obj = self.collect_device_log(
            device=device,
            log_type='system',
            message=parsed.get('message') or payload,
            details=details,
        )

        alert_info = self._try_create_syslog_alert(device=device, parsed=parsed)

        return {
            'success': True,
            'device_id': device.id,
            'device_name': device.name,
            'log_id': log_obj.id,
            'alert_created': bool(alert_info),
            'alert': alert_info,
        }

    def query_runtime_logs(
        self,
        keyword: Optional[str] = None,
        device_id: Optional[int] = None,
        source_ip: Optional[str] = None,
        severity: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """查询设备运行日志（Syslog来源）。"""
        from .models import SystemLog
        from devices.models import Device

        queryset = SystemLog.objects.filter(log_type='system', details__source='syslog')

        if keyword:
            queryset = queryset.filter(Q(message__icontains=keyword) | Q(details__icontains=keyword))
        if device_id:
            queryset = queryset.filter(device_id=device_id)
        if source_ip:
            queryset = queryset.filter(details__source_ip=source_ip)
        if severity:
            queryset = queryset.filter(details__severity=severity)
        if start_time:
            queryset = queryset.filter(timestamp__gte=start_time)
        if end_time:
            queryset = queryset.filter(timestamp__lte=end_time)

        total = queryset.count()
        offset = (page - 1) * page_size
        page_logs = list(queryset[offset:offset + page_size].values(
            'id', 'message', 'timestamp', 'device_id', 'details'
        ))

        device_ids = {item.get('device_id') for item in page_logs if item.get('device_id')}
        devices = {d.id: d.name for d in Device.objects.filter(id__in=device_ids)} if device_ids else {}

        logs = []
        for item in page_logs:
            details = item.get('details') or {}
            logs.append(
                {
                    'id': item['id'],
                    'message': item.get('message'),
                    'timestamp': item['timestamp'].isoformat() if item.get('timestamp') else None,
                    'device_id': item.get('device_id'),
                    'device_name': devices.get(item.get('device_id'), '-'),
                    'source_ip': details.get('source_ip'),
                    'hostname': details.get('hostname'),
                    'severity': details.get('severity'),
                    'facility': details.get('facility'),
                    'program': details.get('program'),
                    'event_time': details.get('event_time'),
                }
            )

        return {
            'total': total,
            'page': page,
            'page_size': page_size,
            'logs': logs,
        }

    def save_device_syslog_settings(
        self,
        device,
        enabled: Optional[bool] = None,
        server_ip: Optional[str] = None,
        server_port: Optional[int] = None,
        protocol: Optional[str] = None,
        severity_threshold: Optional[str] = None,
        push_to_device: bool = False,
    ) -> Dict[str, Any]:
        """保存设备Syslog参数，支持可选的一键下发。"""
        protocol_choices = {item[0] for item in device.SYSLOG_PROTOCOL_CHOICES}
        severity_choices = {item[0] for item in device.SYSLOG_SEVERITY_CHOICES}

        updated_fields = []
        if enabled is not None:
            device.syslog_enabled = bool(enabled)
            updated_fields.append('syslog_enabled')
        if server_ip is not None:
            device.syslog_server_ip = server_ip or None
            updated_fields.append('syslog_server_ip')
        if server_port is not None:
            device.syslog_server_port = int(server_port)
            updated_fields.append('syslog_server_port')
        if protocol and protocol in protocol_choices:
            device.syslog_protocol = protocol
            updated_fields.append('syslog_protocol')
        if severity_threshold and severity_threshold in severity_choices:
            device.syslog_severity_threshold = severity_threshold
            updated_fields.append('syslog_severity_threshold')

        if updated_fields:
            device.save(update_fields=sorted(set(updated_fields)))

        push_result = None
        if push_to_device:
            push_result = self.push_syslog_settings_to_device(device)

        return {
            'success': True,
            'device_id': device.id,
            'updated_fields': sorted(set(updated_fields)),
            'push_result': push_result,
        }

    def push_syslog_settings_to_device(self, device) -> Dict[str, Any]:
        """将设备Syslog参数下发到设备。"""
        from configs.services import ConfigManagementService

        commands = self._build_syslog_config_commands(device)
        if not commands:
            return {
                'success': False,
                'device_id': device.id,
                'device_name': device.name,
                'error': '未生成可下发的Syslog命令，请检查参数配置',
            }

        config_text = '\n'.join(commands)
        service = ConfigManagementService()
        result = service.deploy_config(device, config_text)
        result['generated_commands'] = commands
        return result

    def _build_syslog_config_commands(self, device) -> List[str]:
        vendor = self._detect_vendor(device)
        level = self._map_vendor_syslog_level(vendor, device.syslog_severity_threshold)

        if not device.syslog_enabled:
            return [
                'undo info-center loghost',
            ]

        if not device.syslog_server_ip:
            return []

        if vendor == 'h3c':
            return [
                'info-center enable',
                'undo info-center loghost',
                f'info-center loghost {device.syslog_server_ip} port {device.syslog_server_port}',
                f'info-center source default channel loghost log level {level}',
            ]

        return [
            'info-center enable',
            'undo info-center loghost',
            f'info-center loghost {device.syslog_server_ip} transport udp port {device.syslog_server_port}',
            f'info-center source default channel loghost level {level}',
        ]

    def _map_vendor_syslog_level(self, vendor: str, level: str) -> str:
        """将统一severity映射为厂商命令可接受的级别。"""
        if vendor == 'h3c' and level == 'informational':
            return 'informational'
        return level

    def _parse_syslog_line(self, source_ip: str, raw_message: str) -> Dict[str, Any]:
        payload = (raw_message or '').strip()
        pri = None
        facility = None
        severity = None

        pri_match = _SYSLOG_PRI_RE.match(payload)
        if pri_match:
            pri = int(pri_match.group(1))
            payload = payload[pri_match.end():].lstrip()
            facility = _SYSLOG_FACILITY_NUM_TO_NAME.get(pri // 8)
            severity = _SYSLOG_SEVERITY_NUM_TO_NAME.get(pri % 8)

        timestamp_str = ''
        hostname = source_ip
        body = payload

        iso_match = _SYSLOG_ISO_RE.match(payload)
        rfc3164_match = _SYSLOG_RFC3164_RE.match(payload)
        prefix_match = iso_match or rfc3164_match
        if prefix_match:
            timestamp_str = prefix_match.group('ts')
            hostname = prefix_match.group('host')
            body = prefix_match.group('body')

        program = ''
        message = body
        program_match = _SYSLOG_PROGRAM_RE.match(body)
        if program_match:
            program = program_match.group('program') or ''
            message = program_match.group('msg') or ''

        severity = severity or self._infer_severity_from_message(message)

        return {
            'event_time': self._parse_syslog_event_time(timestamp_str),
            'source_ip': source_ip,
            'hostname': hostname,
            'severity': severity,
            'facility': facility,
            'program': program,
            'message': message or body,
        }

    def _parse_syslog_event_time(self, timestamp_str: str) -> Optional[str]:
        if not timestamp_str:
            return None

        try:
            if '-' in timestamp_str and ':' in timestamp_str:
                normalized = timestamp_str.replace(',', '.')
                if normalized.endswith('Z'):
                    normalized = normalized[:-1] + '+00:00'
                iso_offset_match = re.search(r'([+-]\d{2})(\d{2})$', normalized)
                if iso_offset_match and ':' not in normalized[-6:]:
                    normalized = normalized[:-5] + f"{iso_offset_match.group(1)}:{iso_offset_match.group(2)}"
                dt = datetime.fromisoformat(normalized)
                if timezone.is_naive(dt):
                    dt = timezone.make_aware(dt, timezone.get_current_timezone())
                return dt.isoformat()

            dt = datetime.strptime(timestamp_str, '%b %d %H:%M:%S')
            now = timezone.localtime()
            dt = dt.replace(year=now.year)
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
            return dt.isoformat()
        except Exception:
            return None

    def _infer_severity_from_message(self, message: str) -> str:
        text = (message or '').lower()
        if any(word in text for word in ['critical', 'panic', 'fatal']):
            return 'critical'
        if any(word in text for word in ['error', 'failed', 'failure', 'deny', 'denied']):
            return 'error'
        if any(word in text for word in ['warning', 'down', 'unstable', 'flap']):
            return 'warning'
        if any(word in text for word in ['notice', 'changed']):
            return 'notice'
        if any(word in text for word in ['debug', 'trace']):
            return 'debug'
        return 'informational'

    def _match_syslog_alert_rule(self, message: str) -> Optional[Dict[str, Any]]:
        text = message or ''
        for rule in _SYSLOG_ALERT_RULES:
            for pattern in rule['patterns']:
                if re.search(pattern, text, flags=re.IGNORECASE):
                    return rule
        return None

    def _try_create_syslog_alert(self, device, parsed: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        from alerts.services import AlertService

        rule = self._match_syslog_alert_rule(parsed.get('message', ''))
        if not rule:
            return None

        suppress_seconds = int(getattr(settings, 'SYSLOG_ALERT_SUPPRESS_SECONDS', 120))
        suppress_key = f"syslog_alert:{device.id}:{rule['id']}"
        if cache.get(suppress_key):
            return {
                'suppressed': True,
                'rule_id': rule['id'],
            }

        alert_message = f"设备 {device.name} {rule['message']}: {parsed.get('message', '')[:180]}"
        alert = AlertService().create_alert(
            device=device,
            alert_type='device_fault',
            severity=rule['severity'],
            message=alert_message,
        )
        cache.set(suppress_key, True, timeout=suppress_seconds)

        return {
            'suppressed': False,
            'rule_id': rule['id'],
            'alert_id': alert.id,
        }

    def query_logs(
        self,
        keyword: Optional[str] = None,
        log_type: Optional[str] = None,
        device_id: Optional[int] = None,
        user_id: Optional[int] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 50
    ) -> Dict[str, Any]:
        """
        查询日志

        Args:
            keyword: 关键字搜索
            log_type: 日志类型筛选
            device_id: 设备ID筛选
            user_id: 用户ID筛选
            start_time: 开始时间
            end_time: 结束时间
            page: 页码
            page_size: 每页数量

        Returns:
            分页后的日志列表

        """
        from .models import SystemLog

        queryset = SystemLog.objects.all()

        # 关键字搜索
        if keyword:
            queryset = queryset.filter(
                Q(message__icontains=keyword) |
                Q(details__icontains=keyword)
            )

        # 日志类型筛选
        if log_type:
            queryset = queryset.filter(log_type=log_type)

        # 设备筛选
        if device_id:
            queryset = queryset.filter(device_id=device_id)

        # 用户筛选
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        # 时间范围筛选
        if start_time:
            queryset = queryset.filter(timestamp__gte=start_time)
        if end_time:
            queryset = queryset.filter(timestamp__lte=end_time)

        # 分页
        total = queryset.count()
        offset = (page - 1) * page_size
        page_logs = queryset[offset:offset + page_size]

        # 获取所有字段值（包括 id, device_id, user_id 等）
        logs_values = list(page_logs.values(
            'id', 'log_type', 'message', 'timestamp',
            'device_id', 'user_id'
        ))

        # 构建结果，手动解析 device_name 和 user_name
        from django.contrib.auth import get_user_model
        from devices.models import Device
        User = get_user_model()
        device_ids = set(log['device_id'] for log in logs_values if log.get('device_id'))
        user_ids = set(log['user_id'] for log in logs_values if log.get('user_id'))
        devices = {d.id: d.name for d in Device.objects.filter(id__in=device_ids)} if device_ids else {}
        users = {u.id: u.username for u in User.objects.filter(id__in=user_ids)} if user_ids else {}

        log_list = []
        for log in logs_values:
            log_list.append({
                'id': log['id'],
                'log_type': log['log_type'],
                'message': log['message'],
                'timestamp': log['timestamp'].isoformat() if log.get('timestamp') else None,
                'device_id': log.get('device_id'),
                'device_name': devices.get(log.get('device_id'), '-'),
                'user_id': log.get('user_id'),
                'user_name': users.get(log.get('user_id'), '-'),
            })

        return {
            'total': total,
            'page': page,
            'page_size': page_size,
            'logs': log_list,
        }

    def get_statistics(
        self,
        days: int = 7,
        log_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取日志统计信息

        Args:
            days: 统计天数
            log_type: 日志类型筛选

        Returns:
            统计信息

        """
        from .models import SystemLog

        # 计算时间范围
        end_time = timezone.now()
        start_time = end_time - timedelta(days=days)

        # 基础查询集
        queryset = SystemLog.objects.filter(timestamp__gte=start_time)

        if log_type:
            queryset = queryset.filter(log_type=log_type)

        # 按类型统计
        by_type = queryset.values('log_type').annotate(
            count=Count('id')
        )

        # 按日期统计
        from django.db.models.functions import TruncDate
        by_date = queryset.annotate(
            date=TruncDate('timestamp')
        ).values('date').annotate(count=Count('id')).order_by('date')

        # 总数
        total = queryset.count()

        # 今日数量
        today_start = end_time.replace(hour=0, minute=0, second=0, microsecond=0)
        today_count = queryset.filter(timestamp__gte=today_start).count()

        return {
            'total': total,
            'today_count': today_count,
            'by_type': list(by_type),
            'by_date': list(by_date),
            'days': days,
        }

    def cleanup_old_logs(self, days: int = 7) -> Dict[str, Any]:
        """
        清理老旧日志

        Args:
            days: 保留天数

        Returns:
            清理结果

        """
        from .models import SystemLog

        # 计算截止时间
        cutoff_time = timezone.now() - timedelta(days=days)

        # 删除旧日志
        deleted_count, _ = SystemLog.objects.filter(
            timestamp__lt=cutoff_time
        ).delete()

        return {
            'success': True,
            'deleted_count': deleted_count,
            'cutoff_time': cutoff_time,
        }

    # ==================== 设备日志采集相关方法 ====================

    def collect_logs_from_device(self, device) -> Dict[str, Any]:
        """
        从设备采集日志并存储到数据库

        Args:
            device: 设备对象

        Returns:
            采集结果字典
        """
        if device.status != 'online':
            return {
                'success': False,
                'device_id': device.id,
                'device_name': device.name,
                'error': '设备不在线',
                'collected_count': 0,
            }

        try:
            # 通过SSH获取日志
            raw_logs = self._get_logs_via_ssh(device)

            if not raw_logs:
                return {
                    'success': True,
                    'device_id': device.id,
                    'device_name': device.name,
                    'collected_count': 0,
                    'message': '无日志内容',
                }

            # 解析并存储日志
            collected_count = self._parse_and_store_logs(device, raw_logs)

            logger.info(f"设备 {device.name} 日志采集完成，共 {collected_count} 条")

            return {
                'success': True,
                'device_id': device.id,
                'device_name': device.name,
                'collected_count': collected_count,
            }

        except Exception as e:
            logger.error(f"采集设备 {device.name} 日志失败: {e}")
            return {
                'success': False,
                'device_id': device.id,
                'device_name': device.name,
                'error': str(e),
                'collected_count': 0,
            }

    def _get_logs_via_ssh(self, device) -> str:
        """
        通过SSH获取设备日志

        Args:
            device: 设备对象

        Returns:
            原始日志内容
        """
        try:
            from netmiko import ConnectHandler

            device_params = {
                'device_type': self._map_device_type_to_netmiko(device),
                'host': device.ip_address,
                'port': device.ssh_port or 22,
                'username': device.ssh_username,
                'password': device.ssh_password,
                'timeout': 10,
                'session_timeout': 30,
                'conn_timeout': 8,
                'fast_cli': True,
                'global_delay_factor': 0.5,
                'disabled_algorithms': {'pubkeys': ['rsa-sha2-256', 'rsa-sha2-512']},
            }

            command = self._get_log_command(device)
            vendor = self._detect_vendor(device)

            with ConnectHandler(**device_params) as conn:
                # 禁用分页
                if vendor == 'huawei':
                    conn.send_command('screen-length 0 temporary', expect_string=r'[>#]')
                elif vendor == 'h3c':
                    conn.send_command('screen-length disable', expect_string=r'[>#]')

                logs = conn.send_command(command, read_timeout=15)
                return logs

        except ImportError:
            logger.warning("Netmiko库未安装，无法通过SSH获取设备日志")
            return ""
        except Exception as e:
            logger.error(f"SSH获取设备日志失败: {e}")
            raise

    def _detect_vendor(self, device) -> str:
        """
        检测设备厂商

        Args:
            device: 设备对象

        Returns:
            'huawei' | 'h3c' | 'unknown'
        """
        name = (device.name or '').lower()
        model = (device.model or '').lower()
        device_type = (device.device_type or '').lower()

        huawei_keywords = ['huawei', '华为', 's5700', 's6700', 's12700', 'ce', 'ar', 'ne']
        h3c_keywords = ['h3c', '华三', 's5120', 's5560', 's7500', 's10500', 'msr', 'sr']

        check_str = f"{name} {model} {device_type}"

        for kw in huawei_keywords:
            if kw in check_str:
                return 'huawei'
        for kw in h3c_keywords:
            if kw in check_str:
                return 'h3c'

        return 'huawei'

    def _map_device_type_to_netmiko(self, device) -> str:
        """
        将设备映射到Netmiko设备类型

        Args:
            device: 设备对象

        Returns:
            Netmiko设备类型
        """
        vendor = self._detect_vendor(device)

        if vendor == 'h3c':
            return 'hp_comware'
        else:
            return 'huawei'

    def _get_log_command(self, device) -> str:
        """
        根据设备厂商获取日志命令

        Args:
            device: 设备对象

        Returns:
            获取日志的命令
        """
        vendor = self._detect_vendor(device)

        commands_map = {
            'huawei': 'display logbuffer',
            'h3c': 'display logbuffer',
        }

        return commands_map.get(vendor, 'display logbuffer')

    def _parse_and_store_logs(self, device, raw_logs: str) -> int:
        """
        解析设备原始日志并存储到数据库

        Args:
            device: 设备对象
            raw_logs: 原始日志内容

        Returns:
            存储的日志条数
        """
        if not raw_logs or not raw_logs.strip():
            return 0

        lines = raw_logs.strip().split('\n')
        count = 0

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 跳过命令回显、标题行等无用行
            if any(skip in line for skip in ['display logbuffer', 'Logbuffer', '====', 'Parsing', '-']):
                continue

            # 解析日志行（华为格式: 日期 时间 模块 Level 内容）
            # 例如: "Jul 26 2024 10:30:15  DEV 1  DEV/1/DEV: ..."
            parsed = self._parse_log_line(line)
            if parsed:
                self.collect_device_log(
                    device=device,
                    log_type='system',
                    message=parsed['message'],
                    details=parsed
                )
                count += 1

        return count

    def _parse_log_line(self, line: str) -> Optional[Dict[str, Any]]:
        """
        解析单条日志行

        Args:
            line: 日志行

        Returns:
            解析后的日志字典，解析失败返回None
        """
        import re

        # 华为/华三日志格式匹配
        # 格式: Jul 26 2024 10:30:15  DEV 1  DEV/1/DEV: info message
        # 或: %Y-%m-%d %H:%M:%S like format
        patterns = [
            # 华为设备日志: Jul 26 2024 10:30:15  DEV 1  MODULE/LEVEL/INFO: message
            r'(\w{3}\s+\d{1,2}\s+\d{4}\s+\d{2}:\d{2}:\d{2})\s+(\S+)\s+(\d+)\s+(\S+):\s*(.*)',
            # 简单位置信息格式
            r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(\S+):\s*(.*)',
        ]

        for pattern in patterns:
            match = re.match(pattern, line)
            if match:
                groups = match.groups()
                if len(groups) >= 5:
                    return {
                        'timestamp_str': groups[0],
                        'module': groups[2] if len(groups) > 2 else '',
                        'level': groups[3] if len(groups) > 3 else '',
                        'message': groups[4] if len(groups) > 4 else groups[-1],
                        'raw_line': line,
                    }
                elif len(groups) >= 3:
                    return {
                        'timestamp_str': groups[0],
                        'module': '',
                        'level': '',
                        'message': groups[2] if len(groups) > 2 else groups[-1],
                        'raw_line': line,
                    }

        # 无法解析的原始行也保存
        if line:
            return {
                'timestamp_str': '',
                'module': '',
                'level': '',
                'message': line,
                'raw_line': line,
            }

        return None
