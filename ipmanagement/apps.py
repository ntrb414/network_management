import os
from django.apps import AppConfig


class IpmanagementConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ipmanagement'
    verbose_name = 'IP管理'
    path = os.path.dirname(os.path.abspath(__file__))
