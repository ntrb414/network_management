"""
设备发现服务

提供设备发现相关功能：IP范围扫描、LLDP发现、手动添加设备、设备详细信息获取。
需求引用：1.1, 1.2, 1.3, 1.4
"""

import socket
import subprocess
from ipaddress import ip_network, ip_address
from typing import List, Optional, Dict, Any

from .models import Device, Port


class DeviceDiscoveryService:
    """设备发现服务类"""

    # 常见网络设备的默认端口和特征
    DEVICE_SIGNATURES = {
        'router': {
            'ports': [22, 23, 80, 443],
            'keywords': ['router', 'cisco', 'juniper', 'huawei', 'routeros'],
        },
        'switch': {
            'ports': [22, 23, 80, 443],
            'keywords': ['switch', 'catalyst', 'procurve', 'powerconnect'],
        },
        'ap': {
            'ports': [22, 80, 443, 8080],
            'keywords': ['ap', 'access point', 'unifi', 'aironet', 'cAP'],
        },
        'ac': {
            'ports': [22, 80, 443],
            'keywords': ['controller', 'wireless', 'wlan', 'ac'],
        },
    }

    def scan_ip_range(self, start_ip: str, end_ip: str) -> List[Dict[str, Any]]:
        """
        扫描IP地址范围发现设备

        Args:
            start_ip: 起始IP地址
            end_ip: 结束IP地址

        Returns:
            发现设备的信息列表

        Requirements: 1.1, 1.4
        """
        discovered_devices = []

        try:
            # 解析IP范围
            start = ip_address(start_ip)
            end = ip_address(end_ip)

            # 将IP转换为整数进行遍历
            start_int = int(start)
            end_int = int(end)

            # 限制扫描范围，防止大规模扫描
            max_scan = min(end_int - start_int + 1, 256)

            for i in range(max_scan):
                current_ip_int = start_int + i
                current_ip = str(ip_address(current_ip_int))

                # 检查主机是否存活
                if self._is_host_alive(current_ip):
                    # 尝试识别设备类型
                    device_info = self._identify_device(current_ip)
                    if device_info:
                        discovered_devices.append(device_info)

        except Exception as e:
            print(f"扫描IP范围时发生错误: {e}")

        return discovered_devices

    def _is_host_alive(self, ip: str, timeout: int = 2) -> bool:
        """
        检查主机是否存活

        Args:
            ip: 主机IP地址
            timeout: 超时时间（秒）

        Returns:
            主机是否存活
        """
        try:
            # 使用ping命令检查主机是否存活
            result = subprocess.run(
                ['ping', '-c', '1', '-W', str(timeout), ip],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout + 1
            )
            return result.returncode == 0
        except Exception:
            return False

    def _identify_device(self, ip: str) -> Optional[Dict[str, Any]]:
        """
        识别设备类型

        Args:
            ip: 设备IP地址

        Returns:
            设备信息字典，如果无法识别则返回None
        """
        # 尝试通过SSH端口识别
        device_type = self._detect_via_ports(ip)

        if device_type:
            return {
                'ip_address': ip,
                'device_type': device_type,
                'status': 'online',
                'name': f'{device_type}-{ip.replace(".", "-")}',
            }

        return None

    def _detect_via_ports(self, ip: str) -> Optional[str]:
        """
        通过端口检测识别设备类型

        Args:
            ip: 设备IP地址

        Returns:
            设备类型，如果无法识别则返回None
        """
        # 常见设备端口
        common_ports = {
            22: 'ssh',
            23: 'telnet',
            80: 'http',
            443: 'https',
            161: 'snmp',
        }

        for port, service in common_ports.items():
            if self._check_port(ip, port):
                # 根据开放端口和服务推断设备类型
                if service == 'snmp':
                    return 'router'  # SNMP通常是路由器/交换机
                return self._infer_device_type(ip)

        return None

    def _check_port(self, ip: str, port: int, timeout: int = 2) -> bool:
        """
        检查端口是否开放

        Args:
            ip: 目标IP地址
            port: 端口号
            timeout: 超时时间

        Returns:
            端口是否开放
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            result = sock.connect_ex((ip, port))
            return result == 0
        except Exception:
            return False
        finally:
            sock.close()

    def _infer_device_type(self, ip: str) -> str:
        """
        根据IP特征推断设备类型

        Args:
            ip: 设备IP地址

        Returns:
            设备类型
        """
        # 简单的设备类型推断逻辑
        # 实际生产环境中应该通过SNMP或SSH获取更准确的信息

        # 尝试获取主机名
        try:
            hostname, _, _ = socket.gethostbyaddr(ip)
            hostname_lower = hostname.lower()

            for device_type, sig in self.DEVICE_SIGNATURES.items():
                for keyword in sig['keywords']:
                    if keyword in hostname_lower:
                        return device_type
        except Exception:
            pass

        # 默认返回路由器
        return 'router'

    def discover_via_lldp(self, seed_device: Device) -> List[Dict[str, Any]]:
        """
        通过LLDP协议发现相邻设备

        Args:
            seed_device: 种子设备

        Returns:
            发现的相邻设备列表

        Requirements: 1.2, 1.4
        """
        discovered_devices = []

        try:
            # 尝试导入scapy
            from scapy.all import LLC, SNAP, LLDP, Dot1BR, Ether
            import struct
        except ImportError:
            # 如果没有scapy，返回空列表
            print("警告: scapy库未安装，无法进行LLDP发现")
            return []

        # LLDP帧的目标MAC地址
        LLDP_MULTICAST_MAC = "01:80:c2:00:00:0e"

        # 发送LLDP帧到种子设备
        # 注意: 这需要网络访问权限和正确的网络接口
        try:
            # 构建LLDP帧 (最简单的LLDP帧)
            # 实际环境中需要构造完整的LLDP TLV
            lldp_frame = Ether(src=self._get_random_mac(), dst=LLDP_MULTICAST_MAC)

            # 在实际环境中，需要发送帧到网络并接收响应
            # 这里提供一个框架，实际实现需要根据具体网络设备调整
            discovered_devices = self._parse_lldp_response(seed_device)

        except Exception as e:
            print(f"LLDP发现失败: {e}")

        return discovered_devices

    def _get_random_mac(self) -> str:
        """生成随机MAC地址用于发送LLDP帧"""
        import random
        return ":".join([f"{random.randint(0, 255):02x}" for _ in range(6)])

    def _parse_lldp_response(self, seed_device: Device) -> List[Dict[str, Any]]:
        """
        解析LLDP响应

        Args:
            seed_device: 种子设备

        Returns:
            发现的相邻设备列表
        """
        # 这是一个占位实现
        # 实际实现需要:
        # 1. 监听网络上的LLDP帧
        # 2. 解析Chassis ID TLV
        # 3. 解析Port ID TLV
        # 4. 解析System Name TLV
        # 5. 解析System Description TLV

        # 返回空列表，实际需要网络设备响应
        return []

    def _parse_lldp_tlv(self, tlv_data: bytes) -> Dict[str, Any]:
        """
        解析LLDP TLV (Type-Length-Value)

        Args:
            tlv_data: TLV数据

        Returns:
            解析后的TLV信息
        """
        if len(tlv_data) < 2:
            return {}

        # 解析TLV头
        tlv_type = (tlv_data[0] >> 1) & 0x3F
        tlv_length = ((tlv_data[0] & 0x01) << 8) | tlv_data[1]

        if len(tlv_data) < tlv_length + 2:
            return {}

        tlv_value = tlv_data[2:2 + tlv_length]

        result = {
            'type': tlv_type,
            'length': tlv_length,
        }

        # 根据TLV类型解析值
        if tlv_type == 1:  # Chassis ID
            result['subtype'] = tlv_value[0]
            result['chassis_id'] = tlv_value[1:].hex()
        elif tlv_type == 2:  # Port ID
            result['subtype'] = tlv_value[0]
            result['port_id'] = tlv_value[1:].decode('utf-8', errors='ignore')
        elif tlv_type == 4:  # System Name
            result['system_name'] = tlv_value.decode('utf-8', errors='ignore')
        elif tlv_type == 5:  # System Description
            result['system_description'] = tlv_value.decode('utf-8', errors='ignore')
        elif tlv_type == 6:  # Management Address
            result['management_address'] = tlv_value.hex()

        return result

    def add_device_manually(self, device_info: Dict[str, Any]) -> Device:
        """
        手动添加设备

        Args:
            device_info: 设备信息字典

        Returns:
            创建的设备对象

        Requirements: 1.3
        """
        device = Device.objects.create(
            name=device_info.get('name'),
            device_type=device_info.get('device_type', 'router'),
            ip_address=device_info.get('ip_address'),
            status=device_info.get('status', 'preparing'),
            location=device_info.get('location', ''),
            model=device_info.get('model', ''),
            ssh_port=device_info.get('ssh_port', 22),
            ssh_username=device_info.get('ssh_username', ''),
            ssh_password=device_info.get('ssh_password', ''),
            snmp_community=device_info.get('snmp_community', ''),
            layer=device_info.get('layer'),
        )
        return device

    def get_device_details(self, device: Device) -> Dict[str, Any]:
        """
        获取设备详细信息

        Args:
            device: 设备对象

        Returns:
            设备详细信息字典

        Requirements: 1.4
        """
        details = {
            'id': device.id,
            'name': device.name,
            'device_type': device.device_type,
            'model': device.model,
            'ip_address': device.ip_address,
            'status': device.status,
            'location': device.location,
            'layer': device.layer,
            'ports': [],
        }

        # 获取端口信息
        ports = device.ports.all()
        for port in ports:
            details['ports'].append({
                'name': port.name,
                'port_type': port.port_type,
                'status': port.status,
                'speed': port.speed,
                'mac_address': port.mac_address,
            })

        # 尝试通过SSH获取更多信息
        if device.status == 'online' and device.ssh_username:
            try:
                ssh_info = self._get_device_info_via_ssh(device)
                if ssh_info:
                    details.update(ssh_info)
            except Exception as e:
                print(f"通过SSH获取设备信息失败: {e}")

        return details

    def _get_device_info_via_ssh(self, device: Device) -> Optional[Dict[str, Any]]:
        """
        通过SSH获取设备信息

        Args:
            device: 设备对象

        Returns:
            设备信息字典
        """
        # 实际实现需要使用Netmiko库
        # 这里返回None，让调用者处理
        return None
