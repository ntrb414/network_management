from django.urls import path
from .views import LogListView, log_list_api, log_detail_api, log_statistics_api

app_name = 'logs'

urlpatterns = [
    # System logs page views
    path('', LogListView.as_view(), name='log_list'),

    # API endpoints
    path('api/list/', log_list_api, name='log_list_api'),
    path('api/detail/<int:pk>/', log_detail_api, name='log_detail_api'),
    path('api/statistics/', log_statistics_api, name='log_statistics_api'),
]
