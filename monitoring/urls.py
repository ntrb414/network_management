from django.urls import path
from .views import (
    MonitoringListView, MonitoringDashboardView, MonitoringMetricTypesView, MonitoringDeviceDetailView,
    monitoring_device_realtime_api, monitoring_device_realtime_redis_api,
    monitoring_device_metrics_api,
    monitoring_statistics_api, monitoring_collect_api
)

app_name = 'monitoring'

urlpatterns = [
    # Page views
    path('', MonitoringDashboardView.as_view(), name='monitoring_dashboard'),
    path('metric-types/', MonitoringMetricTypesView.as_view(), name='metric_types'),
    path('metrics/', MonitoringListView.as_view(), name='monitoring_list'),
    path('devices/<int:device_id>/', MonitoringDeviceDetailView.as_view(), name='device_detail'),

    # API views
    path('api/devices/<int:device_id>/realtime/', monitoring_device_realtime_api, name='device_realtime_api'),
    path('api/devices/<int:device_id>/realtime-redis/', monitoring_device_realtime_redis_api, name='device_realtime_redis'),
    path('api/devices/<int:device_id>/metrics/', monitoring_device_metrics_api, name='device_metrics_api'),
    path('api/devices/<int:device_id>/collect/', monitoring_collect_api, name='collect_api'),
    path('api/statistics/', monitoring_statistics_api, name='statistics_api'),
]
