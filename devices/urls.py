from django.urls import path
from .views import (
    DeviceListView, DeviceDetailView, DeviceConfigView,
    DeviceSSHTerminalView,
    device_list_api, device_detail_api,
    device_statistics_api, device_discover_api,
    device_export_api, device_ping_api,
    device_ping_all_api, device_config_api,
    device_config_realtime_api, check_all_devices_status_api
)

app_name = 'devices'

urlpatterns = [
    # Page views
    path('', DeviceListView.as_view(), name='device_list'),
    path('<int:pk>/', DeviceDetailView.as_view(), name='device_detail'),
    path('<int:pk>/config/', DeviceConfigView.as_view(), name='device_config'),
    path('<int:pk>/ssh-terminal/', DeviceSSHTerminalView.as_view(), name='device_ssh_terminal'),

    # API views
    path('api/list/', device_list_api, name='device_list_api'),
    path('api/<int:pk>/', device_detail_api, name='device_detail_api'),
    path('api/statistics/', device_statistics_api, name='device_statistics_api'),
    path('api/discover/', device_discover_api, name='device_discover_api'),
    path('api/export/', device_export_api, name='device_export_api'),
    path('api/ping/<int:pk>/', device_ping_api, name='device_ping_api'),
    path('api/ping-all/', device_ping_all_api, name='device_ping_all_api'),
    path('api/<int:pk>/config/', device_config_api, name='device_config_api'),
    path('api/<int:pk>/config/realtime/', device_config_realtime_api, name='device_config_realtime_api'),
    path('api/check-all-status/', check_all_devices_status_api, name='check_all_devices_status_api'),
]
