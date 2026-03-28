from django.urls import path
from .views import AdminDashboardView, ScheduledTasksView, toggle_periodic_task

app_name = 'admin_panel'

urlpatterns = [
    path('', AdminDashboardView.as_view(), name='dashboard'),
    path('tasks/scheduled/', ScheduledTasksView.as_view(), name='scheduled_tasks'),
    path('tasks/scheduled/<int:task_id>/toggle/', toggle_periodic_task, name='toggle_periodic_task'),
]
