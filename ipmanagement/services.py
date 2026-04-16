"""
IPAM Services - IP地址管理服务
"""
import ipaddress as ip_lib
import json
import logging
import platform
import re
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


class NetworkDiscoveryService:
    """网络发现服务 - 根据设备表IP自动推导网段"""

    ipv4_prefix = 24
    ipv6_prefix = 64

    def _build_cidr_from_device_ip(self, ip_address: str) -> Optional[str]:
        try:
            ip_obj = ip_lib.ip_address(ip_address)
        except ValueError:
            logger.warning(f"Skip invalid device IP during subnet discovery: {ip_address}")
            return None

        prefix = self.ipv4_prefix if ip_obj.version == 4 else self.ipv6_prefix
        return str(ip_lib.ip_network(f"{ip_obj}/{prefix}", strict=False))

    def _subnet_sort_key(self, cidr: str):
        network = ip_lib.ip_network(cidr, strict=False)
        return (network.version, int(network.network_address), network.prefixlen)

    def discover_network_subnet_details(self) -> List[Dict]:
        """从设备表IP推导可发现网段明细"""
        from devices.models import Device
        from .models import Subnet

        existing_subnets = set(Subnet.objects.values_list('cidr', flat=True))
        discovered = {}

        device_ips = Device.objects.exclude(ip_address__isnull=True).values_list('ip_address', flat=True)
        for device_ip in device_ips:
            cidr = self._build_cidr_from_device_ip(device_ip)
            if not cidr:
                continue

            if cidr not in discovered:
                discovered[cidr] = {
                    'cidr': cidr,
                    'name': f'自动发现-{cidr}',
                    'device_count': 0,
                    'exists': cidr in existing_subnets,
                }

            discovered[cidr]['device_count'] += 1

        subnet_details = sorted(discovered.values(), key=lambda item: self._subnet_sort_key(item['cidr']))
        logger.info(f"Discovered {len(subnet_details)} subnets from device IPs")
        return subnet_details

    def discover_network_subnets(self) -> List[str]:
        """从设备表IP推导网段CIDR列表"""
        return [item['cidr'] for item in self.discover_network_subnet_details()]


