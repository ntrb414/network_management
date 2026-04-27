from django.urls import path
from django.views.generic import RedirectView
from .views import (
    RuntimeLogListView,
    LogListView,
    log_list_api,
    log_detail_api,
    log_statistics_api,
    log_cleanup_api,
    runtime_log_list_api,
    device_syslog_config_api,
)

app_name = 'logs'

urlpatterns = [
    # 日志中心（统一入口）
    path('', LogListView.as_view(), name='log_list'),
    # 兼容重定向：旧设备日志页面 → 日志中心并自动选中设备日志
    path('runtime/', RedirectView.as_view(url='/logs/?source=syslog'), name='runtime_log_list'),

    # API endpoints
    path('api/list/', log_list_api, name='log_list_api'),
    path('api/detail/<int:pk>/', log_detail_api, name='log_detail_api'),
    path('api/statistics/', log_statistics_api, name='log_statistics_api'),
    path('api/cleanup/', log_cleanup_api, name='log_cleanup_api'),
    path('api/runtime/', runtime_log_list_api, name='runtime_log_list_api'),
    path('api/devices/<int:device_id>/syslog-config/', device_syslog_config_api, name='device_syslog_config_api'),
]
