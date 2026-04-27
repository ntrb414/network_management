"""
ASGI config for network_management project.
"""

import os
import sys

# 增加 Python 递归限制以避免导入链深度问题
# 某些库（如 rest_framework -> requests -> charset_normalizer）的导入链较深
sys.setrecursionlimit(2000)

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'network_management.settings')

django_asgi_app = get_asgi_application()

from devices.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            websocket_urlpatterns
        )
    ),
})
