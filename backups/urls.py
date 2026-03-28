from django.urls import path
from .views import (
    BackupListView,
    BackupDetailView,
    ConfigBackupView,
    backup_list_api,
    device_backup_list_api,
    backup_detail_api,
    backup_create_api,
    backup_compare_api,
    backup_trigger_api,
)

app_name = 'backups'

urlpatterns = [
    # Configuration backup page views
    path('', BackupListView.as_view(), name='backup_list'),
    path('<int:pk>/', BackupDetailView.as_view(), name='backup_detail'),
    path('config/', ConfigBackupView.as_view(), name='config_backup'),

    # API endpoints
    path('api/list/', backup_list_api, name='backup_list_api'),
    path('api/devices/<int:device_id>/', device_backup_list_api, name='device_backup_list_api'),
    path('api/<int:pk>/', backup_detail_api, name='backup_detail_api'),
    path('api/create/', backup_create_api, name='backup_create_api'),
    path('api/compare/', backup_compare_api, name='backup_compare_api'),
    path('api/trigger/', backup_trigger_api, name='backup_trigger_api'),
]
