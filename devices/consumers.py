"""
WebSocket consumers for SSH connections.
"""

import json
import threading
import asyncio
import paramiko
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async


class SSHConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for SSH connections.
    Handles SSH authentication and data proxying.
    """

    async def connect(self):
        self.device_id = self.scope['url_route']['kwargs']['device_id']
        self.ssh_client = None
        self.channel = None
        self.transport = None
        self.thread = None
        self.stop_event = threading.Event()
        self.loop = asyncio.get_event_loop()
        self.group_name = f"ssh_{self.device_id}"

        await self.accept()

    async def disconnect(self, close_code):
        # Signal the thread to stop
        self.stop_event.set()

        # Clean up SSH connection
        if self.ssh_client:
            try:
                self.ssh_client.close()
            except Exception:
                pass

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)

            if data.get('action') == 'connect':
                await self.handle_connect(data)
            elif data.get('type') == 'input':
                self.handle_input(data)
            elif data.get('type') == 'resize':
                self.handle_resize(data)
        except json.JSONDecodeError:
            pass

    def handle_input(self, data):
        """Handle terminal input (synchronous)"""
        if self.channel:
            try:
                self.channel.send(data.get('data', ''))
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

    async def handle_connect(self, data):
        """Handle SSH connection request"""
        username = data.get('username')
        password = data.get('password')
        port = data.get('port', 22)

        try:
            # Get device info (wrap sync ORM call in sync_to_async)
            from devices.models import Device
            device = await sync_to_async(Device.objects.get)(id=self.device_id)
            host = device.ip_address

            # Reset stop event
            self.stop_event.clear()

            # Run SSH connection in a thread since paramiko is blocking
            def ssh_worker():
                try:
                    self.ssh_client = paramiko.SSHClient()
                    self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

                    self.ssh_client.connect(
                        hostname=host,
                        port=port,
                        username=username,
                        password=password,
                        timeout=10,
                        allow_agent=False,
                        look_for_keys=False
                    )

                    self.transport = self.ssh_client.get_transport()
                    if self.transport is None:
                        raise Exception("Failed to create transport")

                    self.channel = self.transport.open_session()
                    self.channel.invoke_shell()
                    self.channel.setblocking(0)

                    # Schedule coroutine to send connected message
                    asyncio.run_coroutine_threadsafe(
                        self.send(text_data=json.dumps({'type': 'connected'})),
                        self.loop
                    )

                    # Read loop
                    while not self.stop_event.is_set():
                        if self.channel and self.channel.recv_ready():
                            try:
                                output = self.channel.recv(65535).decode('utf-8', errors='replace')
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

                except Exception as e:
                    try:
                        asyncio.run_coroutine_threadsafe(
                            self.send(text_data=json.dumps({
                                'type': 'error',
                                'message': str(e)
                            })),
                            self.loop
                        )
                    except Exception:
                        pass

            self.thread = threading.Thread(target=ssh_worker, daemon=True)
            self.thread.start()

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
