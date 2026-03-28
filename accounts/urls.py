from django.urls import path
from .views import (
    AccountListView,
    AccountDetailView,
    user_list_api,
    user_detail_api,
    user_permissions_api,
    audit_log_list_api,
)

app_name = 'accounts'

urlpatterns = [
    # User account management page views
    path('', AccountListView.as_view(), name='account_list'),
    path('<int:pk>/', AccountDetailView.as_view(), name='account_detail'),

    # API endpoints
    path('api/users/', user_list_api, name='user_list_api'),
    path('api/users/<int:pk>/', user_detail_api, name='user_detail_api'),
    path('api/users/<int:pk>/permissions/', user_permissions_api, name='user_permissions_api'),
    path('api/audit/logs/', audit_log_list_api, name='audit_log_list_api'),
]
