"""
配置管理服务。
配置查看使用Netmiko；配置下发Nornir路径。
"""

from typing import List, Dict, Any, Optional
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
import logging
import json
import os
import tempfile
import time

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

    def render_template(self, template, variables: Optional[Dict[str, Any]] = None) -> str:
        """渲染模板内容。"""
        variables = variables or {}
        try:
            from jinja2 import Template
            return Template(template.template_content).render(**variables)
        except Exception:
            return template.render(variables)

    def validate_template(self, template, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """校验模板变量并尝试渲染。"""
        variables = variables or {}
        required = []
        schema = getattr(template, 'variables_schema', None)
        if isinstance(schema, dict):
            required = schema.get('required', []) or []

        missing = [name for name in required if not variables.get(name)]
        if missing:
            return {
                'valid': False,
                'errors': [f"缺少必填变量: {', '.join(missing)}"],
            }

        try:
            self.render_template(template, variables)
            return {
                'valid': True,
                'errors': [],
            }
        except Exception as exc:
            return {
                'valid': False,
                'errors': [str(exc)],
            }

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
        # 备份设备配置，返回实际的配置内容文本
        result = {
            'device_id': device.id,
            'device_name': device.name,
            'success': False,
            'running_config_content': None,
            'startup_config_content': None,
            'error': None,
            'running_config_time': None,
            'startup_config_time': None,
        }

        try:
            # 备份运行配置
            running_config = self.get_current_config(device, use_cache=False)
            if running_config:
                result['running_config_content'] = running_config
                result['running_config_time'] = timezone.now().isoformat()
                logger.info(f"设备 {device.name} 运行配置备份成功")

            # 备份启动配置
            startup_config = self.get_startup_config(device, use_cache=False)
            if startup_config:
                result['startup_config_content'] = startup_config
                result['startup_config_time'] = timezone.now().isoformat()
                logger.info(f"设备 {device.name} 启动配置备份成功")

            # 至少有一种配置备份成功即为成功
            result['success'] = bool(running_config or startup_config)

        except Exception as error:
            result['error'] = str(error)
            logger.error(f"备份设备 {device.name} 配置失败: {error}")

        return result

    def save_device_configs(self, device) -> Dict[str, Any]:
        # 在设备上执行 save 命令保存配置，然后获取 running-config 和 startup-config
        # H3C 设备执行 save force（无需确认）
        # 华为设备执行 save（需要交互确认 y）
        from nornir import InitNornir
        from nornir_netmiko.tasks import netmiko_save_config

        device_vendor = self._detect_vendor(device)

        # 构造 Nornir inventory（单设备）
        inventory = self._build_simple_inventory_files([device])

        nornir_instance = InitNornir(
            runner={'plugin': 'threaded', 'options': {'num_workers': 1}},
            inventory={'plugin': 'SimpleInventory', 'options': inventory}
        )

        save_success = False
        save_output = ''
        try:
            # 根据设备厂商选择 save 方式
            if device_vendor == 'huawei':
                save_result = nornir_instance.run(
                    task=netmiko_save_config,
                    cmd='save',
                    confirm=True,
                    confirm_response='y',
                )
            elif device_vendor == 'h3c':
                save_result = nornir_instance.run(
                    task=netmiko_save_config,
                    cmd='save force',
                )
            else:
                save_result = nornir_instance.run(
                    task=netmiko_save_config,
                    cmd='write memory',
                )

            # 检查 Nornir 结果，提取可序列化的字符串输出
            for host_name, host_result in save_result.items():
                if host_result.failed:
                    # 提取失败原因
                    exc = getattr(host_result, 'exception', None)
                    save_output = str(exc) if exc else '保存配置失败'
                    break
                result_val = getattr(host_result, 'result', None)
                save_output = str(result_val) if result_val is not None else ''
                save_success = True
            else:
                # 循环正常结束（没有 break）
                save_success = True

        except Exception as e:
            save_success = False
            save_output = str(e)
            logger.error(f"设备 {device.name} 保存配置异常: {e}")
        finally:
            # 关闭 Nornir 连接，清理临时 inventory 文件
            try:
                nornir_instance.close_connections()
            except Exception:
                pass
            self._cleanup_temp_inventory_files(inventory)

        if not save_success:
            return {
                'success': False,
                'device_id': device.id,
                'device_name': device.name,
                'error': save_output,
                'running_config': '',
                'startup_config': '',
            }

        # save 成功后拉取设备配置
        try:
            running_config = self.get_current_config(device, use_cache=False)
        except Exception as e:
            running_config = ''
            logger.error(f"设备 {device.name} 获取运行配置失败: {e}")

        try:
            startup_config = self.get_startup_config(device, use_cache=False)
        except Exception as e:
            startup_config = ''
            logger.error(f"设备 {device.name} 获取启动配置失败: {e}")

        return {
            'success': True,
            'device_id': device.id,
            'device_name': device.name,
            'save_output': save_output,
            'running_config': running_config,
            'startup_config': startup_config,
        }

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

    def _write_temp_inventory_file(self, data: Dict[str, Any]) -> str:
        """写入临时 inventory 文件并返回路径。"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as temp_file:
            json.dump(data, temp_file)
            temp_file.flush()
            return temp_file.name

    def _build_simple_inventory_files(self, devices: List) -> Dict[str, str]:
        """按本次设备集合构建 SimpleInventory 临时文件。"""
        connect_timeout = getattr(settings, 'CONFIG_DEPLOY_CONNECT_TIMEOUT', 15)
        auth_timeout = getattr(settings, 'CONFIG_DEPLOY_AUTH_TIMEOUT', 15)
        banner_timeout = getattr(settings, 'CONFIG_DEPLOY_BANNER_TIMEOUT', 15)
        read_timeout = getattr(settings, 'CONFIG_DEPLOY_READ_TIMEOUT', 30)

        hosts_data = {}
        for device in devices:
            host_name = f"device_{device.id}"
            hosts_data[host_name] = {
                'hostname': device.ip_address,
                'username': device.ssh_username,
                'password': device.ssh_password,
                'port': device.ssh_port or 22,
                'platform': self._map_device_type(device),
                'data': {
                    'device_id': device.id,
                    'device_name': device.name,
                },
                'connection_options': {
                    'netmiko': {
                        'extras': {
                            'timeout': connect_timeout,
                            'conn_timeout': connect_timeout,
                            'auth_timeout': auth_timeout,
                            'banner_timeout': banner_timeout,
                            'read_timeout_override': read_timeout,
                            'fast_cli': False,
                        }
                    }
                }
            }

        return {
            'host_file': self._write_temp_inventory_file(hosts_data),
            'group_file': self._write_temp_inventory_file({}),
            'defaults_file': self._write_temp_inventory_file({}),
        }

    def _cleanup_temp_inventory_files(self, inventory_options: Dict[str, str]):
        """清理 SimpleInventory 临时文件。"""
        for option_name in ('host_file', 'group_file', 'defaults_file'):
            file_path = inventory_options.get(option_name)
            if not file_path:
                continue
            try:
                os.remove(file_path)
            except OSError as exc:
                logger.warning(f"清理临时 inventory 文件失败 {file_path}: {exc}")

    def _build_batch_error_response(self, devices: List, error: str) -> Dict[str, Any]:
        """构造批量下发统一失败结构。"""
        return {
            'success': False,
            'total': len(devices),
            'success_count': 0,
            'failure_count': len(devices),
            'results': [
                {
                    'device_id': device.id,
                    'device_ip': device.ip_address,
                    'device_name': device.name,
                    'success': False,
                    'error': error,
                }
                for device in devices
            ],
        }

    def deploy_config(self, device, config: str) -> Dict[str, Any]:
     
        batch_result = self.deploy_config_batch([device], config)
        if batch_result['results']:
            return batch_result['results'][0]

        return {
            'success': False,
            'device_id': device.id,
            'device_name': device.name,
            'error': '未获取到下发结果',
        }

    def _deploy_config_via_netmiko(self, device, commands: List[str]) -> Dict[str, Any]:
        """通过 Netmiko 直接下发配置"""
        try:
            from netmiko import ConnectHandler

            vendor = self._detect_vendor(device)
            connect_timeout = getattr(settings, 'CONFIG_DEPLOY_CONNECT_TIMEOUT', 15)
            auth_timeout = getattr(settings, 'CONFIG_DEPLOY_AUTH_TIMEOUT', 15)
            banner_timeout = getattr(settings, 'CONFIG_DEPLOY_BANNER_TIMEOUT', 15)
            read_timeout = getattr(settings, 'CONFIG_DEPLOY_READ_TIMEOUT', 30)

            connection = ConnectHandler(
                device_type=self._map_device_type(device),
                host=device.ip_address,
                username=device.ssh_username,
                password=device.ssh_password,
                port=device.ssh_port or 22,
                timeout=connect_timeout,
                conn_timeout=connect_timeout,
                auth_timeout=auth_timeout,
                banner_timeout=banner_timeout,
                fast_cli=False,
            )

            disable_paging_cmd = 'screen-length 0 temporary' if vendor == 'huawei' else 'screen-length disable'
            if disable_paging_cmd:
                connection.send_command_timing(disable_paging_cmd, strip_prompt=False, strip_command=False)

            output = connection.send_config_set(commands, read_timeout=read_timeout, cmd_verify=False)
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
       
        start_time = time.perf_counter()
        devices = list(devices)
        if not devices:
            return {
                'success': True,
                'total': 0,
                'success_count': 0,
                'failure_count': 0,
                'results': [],
            }

        commands = self._split_config_commands(config)
        if not commands:
            return self._build_batch_error_response(devices, '配置内容为空')

        try:
            from nornir import InitNornir
            from nornir_netmiko.tasks import netmiko_send_config
        except ImportError:
            logger.error("Nornir库未安装，无法执行批量并发下发")
            return self._build_batch_error_response(devices, 'Nornir依赖未安装')

        workers = getattr(settings, 'CONFIG_DEPLOY_NORNIR_WORKERS', 20)
        read_timeout = getattr(settings, 'CONFIG_DEPLOY_READ_TIMEOUT', 30)

        valid_devices = []
        invalid_results = {}
        for device in devices:
            missing_fields = []
            if not device.ip_address:
                missing_fields.append('IP地址')
            if not device.ssh_username:
                missing_fields.append('SSH用户名')
            if not device.ssh_password:
                missing_fields.append('SSH密码')

            if missing_fields:
                invalid_results[device.id] = {
                    'device_id': device.id,
                    'device_ip': device.ip_address,
                    'device_name': device.name,
                    'success': False,
                    'error': f"缺少SSH连接信息: {', '.join(missing_fields)}",
                }
                continue

            valid_devices.append(device)

        if not valid_devices:
            elapsed = time.perf_counter() - start_time
            logger.warning(f"批量配置下发被跳过，所有设备SSH信息不完整: total={len(devices)}, elapsed={elapsed:.2f}s")
            return {
                'success': False,
                'total': len(devices),
                'success_count': 0,
                'failure_count': len(devices),
                'results': [invalid_results[device.id] for device in devices],
            }

        active_workers = max(1, min(workers, len(valid_devices)))
        logger.info(
            f"开始批量配置下发: total={len(devices)}, valid={len(valid_devices)}, "
            f"invalid={len(invalid_results)}, workers={active_workers}, commands={len(commands)}"
        )

        inventory_options = {}
        nornir_results = {}
        try:
            inventory_options = self._build_simple_inventory_files(valid_devices)

            nr = InitNornir(
                runner={
                    'plugin': 'threaded',
                    'options': {
                        'num_workers': active_workers,
                    },
                },
                inventory={
                    'plugin': 'SimpleInventory',
                    'options': inventory_options,
                }
            )

            nornir_result = nr.run(
                task=netmiko_send_config,
                config_commands=commands,
                read_timeout=read_timeout,
                cmd_verify=False,
                raise_on_error=False,
            )

            for device in valid_devices:
                host_name = f"device_{device.id}"
                host_result = nornir_result.get(host_name)

                if not host_result:
                    nornir_results[device.id] = {
                        'device_id': device.id,
                        'device_ip': device.ip_address,
                        'device_name': device.name,
                        'success': False,
                        'error': '未获取到设备执行结果',
                    }
                    continue

                if host_result.failed:
                    error_message = ''
                    for task_result in host_result:
                        if task_result.failed:
                            error_message = str(task_result.exception or task_result.result)
                            break
                    if not error_message:
                        error_message = '配置下发失败'

                    nornir_results[device.id] = {
                        'device_id': device.id,
                        'device_ip': device.ip_address,
                        'device_name': device.name,
                        'success': False,
                        'error': error_message,
                    }
                    continue

                output_parts = [str(task_result.result) for task_result in host_result if task_result.result]
                nornir_results[device.id] = {
                    'device_id': device.id,
                    'device_ip': device.ip_address,
                    'device_name': device.name,
                    'success': True,
                    'output': '\n'.join(output_parts),
                }
        except Exception as exc:
            logger.error(f"Nornir 批量配置下发失败: {exc}")
            for device in valid_devices:
                nornir_results[device.id] = {
                    'device_id': device.id,
                    'device_ip': device.ip_address,
                    'device_name': device.name,
                    'success': False,
                    'error': str(exc),
                }
        finally:
            if inventory_options:
                self._cleanup_temp_inventory_files(inventory_options)

        success_count = 0
        failure_count = 0
        results = []

        for device in devices:
            result = invalid_results.get(device.id) or nornir_results.get(device.id) or {
                'device_id': device.id,
                'device_ip': device.ip_address,
                'device_name': device.name,
                'success': False,
                'error': '未获取到设备执行结果',
            }

            if result['success']:
                success_count += 1
            else:
                failure_count += 1

            results.append(result)

        elapsed = time.perf_counter() - start_time
        logger.info(
            f"批量配置下发完成: total={len(devices)}, success={success_count}, "
            f"failed={failure_count}, elapsed={elapsed:.2f}s"
        )

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

        devices = list(task.devices.all())
        batch_result = self.deploy_config_batch(devices, rendered_config)

        success_count = batch_result.get('success_count', 0)
        failure_count = batch_result.get('failure_count', 0)
        device_map = {device.id: device for device in devices}

        for result in batch_result.get('results', []):
            device = device_map.get(result.get('device_id'))
            if not device:
                continue

            ConfigTaskResult.objects.create(
                task=task,
                device=device,
                success=result['success'],
                config_content=rendered_config,
                error_message=result.get('error', ''),
            )

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
