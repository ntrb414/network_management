"""
配置管理服务。

配置查看使用 Netmiko 主链路与 Paramiko 备用链路；配置下发仍保留 Nornir 路径。
需求引用：3.1, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9
"""

from typing import List, Dict, Any, Optional
from django.core.cache import cache
from django.utils import timezone
import logging
import json

logger = logging.getLogger(__name__)

# Redis 缓存配置
REDIS_CONFIG_KEY_PREFIX = 'device_config'
REDIS_CONFIG_EXPIRE_SECONDS = 30 * 24 * 60 * 60  # 30天


class ConfigManagementService:
    """配置管理服务类"""

    def _split_config_commands(self, config: str) -> List[str]:
        """将配置文本拆分为有效命令列表"""
        return [line.strip() for line in config.splitlines() if line.strip()]

    def _render_task_config(self, task) -> str:
        """根据任务定义生成最终下发配置"""
        if task.template:
            return task.template.render(task.variables or {})
        return task.config_content or ''

    def get_current_config(self, device, use_cache=True) -> str:
        """
        获取设备当前运行配置（支持 Redis 缓存）

        Args:
            device: 设备对象
            use_cache: 是否使用缓存，默认 True

        Returns:
            设备运行配置内容
        """
        if use_cache:
            cached_config = self._get_config_from_cache(device.id, 'running')
            if cached_config:
                logger.info(f"从缓存读取设备 {device.ip_address} 运行配置")
                return cached_config

        try:
            config = self._get_config_via_ssh(device, config_type='running')
            if config:
                self._save_config_to_cache(device.id, 'running', config)
            return config
        except Exception as e:
            logger.error(f"获取设备 {device.ip_address} 运行配置失败: {e}")
            return ""

    def get_startup_config(self, device, use_cache=True) -> str:
        """
        获取设备启动配置（支持 Redis 缓存）

        Args:
            device: 设备对象
            use_cache: 是否使用缓存，默认 True

        Returns:
            设备启动配置内容
        """
        if use_cache:
            cached_config = self._get_config_from_cache(device.id, 'startup')
            if cached_config:
                logger.info(f"从缓存读取设备 {device.ip_address} 启动配置")
                return cached_config

        try:
            config = self._get_config_via_ssh(device, config_type='startup')
            if config:
                self._save_config_to_cache(device.id, 'startup', config)
            return config
        except Exception as e:
            logger.error(f"获取设备 {device.ip_address} 启动配置失败: {e}")
            return ""

    def _get_config_via_ssh(self, device, config_type='running') -> str:
        """通过适合网络设备的 SSH 方式获取配置。"""
        try:
            return self._get_config_via_netmiko(device, config_type)
        except ImportError:
            logger.warning("Netmiko库未安装，使用 Paramiko 备用方法获取配置")
            return self._get_config_via_paramiko(device, config_type)
        except Exception as e:
            logger.error(f"Netmiko 获取配置失败: {e}")
            logger.info("尝试使用 Paramiko 备用方法获取配置")
            return self._get_config_via_paramiko(device, config_type)

    def _get_config_from_cache(self, device_id: int, config_type: str) -> Optional[str]:
        """从 Redis 缓存读取配置"""
        cache_key = f"{REDIS_CONFIG_KEY_PREFIX}:{device_id}:{config_type}"
        cached_data = cache.get(cache_key)

        if cached_data:
            try:
                data = json.loads(cached_data)
                return data.get('config')
            except json.JSONDecodeError:
                logger.error(f"解析缓存数据失败: {cache_key}")
                return None
        return None

    def _save_config_to_cache(self, device_id: int, config_type: str, config: str):
        """将配置保存到 Redis 缓存"""
        cache_key = f"{REDIS_CONFIG_KEY_PREFIX}:{device_id}:{config_type}"
        cache_data = json.dumps({
            'config': config,
            'timestamp': timezone.now().isoformat()
        })
        cache.set(cache_key, cache_data, REDIS_CONFIG_EXPIRE_SECONDS)
        logger.info(f"配置已缓存: {cache_key}")

    def get_config_cache_time(self, device_id: int, config_type: str) -> Optional[str]:
        """获取配置缓存的时间戳"""
        cache_key = f"{REDIS_CONFIG_KEY_PREFIX}:{device_id}:{config_type}"
        cached_data = cache.get(cache_key)

        if cached_data:
            try:
                data = json.loads(cached_data)
                return data.get('timestamp')
            except json.JSONDecodeError:
                return None
        return None

    def backup_device_configs(self, device) -> Dict[str, Any]:
        """
        备份设备配置到 Redis（用于定时任务）

        Args:
            device: 设备对象

        Returns:
            备份结果字典
        """
        result = {
            'device_id': device.id,
            'device_name': device.name,
            'success': False,
            'running_config': None,
            'startup_config': None,
            'error': None,
            'running_config_time': None,
            'startup_config_time': None,
        }

        try:
            # 备份运行配置
            running_config = self.get_current_config(device, use_cache=False)
            if running_config:
                result['running_config'] = True
                result['running_config_time'] = timezone.now().isoformat()
                logger.info(f"设备 {device.name} 运行配置备份成功")

            # 备份启动配置
            startup_config = self.get_startup_config(device, use_cache=False)
            if startup_config:
                result['startup_config'] = True
                result['startup_config_time'] = timezone.now().isoformat()
                logger.info(f"设备 {device.name} 启动配置备份成功")

            # 改进成功判断逻辑：至少有一种配置备份成功即为成功
            result['success'] = bool(running_config or startup_config)

        except Exception as e:
            result['error'] = str(e)
            logger.error(f"备份设备 {device.name} 配置失败: {e}")

        return result

    def _get_config_via_netmiko(self, device, config_type='running') -> str:
        """通过 Netmiko 获取设备配置。"""
        from netmiko import ConnectHandler

        command = self._get_config_commands(device, config_type)
        vendor = self._detect_vendor(device)
        connection = {
            'device_type': self._map_device_type(device),
            'host': device.ip_address,
            'port': device.ssh_port or 22,
            'username': device.ssh_username,
            'password': device.ssh_password,
            'timeout': 30,
            'conn_timeout': 20,
            'auth_timeout': 20,
            'banner_timeout': 20,
            'fast_cli': False,
        }

        with ConnectHandler(**connection) as ssh:
            if vendor == 'huawei':
                ssh.send_command(
                    'screen-length 0 temporary',
                    read_timeout=15,
                    strip_prompt=False,
                    strip_command=False,
                )
            elif vendor == 'h3c':
                ssh.send_command(
                    'screen-length disable',
                    read_timeout=15,
                    strip_prompt=False,
                    strip_command=False,
                )

            config_output = ssh.send_command(
                command,
                read_timeout=60,
                strip_prompt=False,
                strip_command=False,
            )

        cleaned_config = self._clean_config_output(config_output, command)
        logger.info(f"成功通过 Netmiko 获取设备 {device.ip_address} 的 {config_type} 配置，共 {len(cleaned_config.splitlines())} 行")
        return cleaned_config

    def _get_config_via_paramiko(self, device, config_type='running') -> str:
        """
        通过 Paramiko 直接获取设备配置（备用方法）

        Args:
            device: 设备对象
            config_type: 配置类型 ('running' 或 'startup')

        Returns:
            配置内容
        """
        try:
            import paramiko
            from paramiko import SSHClient, AutoAddPolicy
            
            command = self._get_config_commands(device, config_type)
            
            # 创建SSH客户端
            ssh = SSHClient()
            ssh.set_missing_host_key_policy(AutoAddPolicy())
            
            # 连接设备
            ssh.connect(
                hostname=device.ip_address,
                port=device.ssh_port or 22,
                username=device.ssh_username,
                password=device.ssh_password,
                timeout=30,
                allow_agent=False,
                look_for_keys=False
            )
            
            logger.info(f"通过SSH连接到设备 {device.ip_address} 成功")
            
            # 执行配置获取命令
            stdin, stdout, stderr = ssh.exec_command(command, timeout=60)
            
            # 读取输出
            config_output = stdout.read().decode('utf-8', errors='ignore')
            error_output = stderr.read().decode('utf-8', errors='ignore')
            
            # 关闭连接
            ssh.close()
            
            # 检查是否有错误
            if error_output and 'Error' in error_output:
                logger.warning(f"设备 {device.ip_address} 执行命令时出现警告: {error_output}")
            
            if config_output:
                cleaned_config = self._clean_config_output(config_output, command)
                logger.info(f"成功获取设备 {device.ip_address} 的 {config_type} 配置，共 {len(cleaned_config.splitlines())} 行")
                return cleaned_config
            else:
                logger.warning(f"设备 {device.ip_address} 返回空配置")
                return ""
                
        except ImportError:
            logger.error("Paramiko库未安装，无法获取设备配置")
            return ""
        except Exception as e:
            logger.error(f"通过Paramiko获取设备 {device.ip_address} 配置失败: {e}")
            raise

    def _clean_config_output(self, output: str, command: str) -> str:
        """清理网络设备回显中的空字节、分页标记、命令回显和提示符。"""
        cleaned_lines = []

        for raw_line in output.replace('\x00', '').splitlines():
            line = raw_line.replace('---- More ----', '').rstrip()
            stripped = line.strip()

            if not stripped:
                cleaned_lines.append('')
                continue

            if stripped == command or stripped.startswith('Press '):
                continue

            if (stripped.startswith('<') and stripped.endswith('>')) or (stripped.startswith('[') and stripped.endswith(']')):
                continue

            cleaned_lines.append(line)

        return '\n'.join(cleaned_lines).strip()

    def _detect_vendor(self, device) -> str:
        """检测设备厂商"""
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

    def _map_device_type(self, device) -> str:
        """将设备映射到 Netmiko 设备类型。"""
        vendor = self._detect_vendor(device)

        if vendor == 'h3c':
            return 'hp_comware'
        else:
            return 'huawei'

    def _get_config_commands(self, device, config_type='running') -> str:
        """根据设备厂商和配置类型获取对应的命令"""
        vendor = self._detect_vendor(device)

        commands_map = {
            ('huawei', 'running'): 'display current-configuration',
            ('huawei', 'startup'): 'display saved-configuration',
            ('h3c', 'running'): 'display current-configuration',
            ('h3c', 'startup'): 'display saved-configuration',
        }

        key = (vendor, config_type)
        return commands_map.get(key, 'display current-configuration')

    def deploy_config(self, device, config: str) -> Dict[str, Any]:
        """
        通过 Nornir 下发配置到设备

        Args:
            device: 设备对象
            config: 配置内容

        Returns:
            执行结果字典
        """
        commands = self._split_config_commands(config)

        if not commands:
            return {
                'success': False,
                'device_id': device.id,
                'device_name': device.name,
                'error': '配置内容为空',
            }

        try:
            from nornir import InitNornir
            from nornir_netmiko.tasks import netmiko_send_config

            vendor = self._detect_vendor(device)

            nr = InitNornir(
                runner={
                    'plugin': 'nornir_runner.SerialRunner'},
                inventory={
                    'plugin': 'nornir.plugins.inventory.simple.SimpleInventory',
                    'options': {
                        'hosts': {
                            device.ip_address: {
                                'hostname': device.ip_address,
                                'username': device.ssh_username,
                                'password': device.ssh_password,
                                'port': device.ssh_port or 22,
                                'device_type': self._map_device_type(device),
                            }
                        }
                    }
                }
            )

            disable_paging_cmd = 'screen-length 0 temporary' if vendor == 'huawei' else 'screen-length disable'

            if disable_paging_cmd:
                nr.run(
                    task=netmiko_send_config,
                    config_commands=[disable_paging_cmd],
                    read_timeout=30
                )

            result = nr.run(
                task=netmiko_send_config,
                config_commands=commands,
                read_timeout=30
            )

            for host, task_result in result.items():
                if task_result[0].failed:
                    raise Exception(task_result[0].exception)
                return {
                    'success': True,
                    'device_id': device.id,
                    'device_name': device.name,
                    'output': task_result[0].result,
                }

        except ImportError:
            logger.warning("Nornir库未安装，使用 Netmiko 备用方式下发配置")
            return self._deploy_config_via_netmiko(device, commands)
        except Exception as e:
            logger.error(f"Nornir 配置下发失败: {e}")
            logger.info("尝试使用 Netmiko 备用方式下发配置")
            return self._deploy_config_via_netmiko(device, commands)

    def _deploy_config_via_netmiko(self, device, commands: List[str]) -> Dict[str, Any]:
        """通过 Netmiko 直接下发配置"""
        try:
            from netmiko import ConnectHandler

            vendor = self._detect_vendor(device)
            connection = ConnectHandler(
                device_type=self._map_device_type(device),
                host=device.ip_address,
                username=device.ssh_username,
                password=device.ssh_password,
                port=device.ssh_port or 22,
                timeout=30,
                conn_timeout=30,
                auth_timeout=30,
                banner_timeout=30,
                fast_cli=False,
            )

            disable_paging_cmd = 'screen-length 0 temporary' if vendor == 'huawei' else 'screen-length disable'
            if disable_paging_cmd:
                connection.send_command_timing(disable_paging_cmd, strip_prompt=False, strip_command=False)

            output = connection.send_config_set(commands, read_timeout=30, cmd_verify=False)
            connection.disconnect()

            return {
                'success': True,
                'device_id': device.id,
                'device_name': device.name,
                'output': output,
            }
        except Exception as e:
            logger.error(f"Netmiko 配置下发失败: {e}")
            return {
                'success': False,
                'device_id': device.id,
                'device_name': device.name,
                'error': str(e),
            }

    def deploy_config_batch(self, devices: List, config: str) -> Dict[str, Any]:
        """
        批量下发配置到多个设备

        Args:
            devices: 设备列表
            config: 配置内容

        Returns:
            执行结果字典
        """
        success_count = 0
        failure_count = 0
        results = []

        for device in devices:
            result = self.deploy_config(device, config)
            if result['success']:
                success_count += 1
                results.append({
                    'device_ip': device.ip_address,
                    'device_name': device.name,
                    'success': True,
                    'output': result.get('output', ''),
                })
            else:
                failure_count += 1
                results.append({
                    'device_ip': device.ip_address,
                    'device_name': device.name,
                    'success': False,
                    'error': result.get('error', ''),
                })

        return {
            'success': failure_count == 0,
            'total': len(devices),
            'success_count': success_count,
            'failure_count': failure_count,
            'results': results,
        }

    def execute_task(self, task) -> Dict[str, Any]:
        """
        执行配置任务

        Args:
            task: ConfigTask对象

        Returns:
            执行结果字典
        """
        from .models import ConfigTaskResult

        # 获取配置内容
        rendered_config = self._render_task_config(task)

        if not rendered_config:
            return {
                'success': False,
                'error': '配置内容为空',
            }

        # 更新任务状态
        task.status = 'executing'
        task.executed_at = timezone.now()
        task.save()

        # 同一任务再次执行时，仅保留本次执行结果，避免历史结果重复展示。
        ConfigTaskResult.objects.filter(task=task).delete()

        results = []
        success_count = 0
        failure_count = 0

        for device in task.devices.all():
            result = self.deploy_config(device, rendered_config)

            ConfigTaskResult.objects.create(
                task=task,
                device=device,
                success=result['success'],
                config_content=rendered_config,
                error_message=result.get('error', ''),
            )

            if result['success']:
                success_count += 1
            else:
                failure_count += 1

        # 更新任务状态
        if failure_count == 0:
            task.status = 'completed'
        elif success_count == 0:
            task.status = 'failed'
        else:
            task.status = 'completed'

        task.save()

        return {
            'success': task.status == 'completed',
            'task_id': task.id,
            'total_devices': task.devices.count(),
            'success_count': success_count,
            'failure_count': failure_count,
        }
