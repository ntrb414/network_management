"""
URL configuration for network_management project.
"""

from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

from homepage.views import permission_denied_view, page_not_found_view

handler403 = permission_denied_view
handler404 = page_not_found_view

urlpatterns = [
    # Homepage
    path('', include('homepage.urls')),

    # Admin
    path('admin/', admin.site.urls),

    # Custom Admin Panel
    path('admin-panel/', include('admin_panel.urls')),

    # Feature pages
    path('devices/', include('devices.urls')),
    path('configs/', include('configs.urls')),
    path('monitoring/', include('monitoring.urls')),
    path('alerts/', include('alerts.urls')),
    path('logs/', include('logs.urls')),
    path('backups/', include('backups.urls')),
    path('accounts/', include('accounts.urls')),
    path('ipmanagement/', include('ipmanagement.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
