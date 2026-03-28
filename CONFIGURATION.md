# 网络管理工具 — 配置与部署文档

> **项目路径**：`/opt/network_management`
> **技术栈**：Django 4.2 · PostgreSQL · Redis · Celery · Netmiko / PySNMP / scapy

---

## 目录

1. [系统要求](#1-系统要求)
2. [Python 环境配置](#2-python-环境配置)
3. [PostgreSQL 数据库配置](#3-postgresql-数据库配置)
4. [Redis 配置](#4-redis-配置)
5. [项目环境变量配置（.env）](#5-项目环境变量配置env)
6. [Django 项目初始化](#6-django-项目初始化)
7. [Celery 异步任务配置](#7-celery-异步任务配置)
8. [项目启动命令](#8-项目启动命令)
9. [服务管理脚本](#9-服务管理脚本)
10. [运行测试](#10-运行测试)
11. [常见问题排查](#11-常见问题排查)

---

## 1. 系统要求

| 组件         | 版本要求        | 说明                   |
| ------------ | --------------- | ---------------------- |
| 操作系统     | Ubuntu 20.04+   | 需 root 或 sudo 权限   |
| Python       | 3.10+           | 推荐 3.10 / 3.11       |
| PostgreSQL   | 14+             | 持久化数据存储          |
| Redis        | 7+              | 缓存 / 会话 / 消息队列  |
| Git          | 2.30+           | 配置备份版本控制        |

---

## 2. Python 环境配置

### 2.1 安装 Python 及依赖工具

```bash
# Ubuntu / Debian
sudo apt update
sudo apt install -y python3 python3-pip python3-venv python3-dev \
    build-essential libpq-dev libffi-dev libssl-dev git
```

### 2.2 创建并激活虚拟环境

```bash
cd /opt/network_management
python3 -m venv venv
source venv/bin/activate
```

> 后续所有命令均需在虚拟环境中执行。

### 2.3 安装项目依赖

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**`requirements.txt` 完整依赖清单：**

| 分类           | 包名                  | 版本要求   | 说明                    |
| -------------- | --------------------- | ---------- | ----------------------- |
| Django 核心    | Django                | >=4.2,<5.0 | Web 框架                |
|                | djangorestframework   | >=3.14     | REST API 框架           |
| 数据库         | psycopg2-binary       | >=2.9      | PostgreSQL 驱动         |
| 缓存/消息队列  | django-redis          | >=5.4      | Django Redis 集成       |
|                | redis                 | >=5.0      | Redis Python 客户端     |
| 任务队列       | celery[redis]         | >=5.3      | 分布式任务队列          |
|                | django-celery-beat    | >=2.5      | Celery 定时任务调度     |
| 网络协议       | netmiko               | >=4.2      | SSH 设备连接            |
|                | pysnmp                | >=4.4      | SNMP 协议采集           |
|                | scapy                 | >=2.5      | LLDP 协议发现           |
| 模板引擎       | Jinja2                | >=3.1      | 配置模板渲染            |
| Git 操作       | GitPython             | >=3.1      | 配置备份版本控制        |
| Excel 导出     | openpyxl              | >=3.1      | 设备清单 Excel 导出     |
| 图像处理       | Pillow                | >=10.0     | 拓扑图导出              |
| 测试           | pytest                | >=7.4      | 测试框架                |
|                | pytest-django         | >=4.5      | Django 测试集成         |
|                | hypothesis            | >=6.82     | 属性测试                |
| 性能测试       | locust                | >=2.16     | 负载测试                |
| 工具           | python-dotenv         | >=1.0      | 环境变量管理            |

---

## 3. PostgreSQL 数据库配置

### 3.1 安装 PostgreSQL

```bash
sudo apt install -y postgresql postgresql-contrib
```

### 3.2 启动并设置开机自启

```bash
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

### 3.3 创建数据库和用户

```bash
sudo -u postgres psql
```

在 PostgreSQL 交互终端中执行：

```sql
-- 创建数据库用户
CREATE USER netadmin WITH PASSWORD 'your_secure_password';

-- 创建数据库
CREATE DATABASE network_management OWNER netadmin;

-- 授权
GRANT ALL PRIVILEGES ON DATABASE network_management TO netadmin;

-- 退出
\q
```

### 3.4 验证数据库连接

```bash
psql -h localhost -U netadmin -d network_management
```

---

## 4. Redis 配置

### 4.1 安装 Redis

```bash
sudo apt install -y redis-server
```

### 4.2 启动并设置开机自启

```bash
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

### 4.3 验证 Redis 运行状态

```bash
redis-cli ping
# 预期输出: PONG
```

### 4.4 Redis 用途说明

本项目使用 Redis 承担三个角色：

| 用途            | 数据库编号 | 配置键                   |
| --------------- | ---------- | ------------------------ |
| Celery 消息代理 | 0          | `CELERY_BROKER_URL`      |
| Celery 结果后端 | 0          | `CELERY_RESULT_BACKEND`  |
| Django 缓存     | 1          | `REDIS_URL`              |

---

## 5. 项目环境变量配置（.env）

### 5.1 创建 `.env` 文件

```bash
cd /opt/network_management
cp .env.example .env
```

### 5.2 编辑 `.env` 文件

```bash
vi .env
```

**生产环境完整配置示例：**

```ini
# ─── Django 核心设置 ───
DJANGO_SECRET_KEY=your-long-random-secret-key-here
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=your-server-ip,your-domain.com

# ─── PostgreSQL 数据库 ───
DB_ENGINE=django.db.backends.postgresql
DB_NAME=network_management
DB_USER=netadmin
DB_PASSWORD=your_secure_password
DB_HOST=localhost
DB_PORT=5432

# ─── Redis 缓存 ───
REDIS_URL=redis://localhost:6379/1

# ─── Celery 任务队列 ───
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# ─── 文件路径 ───
CONFIG_BACKUP_REPO_PATH=/opt/network_management/config_backups
TOPOLOGY_EXPORT_PATH=/opt/network_management/media/topology_exports
```

### 5.3 环境变量说明

| 变量                     | 默认值                               | 说明                                   |
| ------------------------ | ------------------------------------ | -------------------------------------- |
| `DJANGO_SECRET_KEY`      | `django-insecure-dev-key-...`        | **生产环境必须修改**，用于加密签名     |
| `DJANGO_DEBUG`           | `True`                               | 生产环境必须设为 `False`               |
| `DJANGO_ALLOWED_HOSTS`   | `localhost,127.0.0.1`                | 允许访问的主机名，逗号分隔             |
| `DB_ENGINE`              | `django.db.backends.sqlite3`         | 数据库引擎，生产环境用 PostgreSQL      |
| `DB_NAME`                | `db.sqlite3`（SQLite路径）           | 数据库名称                             |
| `DB_USER`                | 空                                   | 数据库用户名                           |
| `DB_PASSWORD`            | 空                                   | 数据库密码                             |
| `DB_HOST`                | 空                                   | 数据库主机地址                         |
| `DB_PORT`                | 空                                   | 数据库端口                             |
| `REDIS_URL`              | 空                                   | Redis 缓存地址，留空则使用本地内存缓存 |
| `CELERY_BROKER_URL`      | `redis://localhost:6379/0`           | Celery 消息代理地址                    |
| `CELERY_RESULT_BACKEND`  | `redis://localhost:6379/0`           | Celery 结果后端地址                    |
| `CONFIG_BACKUP_REPO_PATH`| `<项目目录>/config_backups`          | Git 配置备份仓库路径                   |
| `TOPOLOGY_EXPORT_PATH`   | `<项目目录>/media/topology_exports`  | 拓扑图导出路径                         |

---

## 6. Django 项目初始化

### 6.1 执行数据库迁移

```bash
cd /opt/network_management
source venv/bin/activate

python manage.py migrate
```

### 6.2 创建超级管理员

```bash
python manage.py createsuperuser
```

按提示输入用户名、邮箱和密码。

### 6.3 收集静态文件（生产环境）

```bash
python manage.py collectstatic --noinput
```

### 6.4 初始化配置备份 Git 仓库

```bash
cd /opt/network_management/config_backups
git init
git config user.name "Network Management"
git config user.email "netadmin@localhost"
```

### 6.5 创建必要目录

```bash
mkdir -p /opt/network_management/log_files
mkdir -p /opt/network_management/media/topology_exports
mkdir -p /opt/network_management/config_backups
```

---

## 7. Celery 异步任务配置

### 7.1 架构说明

项目使用 Celery + Redis 处理异步任务，核心配置定义在 `network_management/settings.py`:

| 配置项                          | 值             | 说明                 |
| ------------------------------- | -------------- | -------------------- |
| `CELERY_ACCEPT_CONTENT`         | `['json']`     | 仅接受 JSON 序列化   |
| `CELERY_TASK_SERIALIZER`        | `json`         | 任务序列化格式       |
| `CELERY_TIMEZONE`               | `Asia/Shanghai`| 时区设置             |
| `CELERY_TASK_TRACK_STARTED`     | `True`         | 追踪任务启动状态     |
| `CELERY_TASK_TIME_LIMIT`        | `600`          | 硬超时 10 分钟       |
| `CELERY_TASK_SOFT_TIME_LIMIT`   | `540`          | 软超时 9 分钟        |
| `CELERY_TASK_MAX_RETRIES`       | `3`            | 最大重试 3 次        |
| `CELERY_TASK_DEFAULT_RETRY_DELAY`| `5`           | 重试间隔 5 秒        |
| `CELERY_BEAT_SCHEDULER`         | `DatabaseScheduler` | 使用数据库存储定时任务 |

### 7.2 项目中的 Celery 任务模块

各应用均定义了异步任务，通过 `app.autodiscover_tasks()` 自动注册：

| 应用模块       | 文件路径              | 职责                       |
| -------------- | --------------------- | -------------------------- |
| `devices`      | `devices/tasks.py`    | 设备发现、状态检查         |
| `configs`      | `configs/tasks.py`    | 配置下发                   |
| `monitoring`   | `monitoring/tasks.py` | 性能指标采集               |
| `alerts`       | `alerts/tasks.py`     | 告警检查                   |
| `topology`     | `topology/tasks.py`   | 拓扑发现                   |
| `backups`      | `backups/tasks.py`    | 配置备份                   |

---

## 8. 项目启动命令

### 8.1 开发环境启动

在虚拟环境下，需要分别启动三个进程：

#### 终端 1 — Django 开发服务器

```bash
cd /opt/network_management
source venv/bin/activate
python manage.py runserver 0.0.0.0:8000
```

#### 终端 2 — Celery Worker

```bash
cd /opt/network_management
source venv/bin/activate
celery -A network_management worker --loglevel=info
```

#### 终端 3 — Celery Beat（定时任务调度）

```bash
cd /opt/network_management
source venv/bin/activate
celery -A network_management beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

### 8.2 生产环境启动

生产环境建议使用 **Gunicorn** 替代 Django 自带的开发服务器：

```bash
# 安装 Gunicorn
pip install gunicorn

# 启动 Gunicorn（4 个 worker 进程）
cd /opt/network_management
source venv/bin/activate
gunicorn network_management.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 4 \
    --timeout 120 \
    --access-logfile /opt/network_management/log_files/gunicorn_access.log \
    --error-logfile /opt/network_management/log_files/gunicorn_error.log \
    --daemon
```

### 8.3 访问入口

| 入口             | 地址                            | 说明               |
| ---------------- | ------------------------------- | ------------------ |
| Web 首页         | `http://<IP>:8000/`             | 主应用入口         |
| Django Admin     | `http://<IP>:8000/admin/`       | 后台管理           |
| API - 设备管理   | `http://<IP>:8000/api/devices/` | 设备 API           |
| API - 配置管理   | `http://<IP>:8000/api/configs/` | 配置 API           |
| API - 性能监控   | `http://<IP>:8000/api/monitoring/` | 监控 API        |
| API - 告警       | `http://<IP>:8000/api/alerts/`  | 告警 API           |
| API - 拓扑       | `http://<IP>:8000/api/topology/`| 拓扑 API           |
| API - 日志       | `http://<IP>:8000/api/logs/`    | 日志 API           |
| API - 备份       | `http://<IP>:8000/api/backups/` | 备份 API           |
| API - 用户       | `http://<IP>:8000/api/users/`   | 用户 API           |

---

## 9. 服务管理脚本

### 9.1 一键启动全部服务

创建启动脚本 `start_services.sh`：

```bash
#!/bin/bash
PROJECT_DIR=/opt/network_management
VENV=$PROJECT_DIR/venv/bin/activate

echo "=== 启动 PostgreSQL ==="
sudo systemctl start postgresql

echo "=== 启动 Redis ==="
sudo systemctl start redis-server

echo "=== 启动 Celery Worker ==="
cd $PROJECT_DIR && source $VENV
celery -A network_management worker --loglevel=info \
    --logfile=$PROJECT_DIR/log_files/celery_worker.log \
    --detach

echo "=== 启动 Celery Beat ==="
celery -A network_management beat --loglevel=info \
    --logfile=$PROJECT_DIR/log_files/celery_beat.log \
    --scheduler django_celery_beat.schedulers:DatabaseScheduler \
    --detach

echo "=== 启动 Django ==="
python manage.py runserver 0.0.0.0:8000 &

echo "=== 全部服务已启动 ==="
```

### 9.2 一键停止全部服务

创建停止脚本 `stop_services.sh`：

```bash
#!/bin/bash
echo "=== 停止 Django ==="
pkill -f "manage.py runserver" 2>/dev/null
pkill -f "gunicorn" 2>/dev/null

echo "=== 停止 Celery ==="
pkill -f "celery.*network_management" 2>/dev/null

echo "=== 全部应用服务已停止 ==="
echo "提示: PostgreSQL 和 Redis 作为系统服务继续运行"
```

### 9.3 服务状态检查

```bash
# 检查 PostgreSQL
sudo systemctl status postgresql

# 检查 Redis
redis-cli ping

# 检查 Celery Worker
celery -A network_management inspect active

# 检查 Django
curl -s http://localhost:8000/admin/ -o /dev/null -w "%{http_code}"
```

---

## 10. 运行测试

### 10.1 运行全部测试

```bash
cd /opt/network_management
source venv/bin/activate
pytest
```

### 10.2 pytest 配置

项目测试配置定义在 `pytest.ini`：

```ini
[pytest]
DJANGO_SETTINGS_MODULE = network_management.settings
python_files = tests.py test_*.py *_tests.py
python_classes = Test*
python_functions = test_*
```

### 10.3 运行特定模块测试

```bash
# 仅运行设备模块测试
pytest devices/

# 仅运行配置模块测试
pytest configs/

# 运行特定测试文件
pytest devices/tests.py -v
```

### 10.4 性能测试（Locust）

```bash
# 启动 Locust Web 界面
locust -f locustfile.py --host=http://localhost:8000
# 浏览器访问 http://localhost:8089 配置并发参数
```

---

## 11. 常见问题排查

### PostgreSQL 连接失败

```bash
# 检查服务状态
sudo systemctl status postgresql

# 检查端口监听
sudo ss -tlnp | grep 5432

# 检查认证配置
sudo cat /etc/postgresql/*/main/pg_hba.conf | grep -v "^#"
```

### Redis 连接失败

```bash
# 检查服务状态
sudo systemctl status redis-server

# 测试连接
redis-cli -h localhost -p 6379 ping
```

### Celery Worker 未处理任务

```bash
# 检查 Worker 是否注册了任务
celery -A network_management inspect registered

# 检查 Redis 队列
redis-cli llen celery

# 查看 Worker 日志
tail -f /opt/network_management/log_files/celery_worker.log
```

### Django 迁移问题

```bash
# 查看迁移状态
python manage.py showmigrations

# 重新生成迁移文件
python manage.py makemigrations

# 执行迁移
python manage.py migrate
```

### 日志文件位置

| 日志                | 路径                                                        |
| ------------------- | ----------------------------------------------------------- |
| Django 应用日志     | `/opt/network_management/log_files/network_management.log`  |
| Celery Worker 日志  | `/opt/network_management/log_files/celery_worker.log`       |
| Celery Beat 日志    | `/opt/network_management/log_files/celery_beat.log`         |
| Gunicorn 访问日志   | `/opt/network_management/log_files/gunicorn_access.log`     |
| Gunicorn 错误日志   | `/opt/network_management/log_files/gunicorn_error.log`      |

---

## 附录：Django 项目内置设置参考

以下是 `network_management/settings.py` 中的关键业务配置项：

| 设置项                           | 默认值      | 说明                   |
| -------------------------------- | ----------- | ---------------------- |
| `DEVICE_DISCOVERY_INTERVAL`      | `7200`（秒）| 设备发现扫描间隔（2小时）|
| `MONITORING_DATA_RETENTION_HOURS`| `24`（小时）| 监控数据保留时间        |
| `LOG_RETENTION_DAYS`             | `7`（天）   | 日志保留时间            |
| `BACKUP_RETENTION_DAYS`          | `30`（天）  | 配置备份保留时间        |
| `SSH_TIMEOUT`                    | `30`（秒）  | SSH 连接超时            |
| `SNMP_TIMEOUT`                   | `10`（秒）  | SNMP 查询超时           |
| `LANGUAGE_CODE`                  | `zh-hans`   | 界面语言（简体中文）    |
| `TIME_ZONE`                      | `Asia/Shanghai` | 时区设置            |
