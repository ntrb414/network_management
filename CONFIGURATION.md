# 网络管理系统 实际运行说明（代码对齐版）

本文档基于当前仓库代码生成，作为项目唯一的运行与测试说明。
如文档与代码冲突，以代码为准。

## 1. 项目定位

- 项目类型：Django 网络管理系统
- 运行协议：HTTP + WebSocket（ASGI）
- 任务系统：Celery + django-celery-beat
- 当前范围：不包含拓扑功能（已取消）

## 2. 实际启用模块（来自 settings.py）

当前已在 Django 中注册的业务应用：

- homepage
- devices
- configs
- monitoring
- alerts
- logs
- backups
- accounts
- admin_panel
- ipmanagement

说明：当前代码中未注册 topology 应用，也未提供 topology 业务代码实现。

## 3. 运行架构（实际）

项目已切换为 systemd 托管启动，不再使用脚本内 nohup + pid 的方式。

### 3.1 已注册服务

- network_management.service（Web/ASGI，Daphne）
- network_management-celery-worker.service（Celery Worker）
- network_management-celery-beat.service（Celery Beat）
- network_management-flower.service（Flower，监控）

### 3.2 启动脚本

`start.sh` 现已作为 systemd 控制入口，支持以下命令：

- `./start.sh start`：启动 Web + Worker + Beat（若存在 Flower 也会启动）
- `./start.sh stop`：停止核心服务
- `./start.sh restart`：重启核心服务
- `./start.sh status`：查看服务状态
- `./start.sh web|worker|beat|flower`：单服务重启

### 3.3 直接 systemd 命令

```bash
sudo systemctl status network_management.service
sudo systemctl status network_management-celery-worker.service
sudo systemctl status network_management-celery-beat.service
sudo systemctl status network_management-flower.service
```

## 4. 实际配置接口（环境变量）

以下为代码中真实读取的配置项：

### 4.1 Django

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_LOG_LEVEL`

### 4.2 数据库

- `DB_ENGINE`（默认 `django.db.backends.postgresql`）
- `DB_NAME`（默认 `network_management`）
- `DB_USER`（默认 `admin`）
- `DB_PASSWORD`（默认 `admin`）
- `DB_HOST`（默认 `localhost`）
- `DB_PORT`（默认 `5432`）

### 4.3 Redis / 缓存 / 队列

- `REDIS_HOST`（默认 `localhost`）
- `REDIS_PORT`（默认 `6379`）
- `REDIS_DB_CACHE`（默认 `1`）
- `REDIS_DB_QUEUE`（默认 `2`）

### 4.4 Celery

- `CELERY_BROKER_URL`（默认回退到 `redis://REDIS_HOST:REDIS_PORT/REDIS_DB_QUEUE`）
- `CELERY_RESULT_BACKEND`（同上）

### 4.5 其他

- `CONFIG_BACKUP_REPO_PATH`

## 5. 定时任务（当前代码）

Celery Beat 在 settings 中配置了以下任务：

- `ipmanagement.tasks.discover_subnets`（3600 秒）
- `ipmanagement.tasks.scan_all_subnets`（500 秒）
- `configs.tasks.execute_scheduled_backup`（60 秒）

## 6. 自动化测试方案（稳定版）

为降低环境依赖，测试统一使用 `network_management.test_settings`：

- 数据库：SQLite 内存库
- 缓存：LocMemCache（不依赖 Redis）
- Celery：Eager 模式同步执行

### 6.1 标准执行命令

```bash
cd /opt/network_management
source venv/bin/activate
pytest
```

当前 `pytest.ini` 已固定：

- `DJANGO_SETTINGS_MODULE = network_management.test_settings`
- `addopts = -q -ra --maxfail=1`

### 6.2 分层执行建议（CI / 本地联调）

```bash
# 快速冒烟：先跑核心 app
pytest devices/tests.py monitoring/tests.py alerts/tests.py

# 全量回归
pytest

# 集成场景（按需）
pytest ipmanagement/tests_integration.py
```

### 6.3 已修复的测试阻塞

- `monitoring/tests.py` 中 `MonitoringDeviceDetailViewTestCase` 的断言缩进错误已修复，避免 pytest 在收集阶段因 `NameError: self is not defined` 直接中断。

### 6.4 测试过程日志（Markdown + 时间）

测试运行期间会自动记录动作与结果到 Markdown 文件：

- 默认日志文件：`/opt/network_management/test_process_log.md`
- 日志内容包含：开始时间、收集数量、结束状态、失败用例（若有）

可通过参数或环境变量自定义日志文件路径：

```bash
# 参数方式
pytest --test-log-file logs/test_run_$(date +%F).md

# 环境变量方式
TEST_PROCESS_LOG_FILE=logs/test_run.md pytest
```

## 7. 多智能体协作约定

由于历史上存在“代码先改、文档后补”与多智能体并行编码，后续统一采用以下规则：

- 代码合并后必须同步更新本文档
- 本文档仅描述当前可运行、可验证的实现
- 需求性描述或未来规划不写入本文件

---

最后更新：2026-04-16
数据来源：仓库实际代码与当前系统服务状态
