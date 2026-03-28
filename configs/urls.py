from django.urls import path
from .views import (
    ConfigListView, ConfigDetailView, ConfigBackupView,
    config_template_list_api, config_template_detail_api,
    validate_template_api,
    config_task_list_api, config_task_detail_api,
    config_task_execute_api,
    config_backup_trigger_api, config_backup_status_api, config_backup_schedule_api,
    schedule_list_api, schedule_detail_api, schedule_run_api, schedule_logs_api
)

app_name = 'configs'

urlpatterns = [
    # Page views
    path('', ConfigListView.as_view(), name='config_list'),
    path('<int:pk>/', ConfigDetailView.as_view(), name='config_detail'),
    path('backup/', ConfigBackupView.as_view(), name='config_backup'),

    # Template API
    path('api/templates/', config_template_list_api, name='template_list_api'),
    path('api/templates/<int:pk>/', config_template_detail_api, name='template_detail_api'),
    path('api/templates/validate/', validate_template_api, name='validate_template_api'),

    # Task API
    path('api/tasks/', config_task_list_api, name='task_list_api'),
    path('api/tasks/<int:pk>/', config_task_detail_api, name='task_detail_api'),
    path('api/tasks/<int:pk>/execute/', config_task_execute_api, name='task_execute_api'),

    # Backup API
    path('api/backup/trigger/', config_backup_trigger_api, name='backup_trigger_api'),
    path('api/backup/status/', config_backup_status_api, name='backup_status_api'),
    path('api/backup/schedule/', config_backup_schedule_api, name='backup_schedule_api'),

    # Schedule API
    path('api/schedules/', schedule_list_api, name='schedule_list_api'),
    path('api/schedules/<int:pk>/', schedule_detail_api, name='schedule_detail_api'),
    path('api/schedules/<int:pk>/run/', schedule_run_api, name='schedule_run_api'),
    path('api/schedules/<int:pk>/logs/', schedule_logs_api, name='schedule_logs_api'),
]
