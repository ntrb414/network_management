"""
IP Management URLs
"""
from django.urls import path
from . import views

app_name = 'ipmanagement'

urlpatterns = [
    # 网段管理
    path('', views.SubnetListView.as_view(), name='subnet_list'),
    path('subnets/add/', views.SubnetCreateView.as_view(), name='subnet_add'),
    path('subnets/<int:pk>/', views.SubnetDetailView.as_view(), name='subnet_detail'),
    path('subnets/<int:pk>/edit/', views.SubnetUpdateView.as_view(), name='subnet_edit'),
    path('subnets/<int:pk>/delete/', views.SubnetDeleteView.as_view(), name='subnet_delete'),

    # IP扫描页面
    path('scan/', views.IPScanView.as_view(), name='ip_scan'),

    # IP分配历史
    path('allocations/', views.AllocationHistoryView.as_view(), name='allocation_history'),

    # API - 子网
    path('api/subnets/', views.api_subnets, name='api_subnets'),
    path('api/subnets/<int:subnet_id>/', views.api_subnet_detail, name='api_subnet_detail'),
    path('api/subnets/<int:subnet_id>/available/', views.api_subnet_available, name='api_subnet_available'),
    path('api/subnets/<int:subnet_id>/allocate/', views.api_subnet_allocate, name='api_subnet_allocate'),
    path('api/subnets/<int:subnet_id>/release/', views.api_subnet_release, name='api_subnet_release'),

    # API - IP
    path('api/ips/', views.api_ips, name='api_ips'),
    path('api/ips/<str:ip_address>/', views.api_ip_detail, name='api_ip_detail'),
    path('api/ips/<str:ip_address>/allocate/', views.api_ip_allocate, name='api_ip_allocate'),
    path('api/ips/<str:ip_address>/release/', views.api_ip_release, name='api_ip_release'),
    path('api/ips/<str:ip_address>/reserve/', views.api_ip_reserve, name='api_ip_reserve'),
    path('api/ips/<str:ip_address>/status/', views.api_ip_update_status, name='api_ip_update_status'),

    # API - 扫描
    path('api/scan/', views.api_scan_subnet, name='api_scan_subnet'),
    path('api/scan/<int:task_id>/', views.api_scan_status, name='api_scan_status'),
    path('api/scan/<int:task_id>/result/', views.api_scan_result, name='api_scan_result'),
    path('api/scan/<int:task_id>/sync/', views.api_sync_scan, name='api_sync_scan'),
    path('api/quick-scan/', views.api_quick_scan, name='api_quick_scan'),

    # API - IP使用情况
    path('api/subnets/<int:subnet_id>/usage/', views.api_subnet_usage, name='api_subnet_usage'),
    path('api/subnets/<int:subnet_id>/batch/', views.api_batch_ip_operations, name='api_batch_ip_operations'),

    # API - 网段发现
    path('api/auto-subnets/', views.api_auto_subnets, name='api_auto_subnets'),
    path('api/discover-subnets/', views.api_discover_subnets, name='api_discover_subnets'),

    # API - 日志
    path('api/allocations/', views.api_allocation_history, name='api_allocation_history'),
]
