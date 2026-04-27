"""
Django settings for network_management project.
"""

import os
from pathlib import Path
from celery.schedules import crontab

from dotenv import load_dotenv

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure-dev-key-change-in-production-!@#$%^&*()'
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DJANGO_DEBUG', 'True').lower() in ('true', '1', 'yes')

ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,192.168.50.132,*').split(',')

# Security settings - 开发环境禁用某些安全特性
if DEBUG:
    SECURE_CROSS_ORIGIN_OPENER_POLICY = None  # 开发环境禁用 COOP
    SECURE_SSL_REDIRECT = False
else:
    SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'
    SECURE_SSL_REDIRECT = True
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party apps
    'rest_framework',
    'django_celery_beat',
    'channels',
    # Project apps
    'homepage.apps.HomepageConfig',
    'devices.apps.DevicesConfig',
    'configs.apps.ConfigsConfig',
    'monitoring.apps.MonitoringConfig',
    'alerts.apps.AlertsConfig',
    'logs.apps.LogsConfig',
    'backups.apps.BackupsConfig',
    'accounts.apps.AccountsConfig',
    'admin_panel.apps.AdminPanelConfig',
    'ipmanagement.apps.IpmanagementConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # Custom middleware
    'network_management.middleware.APIDisallowRedirectMiddleware',
    'accounts.middleware.PermissionMiddleware',
]

ROOT_URLCONF = 'network_management.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'network_management.wsgi.application'
ASGI_APPLICATION = 'network_management.asgi.application'

# Channels configuration for WebSocket support
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer'
    }
}

# Database
# https://docs.djangoproject.com/4.2/ref/settings/#databases
# 默认使用 PostgreSQL 数据库
DATABASES = {
    'default': {
        'ENGINE': os.environ.get('DB_ENGINE', 'django.db.backends.postgresql'),
        'NAME': os.environ.get('DB_NAME', 'network_management'),
        'USER': os.environ.get('DB_USER', 'admin'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'admin'),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        'CONN_MAX_AGE': 600,  # 持久连接10分钟
        'CONN_HEALTH_CHECKS': True,  # 连接健康检查
        'OPTIONS': {
            'connect_timeout': 10,
        },
    }
}

# Cache configuration
# Redis 数据库分配：
# DB 1: 数据存储（Django缓存、Session、配置缓存）
# DB 2: 队列存储（Celery任务队列）

REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
REDIS_DB_CACHE = int(os.environ.get('REDIS_DB_CACHE', 1))   # 数据存储 - DB 1
REDIS_DB_QUEUE = int(os.environ.get('REDIS_DB_QUEUE', 2))   # 队列存储 - DB 2

# 缓存配置 - 使用 Redis DB 1
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB_CACHE}',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
        'TIMEOUT': 300,  # 默认5分钟过期
    }
}

# 使用 Redis 存储 session
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

print(f"[Cache] Using Redis DB {REDIS_DB_CACHE} for data storage (cache, session)")
print(f"[Queue] Using Redis DB {REDIS_DB_QUEUE} for task queues")

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Django REST Framework configuration
REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DATETIME_FORMAT': '%Y-%m-%d %H:%M:%S',
    'EXCEPTION_HANDLER': 'network_management.exceptions.custom_exception_handler',
}

# ============================================================
# Celery Configuration (异步任务队列 - 定时任务调度)
# ============================================================
# Celery Broker 和 Result Backend 使用 Redis
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB_QUEUE}')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB_QUEUE}')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# Celery Worker 预取配置：关键队列设为 1，避免长任务阻塞后续任务
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

