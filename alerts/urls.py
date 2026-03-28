from django.urls import path
from .views import (
    AlertListView, AlertDetailView,
    alert_list_api, alert_detail_api,
    alert_acknowledge_api, alert_ignore_api,
    alert_acknowledge_all_api, alert_bulk_delete_api, alert_delete_all_api,
    alert_statistics_api, alert_device_api,
    alert_active_api, alert_counts_api
)

app_name = 'alerts'

urlpatterns = [
    # Page views
    path('', AlertListView.as_view(), name='alert_list'),
    path('<int:pk>/', AlertDetailView.as_view(), name='alert_detail'),

    # API views
    path('api/list/', alert_list_api, name='alert_list_api'),
    path('api/<int:pk>/', alert_detail_api, name='alert_detail_api'),
    path('api/<int:pk>/acknowledge/', alert_acknowledge_api, name='alert_acknowledge_api'),
    path('api/<int:pk>/ignore/', alert_ignore_api, name='alert_ignore_api'),
    path('api/acknowledge-all/', alert_acknowledge_all_api, name='alert_acknowledge_all_api'),
    path('api/bulk-delete/', alert_bulk_delete_api, name='alert_bulk_delete_api'),
    path('api/delete-all/', alert_delete_all_api, name='alert_delete_all_api'),
    path('api/statistics/', alert_statistics_api, name='alert_statistics_api'),
    path('api/device/<int:device_id>/', alert_device_api, name='alert_device_api'),
    path('api/active/', alert_active_api, name='alert_active_api'),
    path('api/counts/', alert_counts_api, name='alert_counts_api'),
]
