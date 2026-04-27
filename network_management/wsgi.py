"""
WSGI config for network_management project.
"""

import os
import sys

# 增加 Python 递归限制以避免导入链深度问题
sys.setrecursionlimit(2000)

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'network_management.settings')

application = get_wsgi_application()
