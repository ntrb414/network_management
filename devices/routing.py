from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('devices/webssh/<int:device_id>/', consumers.SSHConsumer.as_asgi()),
]