class IPScanService:
    """IP扫描服务 - 优先使用ICMP ping"""

    def __init__(self, timeout: int = 2, max_workers: int = 20, common_ports: List[int] = None):
        # 保守默认：超时2s，并发20
        self.timeout = timeout
        self.max_workers = max_workers
        # 可配置的端口回退列表
        self.common_ports = common_ports or [22, 80, 443, 161, 3389, 8080]

    def icmp_ping(self, ip: str) -> Dict:
        """使用ICMP ping检测主机是否存活"""
        system = platform.system().lower()
        try:
            if system == 'windows':
                cmd = ['ping', '-n', '1', '-w', str(self.timeout * 1000), ip]
            else:
                cmd = ['ping', '-c', '1', '-W', str(self.timeout), ip]

            start_time = timezone.now()
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout + 1,
                shell=False
            )

            is_alive = result.returncode == 0
            response_time = None

            if is_alive:
                response_time = self._parse_response_time(result.stdout)
                if response_time is None:
                    delta = (timezone.now() - start_time).total_seconds() * 1000
                    response_time = round(delta, 2)

            return {
                'ip': ip,
                'alive': is_alive,
                'hostname': None,
                'response_time': response_time,
                'method': 'ICMP',
            }

        except subprocess.TimeoutExpired:
            logger.debug(f"ICMP ping timeout for {ip}")
            return {'ip': ip, 'alive': False, 'hostname': None, 'response_time': None, 'method': 'ICMP'}
        except Exception as e:
            logger.debug(f"ICMP ping failed for {ip}: {e}")
            return {'ip': ip, 'alive': False, 'hostname': None, 'response_time': None, 'method': 'ICMP'}

    def _parse_response_time(self, output) -> Optional[float]:
        """从ping输出中解析响应时间"""
        try:
            output_str = output.decode('utf-8', errors='ignore') if isinstance(output, bytes) else str(output)
            match = re.search(r'time[<=]([\d.]+)\s*ms', output_str, re.IGNORECASE)
            if match:
                return float(match.group(1))
        except Exception:
            pass
        return None

    def tcp_port_scan_fallback(self, ip: str, hostname: str = None) -> Dict:
        """TCP端口扫描后备方案，使用实例化时配置的端口列表"""
        for port in self.common_ports:
            try:
                start_time = timezone.now()
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self.timeout)
                result = sock.connect_ex((ip, port))
                sock.close()

                if result == 0:
                    # 端口开放，主机存活
                    delta = (timezone.now() - start_time).total_seconds() * 1000
                    response_time = round(delta, 2)

                    return {
                        'ip': ip,
                        'alive': True,
                        'hostname': hostname,
                        'response_time': response_time,
                        'open_port': port,
                        'method': 'TCP',
                    }
            except (socket.error, socket.timeout, OSError) as e:
                logger.debug(f"Port {port} on {ip} failed: {e}")
                continue

        return {'ip': ip, 'alive': False, 'hostname': hostname, 'response_time': None, 'method': 'TCP'}

    def ping_host(self, ip: str) -> Dict:
        """检测主机是否存活，优先使用ICMP ping"""
        # 先尝试ICMP ping
        result = self.icmp_ping(ip)
        
        # 如果ICMP失败，尝试TCP端口扫描
        if not result['alive']:
            tcp_result = self.tcp_port_scan_fallback(ip, result.get('hostname'))
            if tcp_result['alive']:
                return tcp_result
        
        return result

    def calculate_ip_range(self, cidr: str) -> List[str]:
        """根据CIDR计算IP范围，支持任意大小网段"""
        try:
            network = ip_lib.ip_network(cidr, strict=False)
            hosts = network.hosts()
            # 对于大网段，仍然生成完整hosts迭代，但实际扫描由上层限制
            return [str(ip) for ip in hosts]
        except ValueError as e:
            logger.error(f"Invalid CIDR format: {cidr}, error: {e}")
            return []

    def parse_targets(self, targets: List[str], max_targets: int = 4096) -> List[str]:
        """解析用户输入的 targets 列表（IP 或 CIDR 或 IP范围 start-end），返回去重后的 IP 列表，受 max_targets 限制"""
        resolved = []
        seen = set()

        for t in targets:
            t = t.strip()
            if not t:
                continue

            # CIDR
            if '/' in t:
                ips = self.calculate_ip_range(t)
            # IP range like 192.168.1.10-192.168.1.20
            elif '-' in t and not t.count('.') == 0:
                parts = t.split('-')
                if len(parts) == 2:
                    try:
                        start = ip_lib.ip_address(parts[0].strip())
                        end = ip_lib.ip_address(parts[1].strip())
                        if int(start) > int(end):
                            start, end = end, start
                        ips = [str(ip_lib.ip_address(i)) for i in range(int(start), int(end) + 1)]
                    except Exception:
                        ips = []
                else:
                    ips = []
            else:
                # 单个IP
                try:
                    ip_obj = ip_lib.ip_address(t)
                    ips = [str(ip_obj)]
                except ValueError:
                    ips = []

            for ip in ips:
                if ip in seen:
                    continue
                seen.add(ip)
                resolved.append(ip)

                if len(resolved) >= max_targets:
                    logger.warning(f"Reached max_targets limit {max_targets}, stopping parse")
                    return resolved

        return resolved

    def scan_targets(self, targets: List[str], progress_callback=None, ports: List[int] = None, max_targets: int = 4096, return_all: bool = False) -> List[Dict]:
        """统一入口：接收混合的 IP/CIDR/范围 列表，解析并扫描，受 max_targets 限制"""
        try:
            ip_list = self.parse_targets(targets, max_targets=max_targets)
            total = len(ip_list)

            if total == 0:
                logger.error("No valid targets to scan")
                return []

            logger.info(f"Starting scan for {total} targets (max_workers={self.max_workers})")

            max_workers = min(self.max_workers, max(5, total // 50))
            alive_hosts = []
            all_results = []
            scanned_count = 0

            # 临时覆盖回退端口（如果传入）
            if ports is not None:
                old_ports = self.common_ports
                self.common_ports = ports

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_ip = {executor.submit(self.ping_host, ip): ip for ip in ip_list}

                for future in as_completed(future_to_ip):
                    result = future.result()
                    scanned_count += 1
                    all_results.append(result)

                    if result['alive']:
                        alive_hosts.append(result)

                    if progress_callback:
                        progress_callback(scanned_count, total, result)

            if ports is not None:
                self.common_ports = old_ports

            logger.info(f"Scan completed: {len(alive_hosts)}/{total} hosts alive")
            return all_results if return_all else alive_hosts

        except Exception as e:
            logger.error(f"scan_targets failed: {e}")
            return []

    def scan_subnet(self, cidr: str, progress_callback=None, return_all: bool = False) -> List[Dict]:
        """扫描整个网段，支持任意大小"""
        try:
            ip_list = self.calculate_ip_range(cidr)
            total = len(ip_list)
            
            if total == 0:
                logger.error(f"No valid hosts found for CIDR: {cidr}")
                return []

            logger.info(f"Starting scan for subnet {cidr}, total IPs: {total}")
            
            # 根据网段大小动态调整并发数
            max_workers = min(self.max_workers, max(10, total // 100))
            alive_hosts = []
            all_results = []
            scanned_count = 0

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_ip = {executor.submit(self.ping_host, ip): ip for ip in ip_list}
                
                for future in as_completed(future_to_ip):
                    result = future.result()
                    scanned_count += 1
                    all_results.append(result)
                    
                    if result['alive']:
                        alive_hosts.append(result)
                    
                    if progress_callback:
                        progress_callback(scanned_count, total, result)

            logger.info(f"Scan completed for {cidr}: {len(alive_hosts)}/{total} hosts alive")
            return all_results if return_all else alive_hosts

        except Exception as e:
            logger.error(f"Scan subnet {cidr} failed: {e}")
            return []

    def get_scan_result(self, task_id: int) -> Dict:
        """获取扫描任务结果（优先从 Redis 读取）"""
        from .models import IPScanTask
        from django_redis import get_redis_connection

        try:
            task = IPScanTask.objects.get(id=task_id)
        except IPScanTask.DoesNotExist:
            return {'success': False, 'error': '扫描任务不存在'}

        redis_conn = get_redis_connection("default")
        redis_key = f"ipscan:task:{task_id}"
        raw = redis_conn.get(redis_key)

        if raw:
            try:
                result_data = json.loads(raw)
                return {
                    'success': True,
                    'task_id': task.id,
                    'cidr': task.cidr,
                    'status': task.status,
                    'total_ips': task.total_ips,
                    'scanned_ips': task.scanned_ips,
                    'alive_count': result_data.get('alive_count', 0),
                    'alive_hosts': result_data.get('alive_hosts', []),
                    'all_results': result_data.get('all_results', []),
                    'created_at': task.created_at,
                    'completed_at': task.completed_at,
                }
            except json.JSONDecodeError:
                pass

        # Redis 已过期或解析失败，返回任务元数据
        return {
            'success': True,
            'task_id': task.id,
            'cidr': task.cidr,
            'status': task.status,
            'total_ips': task.total_ips,
            'scanned_ips': task.scanned_ips,
            'alive_count': task.alive_ips,
            'alive_hosts': [],
            'expired': True,
            'note': '扫描结果已过期，请重新扫描',
            'created_at': task.created_at,
            'completed_at': task.completed_at,
        }


class IPAMService:
    """IPAM服务 - IP地址分配和管理"""

    def get_or_create_ip(self, ip_address: str, subnet) -> 'IPAddress':
        """获取或创建IP地址记录"""
        from .models import IPAddress

        ip, created = IPAddress.objects.get_or_create(
            ip_address=ip_address,
            defaults={'subnet': subnet, 'status': 'available'}
        )
        return ip

    def allocate_ip(
        self,
        ip_address: str,
        device=None,
        user=None,
        hostname: str = '',
        description: str = ''
    ) -> Dict[str, any]:
        """分配IP给设备"""
        from .models import IPAddress, AllocationLog

        try:
            ip = IPAddress.objects.get(ip_address=ip_address)
        except IPAddress.DoesNotExist:
            return {'success': False, 'error': 'IP地址不存在'}

        if ip.status == 'allocated' and ip.device:
            return {'success': False, 'error': f'IP已被 {ip.device.name} 占用'}
        if ip.status == 'reserved':
            return {'success': False, 'error': 'IP已被预留，不能分配'}

        old_value = {
            'status': ip.status,
            'device_id': ip.device_id,
            'hostname': ip.hostname,
            'description': ip.description,
        }

        try:
            ip.allocate(device=device, user=user, hostname=hostname, description=description)
        except ValueError as e:
            return {'success': False, 'error': str(e)}

        new_value = {
            'status': ip.status,
            'device_id': ip.device_id,
            'hostname': ip.hostname,
            'description': ip.description,
        }

        AllocationLog.objects.create(
            ip_address=ip_address,
            hostname=hostname,
            action='allocate',
            old_value=old_value,
            new_value=new_value,
            performed_by=user,
            notes=description
        )

        return {'success': True, 'ip': ip}

    def release_ip(self, ip_address: str, user=None, reason: str = '') -> Dict[str, any]:
        """释放IP"""
        from .models import IPAddress, AllocationLog

        try:
            ip = IPAddress.objects.get(ip_address=ip_address)
        except IPAddress.DoesNotExist:
            return {'success': False, 'error': 'IP地址不存在'}

        if ip.status == 'available':
            return {'success': False, 'error': 'IP已经是可用状态'}

        old_value = {
            'status': ip.status,
            'device_id': ip.device_id,
            'hostname': ip.hostname,
            'description': ip.description,
        }

        try:
            ip.release()
        except ValueError as e:
            return {'success': False, 'error': str(e)}

        AllocationLog.objects.create(
            ip_address=ip_address,
            hostname=ip.hostname,
            action='release',
            old_value=old_value,
            new_value={'status': 'available'},
            performed_by=user,
            notes=reason
        )

        return {'success': True, 'ip': ip}

    def reserve_ip(self, ip_address: str, user=None, description: str = '', device=None) -> Dict[str, any]:
        """预留IP"""
        from .models import IPAddress, AllocationLog

        try:
            ip = IPAddress.objects.get(ip_address=ip_address)
        except IPAddress.DoesNotExist:
            return {'success': False, 'error': 'IP地址不存在'}

        old_value = {'status': ip.status, 'description': ip.description, 'device_id': ip.device_id}

        try:
            ip.reserve(user=user, description=description, device=device)
        except ValueError as e:
            return {'success': False, 'error': str(e)}

        AllocationLog.objects.create(
            ip_address=ip_address,
            hostname=ip.hostname,
            action='reserve',
            old_value=old_value,
            new_value={'status': 'reserved', 'description': description, 'device_id': ip.device_id},
            performed_by=user,
            notes=description
        )

        return {'success': True, 'ip': ip}

    def get_ip_info(self, ip_address: str) -> Dict:
        """获取IP详细信息"""
        from .models import IPAddress

        try:
            ip = IPAddress.objects.select_related('subnet', 'device', 'allocated_by').get(ip_address=ip_address)
        except IPAddress.DoesNotExist:
            return {'success': False, 'error': 'IP地址不存在'}

        return {
            'success': True,
            'ip': {
                'id': ip.id,
                'ip_address': ip.ip_address,
                'subnet_id': ip.subnet_id,
                'subnet_cidr': ip.subnet.cidr,
                'hostname': ip.hostname,
                'mac_address': ip.mac_address,
                'description': ip.description,
                'status': ip.status,
                'status_display': ip.get_status_display(),
                'device_id': ip.device_id,
                'device_name': ip.device.name if ip.device else None,
                'allocated_at': ip.allocated_at,
                'allocated_by': ip.allocated_by.username if ip.allocated_by else None,
                'created_at': ip.created_at,
                'updated_at': ip.updated_at,
            }
        }

    def get_available_ips(self, subnet_id: int, count: int = 1) -> List['IPAddress']:
        """获取网段内可用IP列表"""
        from .models import IPAddress

        return list(
            IPAddress.objects.filter(
                subnet_id=subnet_id,
                status='available'
            )[:count]
        )

    def get_subnet_usage(self, subnet_id: int) -> Dict:
        """获取网段使用统计"""
        from .models import IPAddress, Subnet

        try:
            subnet = Subnet.objects.get(id=subnet_id)
        except Subnet.DoesNotExist:
            return {'success': False, 'error': 'Subnet不存在'}

        ips = subnet.ip_addresses.all()
        total = ips.count()
        available = ips.filter(status='available').count()
        allocated = ips.filter(status='allocated').count()
        reserved = ips.filter(status='reserved').count()

        used = allocated + reserved
        usage_rate = round(used / total * 100, 1) if total > 0 else 0

        return {
            'success': True,
            'subnet_id': subnet_id,
            'cidr': subnet.cidr,
            'name': subnet.name,
            'total_ips': total,
            'available': available,
            'allocated': allocated,
            'reserved': reserved,
            'used': used,
            'usage_rate': usage_rate,
        }

    @transaction.atomic
    def bulk_allocate(
        self,
        subnet_id: int,
        start_ip: str,
        end_ip: str,
        device=None,
        user=None,
        description: str = ''
    ) -> Dict:
        """批量分配IP范围内所有IP（原子性操作）"""
        from .models import IPAddress, Subnet

        try:
            subnet = Subnet.objects.get(id=subnet_id)
        except Subnet.DoesNotExist:
            return {'success': False, 'error': 'Subnet不存在'}

        try:
            start = ip_lib.ip_address(start_ip)
            end = ip_lib.ip_address(end_ip)
        except ValueError:
            return {'success': False, 'error': '无效的IP地址'}

        if isinstance(start, ip_lib.IPv6Address) or isinstance(end, ip_lib.IPv6Address):
            return {'success': False, 'error': '暂不支持IPv6地址'}

        if start > end:
            start, end = end, start

        subnet_network = ip_lib.ip_network(subnet.cidr, strict=False)
        start_int = int(start)
        end_int = int(end)
        network_start_int = int(subnet_network.network_address)
        network_end_int = int(subnet_network.broadcast_address)

        if start_int < network_start_int or end_int > network_end_int:
            return {'success': False, 'error': f'IP范围不在子网{subnet.cidr}内'}

        allocated = []
        failed = []
        allocated_ips = []

        current = start
        while current <= end:
            ip_str = str(current)
            result = self.allocate_ip(
                ip_address=ip_str,
                device=device,
                user=user,
                description=description
            )
            if result['success']:
                allocated.append(ip_str)
                allocated_ips.append(result['ip'])
            else:
                failed.append({'ip': ip_str, 'reason': result.get('error')})

            current = ip_lib.ip_address(int(current) + 1)

        if failed:
            raise ValueError(f'部分IP分配失败: {failed[0]["reason"]}')

        return {
            'success': True,
            'allocated': allocated,
            'allocated_count': len(allocated),
            'failed': failed,
            'failed_count': len(failed),
        }

    @transaction.atomic
    def bulk_release(self, ip_list: List[str], user=None, reason: str = '') -> Dict:
        """批量释放IP（原子性操作）"""
        released = []
        failed = []

        for ip_address in ip_list:
            result = self.release_ip(ip_address=ip_address, user=user, reason=reason)
            if result['success']:
                released.append(ip_address)
            else:
                failed.append({'ip': ip_address, 'reason': result.get('error')})

        if failed:
            raise ValueError(f'部分IP释放失败: {failed[0]["reason"]}')

        return {
            'success': True,
            'released': released,
            'released_count': len(released),
            'failed': failed,
            'failed_count': len(failed),
        }

    def sync_scan_results(self, subnet_id: int, scan_results: List[Dict]) -> Dict:
        """将扫描结果同步到IPAM"""
        from .models import IPAddress, AllocationLog, Subnet

        try:
            subnet = Subnet.objects.get(id=subnet_id)
        except Subnet.DoesNotExist:
            return {'success': False, 'error': 'Subnet不存在'}

        created_count = 0
        updated_count = 0
        discovered_count = 0

        for result in scan_results:
            ip_str = result['ip']
            is_alive = result.get('alive', False)
            hostname = result.get('hostname', '')
            response_time = result.get('response_time')

            ip, created = IPAddress.objects.get_or_create(
                ip_address=ip_str,
                defaults={'subnet': subnet, 'status': 'allocated' if is_alive else 'available'}
            )

            if created:
                created_count += 1
            else:
                old_status = ip.status
                old_hostname = ip.hostname
                updated = False

                if is_alive and ip.status == 'available':
                    ip.status = 'allocated'
                    ip.hostname = hostname or ip.hostname
                    ip.save()
                    updated = True
                    discovered_count += 1

                    AllocationLog.objects.create(
                        ip_address=ip_str,
                        hostname=hostname,
                        action='scan_discover',
                        old_value={'status': old_status, 'hostname': old_hostname},
                        new_value={'status': 'allocated', 'hostname': ip.hostname},
                        notes=f'扫描发现，响应时间: {response_time}ms' if response_time else '扫描发现'
                    )
                elif is_alive and ip.status in ('allocated', 'reserved'):
                    ip.hostname = hostname or ip.hostname
                    if ip.hostname != old_hostname:
                        ip.save()
                        updated = True

                if updated:
                    updated_count += 1

        return {
            'success': True,
            'created': created_count,
            'updated': updated_count,
            'discovered': discovered_count,
        }

    def get_allocation_history(self, ip_address: str = None, limit: int = 100) -> List[Dict]:
        """获取分配历史"""
        from .models import AllocationLog

        queryset = AllocationLog.objects.select_related('performed_by').all()
        if ip_address:
            queryset = queryset.filter(ip_address=ip_address)

        return list(queryset[:limit].values(
            'id', 'ip_address', 'hostname', 'action', 'old_value',
            'new_value', 'performed_by__username', 'performed_at', 'notes'
        ))