# Celery 任务队列配置（按优先级分级）
# critical: 最高优先级 - 设备检测/告警（P0 Worker 消费）
# metrics:  中等优先级 - 监控指标采集（P1 Worker 消费）
# default:  普通后台任务（P2 Worker 消费）
# low:      最低优先级 - 配置备份/数据清理（P2 Worker 消费）
CELERY_TASK_ROUTES = {
    # P0 - Critical（最高优先级，设备检测与告警）
    'devices.tasks.check_device_online': {'queue': 'critical'},
    'alerts.tasks.check_device_status': {'queue': 'critical'},

    # P1 - Monitor（中等优先级，监控指标采集）
    'monitoring.tasks.collect_device_metrics': {'queue': 'metrics'},
    'monitoring.tasks.collect_all_online_devices_metrics': {'queue': 'metrics'},
    'monitoring.tasks.collect_ap_devices_metrics': {'queue': 'metrics'},

    # P2 - Batch（最低优先级，配置备份与后台任务）
    'configs.tasks.backup_all_devices_configs': {'queue': 'low'},
    'configs.tasks.backup_single_device_config': {'queue': 'low'},
    'configs.tasks.execute_scheduled_backup': {'queue': 'low'},
    'configs.tasks.preload_device_configs_task': {'queue': 'low'},
    'configs.tasks.execute_config_task': {'queue': 'low'},
    'configs.tasks.deploy_single_device_config': {'queue': 'low'},
    'configs.tasks.deploy_batch_device_config': {'queue': 'low'},
    'configs.tasks.cleanup_old_config_results': {'queue': 'low'},
    'logs.tasks.cleanup_old_logs': {'queue': 'low'},
    'alerts.tasks.cleanup_old_alerts': {'queue': 'low'},
    'alerts.tasks.generate_alert_report': {'queue': 'low'},
    'monitoring.tasks.cleanup_old_metrics': {'queue': 'low'},
    'backups.tasks.cleanup_old_backups': {'queue': 'low'},
    'ipmanagement.tasks.discover_subnets': {'queue': 'default'},
    'ipmanagement.tasks.scan_all_subnets': {'queue': 'default'},
}

# ============================================================
# 定时任务间隔配置（从环境变量读取）
# ============================================================
SCHEDULE_CHECK_DEVICES_ONLINE = int(os.environ.get('SCHEDULE_CHECK_DEVICES_ONLINE', 60))
SCHEDULE_COLLECT_DEVICES_RUNNING_DATA = int(os.environ.get('SCHEDULE_COLLECT_DEVICES_RUNNING_DATA', 60))
SCHEDULE_CONFIG_BACKUP_DAILY = int(os.environ.get('SCHEDULE_CONFIG_BACKUP_DAILY', 14400))
SCHEDULE_SUBNETS_FIND = int(os.environ.get('SCHEDULE_SUBNETS_FIND', 600))
SCHEDULE_ACTIVE_IP_FIND = int(os.environ.get('SCHEDULE_ACTIVE_IP_FIND', 300))

# Celery Beat 定时任务配置
# 核心定时任务已固化到代码中，避免依赖数据库动态调度
CELERY_BEAT_SCHEDULE = {
    # P0 - Critical: 设备在线状态检测（每60秒）
    'check-devices-online': {
        'task': 'devices.tasks.check_device_online',
        'schedule': SCHEDULE_CHECK_DEVICES_ONLINE,
        'options': {'queue': 'critical'},
    },
    # P0 - Critical: 告警状态检查（每60秒）
    'check-device-status-alerts': {
        'task': 'alerts.tasks.check_device_status',
        'schedule': SCHEDULE_CHECK_DEVICES_ONLINE,
        'options': {'queue': 'critical'},
    },
    # P1 - Monitor: 批量采集在线设备指标（每60秒）
    'collect-all-online-devices-metrics': {
        'task': 'monitoring.tasks.collect_all_online_devices_metrics',
        'schedule': SCHEDULE_COLLECT_DEVICES_RUNNING_DATA,
        'options': {'queue': 'metrics'},
    },
    # P2 - Batch / Default: 网段自动发现
    'subnets-find': {
        'task': 'ipmanagement.tasks.discover_subnets',
        'schedule': SCHEDULE_SUBNETS_FIND,
        'options': {'queue': 'default'},
    },
    # P2 - Batch / Default: 活跃 IP 扫描
    'active-ip-find': {
        'task': 'ipmanagement.tasks.scan_all_subnets',
        'schedule': SCHEDULE_ACTIVE_IP_FIND,
        'options': {'queue': 'default'},
    },
    # P2 - Batch: 定时配置备份调度触发器
    'config-backup-daily': {
        'task': 'configs.tasks.execute_scheduled_backup',
        'schedule': SCHEDULE_CONFIG_BACKUP_DAILY,
        'options': {'queue': 'low'},
    },
}

# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name} {module} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'log_files' / 'network_management.log',
            'maxBytes': 10 * 1024 * 1024,  # 10MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.environ.get('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'devices': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'configs': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'monitoring': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'alerts': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
}

# Network Management specific settings
# 设备发现扫描间隔（秒）
DEVICE_DISCOVERY_INTERVAL = 60 

# 监控数据保留时间（小时）
MONITORING_DATA_RETENTION_HOURS = 2

# 监控页面自动刷新间隔（秒）
MONITORING_RELOAD_TIME = int(os.environ.get('MONITORING_RELOAD_TIME', 30))

# 日志保留时间（天）
LOG_RETENTION_DAYS = 7

# Syslog 接收配置
SYSLOG_BIND_HOST = os.environ.get('SYSLOG_BIND_HOST', '0.0.0.0')
SYSLOG_PORT = int(os.environ.get('SYSLOG_PORT', 10514))
SYSLOG_BUFFER_SIZE = int(os.environ.get('SYSLOG_BUFFER_SIZE', 8192))
SYSLOG_ALERT_SUPPRESS_SECONDS = int(os.environ.get('SYSLOG_ALERT_SUPPRESS_SECONDS', 120))

# 配置备份保留时间（天）
BACKUP_RETENTION_DAYS = 30

# SSH 连接默认超时（秒）
SSH_TIMEOUT = 30

# SNMP 默认超时（秒）
SNMP_TIMEOUT = 10
# ============================================================
# Gitlab 备份参数
# ============================================================
# 配置备份 Git 仓库路径
CONFIG_BACKUP_REPO_PATH = os.environ.get(
    'CONFIG_BACKUP_REPO_PATH',
    str(BASE_DIR / 'config_backups')
)

# GitLab 配置
GITLAB_URL = os.environ.get('GITLAB_URL', 'http://192.168.50.142')
GITLAB_PROJECT_ID = os.environ.get('GITLAB_PROJECT_ID', '')
GITLAB_ACCESS_TOKEN = os.environ.get('GITLAB_ACCESS_TOKEN', '')
GITLAB_BRANCH = os.environ.get('GITLAB_BRANCH', 'main')
GITLAB_CONFIG_REPO_PATH = os.environ.get(
    'GITLAB_CONFIG_REPO_PATH',
    str(BASE_DIR / 'gitlab_configs')
)

# ============================================================
# Nornir 配置下发参数
# ============================================================
CONFIG_DEPLOY_NORNIR_WORKERS = int(os.environ.get('CONFIG_DEPLOY_NORNIR_WORKERS', 20))
CONFIG_DEPLOY_CONNECT_TIMEOUT = int(os.environ.get('CONFIG_DEPLOY_CONNECT_TIMEOUT', 10))
CONFIG_DEPLOY_AUTH_TIMEOUT = int(os.environ.get('CONFIG_DEPLOY_AUTH_TIMEOUT', 10))
CONFIG_DEPLOY_BANNER_TIMEOUT = int(os.environ.get('CONFIG_DEPLOY_BANNER_TIMEOUT', 10))
CONFIG_DEPLOY_READ_TIMEOUT = int(os.environ.get('CONFIG_DEPLOY_READ_TIMEOUT', 20))

