from django.urls import path
from .views import (
    AdminDashboardView,
    ScheduledTasksView,
    toggle_periodic_task,
    update_task_interval,
    get_task_detail,
)

app_name = 'admin_panel'

urlpatterns = [
    path('', AdminDashboardView.as_view(), name='dashboard'),
    path('tasks/scheduled/', ScheduledTasksView.as_view(), name='scheduled_tasks'),
    path('tasks/scheduled/<int:task_id>/toggle/', toggle_periodic_task, name='toggle_periodic_task'),
    path('tasks/scheduled/<int:task_id>/interval/', update_task_interval, name='update_task_interval'),
    path('tasks/scheduled/<int:task_id>/detail/', get_task_detail, name='get_task_detail'),
]
