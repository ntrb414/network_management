import logging
import socket
import socketserver

from django.conf import settings
from django.core.management.base import BaseCommand

from logs.services import LogService

logger = logging.getLogger('logs.syslog')


class SyslogUDPHandler(socketserver.BaseRequestHandler):
    service = LogService()

    def handle(self):
        data = self.request[0]
        source_ip, _ = self.client_address

        try:
            payload = data.decode('utf-8', errors='ignore').strip('\x00\r\n')
            if not payload:
                return

            result = self.service.process_syslog_message(source_ip=source_ip, raw_message=payload)
            if not result.get('success') and not result.get('ignored'):
                logger.warning('Syslog处理失败: source_ip=%s result=%s', source_ip, result)
        except Exception as exc:
            logger.error('Syslog处理异常: source_ip=%s err=%s', source_ip, exc)


class ThreadedUDPServer(socketserver.ThreadingMixIn, socketserver.UDPServer):
    allow_reuse_address = True
    daemon_threads = True


class Command(BaseCommand):
    help = '运行设备Syslog接收服务（UDP）'

    def add_arguments(self, parser):
        parser.add_argument('--host', type=str, default=getattr(settings, 'SYSLOG_BIND_HOST', '0.0.0.0'))
        parser.add_argument('--port', type=int, default=int(getattr(settings, 'SYSLOG_PORT', 10514)))

    def handle(self, *args, **options):
        host = options['host']
        port = int(options['port'])
        recv_buffer = int(getattr(settings, 'SYSLOG_BUFFER_SIZE', 8192))

        server = ThreadedUDPServer((host, port), SyslogUDPHandler)
        server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, recv_buffer * 4)

        self.stdout.write(self.style.SUCCESS(f'Starting Syslog receiver on udp://{host}:{port}'))
        logger.info('Syslog receiver started: udp://%s:%s', host, port)

        try:
            server.serve_forever(poll_interval=0.5)
        except KeyboardInterrupt:
            logger.info('Syslog receiver interrupted by user')
        finally:
            server.server_close()
            logger.info('Syslog receiver stopped')
