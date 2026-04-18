from .settings import *

# 使用内存 SQLite 数据库以便在没有 PostgreSQL 权限的环境下运行测试
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# 测试环境使用本地内存缓存，避免依赖 Redis 服务
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'network-management-tests',
    }
}

SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# 在测试中让 Celery 任务同步执行
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
