"""
WebSocket consumers for SSH connections.
"""

import json
import threading
import asyncio
import time
import socket
import logging
import paramiko
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async

from accounts.permissions import is_readonly_user, is_readonly_websocket_allowed

logger = logging.getLogger(__name__)

IDLE_TIMEOUT = 300  # 300秒无操作自动断开


class SSHConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for SSH connections.
    Handles SSH authentication and data proxying.
    Supports reconnect and idle timeout (300s).
    """

    async def connect(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return

        if is_readonly_user(user) and not is_readonly_websocket_allowed(self.scope.get('path', '')):
            await self.close(code=4403)
            return

        self.device_id = self.scope['url_route']['kwargs']['device_id']
        self.ssh_client = None
        self.channel = None
        self.transport = None
        self.thread = None
        self.stop_event = threading.Event()
        self.loop = asyncio.get_event_loop()
        self._last_active = time.time()
        self._timeout_task = None
        self._conn_params = {}
        await self.accept()

    async def disconnect(self, close_code):
        await self._cleanup_ssh()
        if self._timeout_task:
            self._timeout_task.cancel()

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            action = data.get('action') or data.get('type')

            if action == 'connect':
                await self.handle_connect(data)
            elif action == 'reconnect':
                await self.handle_reconnect()
            elif action == 'input':
                self._last_active = time.time()
                self.handle_input(data)
            elif action == 'resize':
                self.handle_resize(data)
        except json.JSONDecodeError:
            pass

    def handle_input(self, data):
        """Handle terminal input (synchronous)"""
        if self.channel:
            try:
                input_data = data.get('data', '')
                if isinstance(input_data, str):
                    input_data = input_data.encode('utf-8')
                self.channel.send(input_data)
            except Exception:
                pass

    def handle_resize(self, data):
        """Handle terminal resize (synchronous)"""
        if self.channel:
            try:
                self.channel.resize_pty(
                    width=data.get('cols', 80),
                    height=data.get('rows', 24)
                )
            except Exception:
                pass

    async def _cleanup_ssh(self):
        """关闭当前 SSH 连接并回收资源"""
        self.stop_event.set()
        if self.ssh_client:
            try:
                self.ssh_client.close()
            except Exception:
                pass
        self.ssh_client = None
        self.channel = None
        self.transport = None

    async def handle_reconnect(self):
        """断开当前连接并用保存的参数重新连接"""
        if not self._conn_params:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': '没有可用的连接参数，请重新输入凭据'
            }))
            return
        await self._cleanup_ssh()
        self.stop_event.clear()
        await self.send(text_data=json.dumps({'type': 'reconnecting'}))
        await self.handle_connect(self._conn_params)

    async def _start_idle_watchdog(self):
        """空闲超时监控协程，300s 无操作则断开"""
        try:
            while True:
                await asyncio.sleep(10)
                idle = time.time() - self._last_active
                remaining = int(IDLE_TIMEOUT - idle)
                if idle >= IDLE_TIMEOUT:
                    await self.send(text_data=json.dumps({
                        'type': 'timeout',
                        'message': '连接已因 300 秒无操作而断开'
                    }))
                    await self._cleanup_ssh()
                    return
                if remaining <= 60:
                    await self.send(text_data=json.dumps({
                        'type': 'idle_warning',
                        'remaining': remaining
                    }))
        except asyncio.CancelledError:
            pass

    async def handle_connect(self, data):
        """Handle SSH connection request"""
        username = data.get('username')
        password = data.get('password')
        port = data.get('port', 22)

        try:
            from devices.models import Device
            device = await sync_to_async(Device.objects.get)(id=self.device_id)
            host = device.ip_address

            self._conn_params = {
                'action': 'connect',
                'username': username,
                'password': password,
                'port': port,
            }
            self._last_active = time.time()
            self.stop_event.clear()

            def ssh_worker():
                try:
                    self.ssh_client = paramiko.SSHClient()
                    self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

                    # 兼容旧设备：启用 ssh-rsa 主机密钥算法（H3C/华为旧设备需要）
                    # 现代SSH客户端默认禁用ssh-rsa，但旧网络设备只支持此算法
                    self.ssh_client._transport = None  # 初始化transport属性

                    # 配置兼容旧版 SSH 算法（支持 OpenSSH 8.8+ 连接旧设备）
                    # 禁用新版算法，强制使用 ssh-rsa 等旧算法
                    disabled_algorithms = {
                        'pubkeys': [
                            'rsa-sha2-256',
                            'rsa-sha2-512',
                            'rsa-sha2-256-cert-v01@openssh.com',
                            'rsa-sha2-512-cert-v01@openssh.com',
                        ],
                        'keys': [
                            'rsa-sha2-256',
                            'rsa-sha2-512',
                        ],
                        'kex': [
                            'curve25519-sha256',
                            'curve25519-sha256@libssh.org',
                            'ecdh-sha2-nistp256',
                            'ecdh-sha2-nistp384',
                            'ecdh-sha2-nistp521',
                            'diffie-hellman-group-exchange-sha256',
                        ],
                    }

                    # 设置更长的连接超时
                    self.ssh_client.connect(
                        hostname=host,
                        port=port,
                        username=username,
                        password=password,
                        timeout=15,
                        banner_timeout=15,
                        auth_timeout=15,
                        allow_agent=False,
                        look_for_keys=False,
                        disabled_algorithms=disabled_algorithms
                    )

                    self.transport = self.ssh_client.get_transport()
                    if self.transport is None:
                        raise Exception("无法创建 SSH 传输层")

                    self.channel = self.transport.open_session()
                    # 使用标准 xterm 类型
                    self.channel.get_pty(term='xterm', width=120, height=30)
                    self.channel.invoke_shell()
                    self.channel.setblocking(0)

                    # 发送连接成功消息
                    asyncio.run_coroutine_threadsafe(
                        self.send(text_data=json.dumps({'type': 'connected'})),
                        self.loop
                    )

                    while not self.stop_event.is_set():
                        if self.channel and self.channel.recv_ready():
                            try:
                                output = self.channel.recv(65535).decode('utf-8', errors='replace')
                                if output:  # 只发送非空数据
                                    asyncio.run_coroutine_threadsafe(
                                        self.send(text_data=json.dumps({
                                            'type': 'output',
                                            'data': output
                                        })),
                                        self.loop
                                    )
                            except Exception:
                                pass
                        self.stop_event.wait(0.01)

                except EOFError as e:
                    error_msg = "SSH 连接被远程主机关闭，可能原因：设备不支持交互式 Shell 或禁用了 PTY 分配"
                    logger.warning(f"SSH EOF错误 [{host}]: {e}")
                    try:
                        asyncio.run_coroutine_threadsafe(
                            self.send(text_data=json.dumps({
                                'type': 'error',
                                'message': error_msg,
                                'error_type': 'eof'
                            })),
                            self.loop
                        )
                    except Exception:
                        pass
                except paramiko.AuthenticationException as e:
                    error_msg = "SSH 认证失败：用户名或密码错误"
                    logger.warning(f"SSH认证失败 [{host}]: {e}")
                    try:
                        asyncio.run_coroutine_threadsafe(
                            self.send(text_data=json.dumps({
                                'type': 'error',
                                'message': error_msg,
                                'error_type': 'authentication'
                            })),
                            self.loop
                        )
                    except Exception:
                        pass
                except paramiko.BadHostKeyException as e:
                    error_msg = "SSH 主机密钥验证失败"
                    logger.warning(f"SSH主机密钥验证失败 [{host}]: {e}")
                    try:
                        asyncio.run_coroutine_threadsafe(
                            self.send(text_data=json.dumps({
                                'type': 'error',
                                'message': error_msg,
                                'error_type': 'host_key'
                            })),
                            self.loop
                        )
                    except Exception:
                        pass
                except paramiko.SSHException as e:
                    error_msg = str(e)
                    if "channel" in error_msg.lower():
                        error_msg = "SSH 会话通道创建失败"
                    else:
                        error_msg = f"SSH 连接错误: {error_msg}"
                    logger.warning(f"SSH异常 [{host}]: {e}")
                    try:
                        asyncio.run_coroutine_threadsafe(
                            self.send(text_data=json.dumps({
                                'type': 'error',
                                'message': error_msg,
                                'error_type': 'ssh'
                            })),
                            self.loop
                        )
                    except Exception:
                        pass
                except socket.timeout as e:
                    error_msg = "SSH 连接超时，请检查设备网络和 SSH 服务是否正常"
                    logger.warning(f"SSH连接超时 [{host}]: {e}")
                    try:
                        asyncio.run_coroutine_threadsafe(
                            self.send(text_data=json.dumps({
                                'type': 'error',
                                'message': error_msg,
                                'error_type': 'timeout'
                            })),
                            self.loop
                        )
                    except Exception:
                        pass
                except socket.error as e:
                    error_msg = str(e)
                    if "refused" in error_msg.lower() or "connection refused" in error_msg.lower():
                        error_msg = "SSH 连接被拒绝，请检查 SSH 服务是否已启动"
                    elif "no route" in error_msg.lower():
                        error_msg = "无法连接到设备，请检查网络连接"
                    elif "network is unreachable" in error_msg.lower():
                        error_msg = "网络不可达，请检查网络配置"
                    else:
                        error_msg = f"网络连接错误: {error_msg}"
                    logger.warning(f"SSH网络错误 [{host}]: {e}")
                    try:
                        asyncio.run_coroutine_threadsafe(
                            self.send(text_data=json.dumps({
                                'type': 'error',
                                'message': error_msg,
                                'error_type': 'network'
                            })),
                            self.loop
                        )
                    except Exception:
                        pass
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"SSH未知错误 [{host}]: {e}", exc_info=True)
                    if "timed out" in error_msg.lower() or "timeout" in error_msg.lower():
                        error_msg = "SSH 连接超时，请检查设备网络和 SSH 服务是否正常"
                    elif "refused" in error_msg.lower() or "connection refused" in error_msg.lower():
                        error_msg = "SSH 连接被拒绝，请检查 SSH 服务是否已启动"
                    elif "no route" in error_msg.lower():
                        error_msg = "无法连接到设备，请检查网络连接"
                    else:
                        error_msg = f"连接错误: {error_msg}"
                    try:
                        asyncio.run_coroutine_threadsafe(
                            self.send(text_data=json.dumps({
                                'type': 'error',
                                'message': error_msg,
                                'error_type': 'unknown'
                            })),
                            self.loop
                        )
                    except Exception:
                        pass

            self.thread = threading.Thread(target=ssh_worker, daemon=True)
            self.thread.start()

            # 启动空闲超时监控
            if self._timeout_task:
                self._timeout_task.cancel()
            self._timeout_task = asyncio.ensure_future(self._start_idle_watchdog())

        except Device.DoesNotExist:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Device not found'
            }))
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Connection failed: {str(e)}'
            }))
