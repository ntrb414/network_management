# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Django-based Network Management System for managing network devices (routers, switches, APs, ACs). Supports SSH/Netmiko connections, SNMP/gNMI monitoring, device discovery, configuration backups (Git/GitLab), IP address management, and real-time WebSocket SSH terminal.

## Development Commands

### Running the Application
```bash
cd /opt/network_management
./start.sh [start|stop|restart|status|web|worker|beat|flower|syslog]
```
- Uses Daphne ASGI server on port 8000
- Celery workers run in 3 priority tiers (P0-critical, P1-monitor, P2-batch)
- All services managed via systemd

### Virtual Environment
```bash
cd /opt/network_management
source venv/bin/activate
```

### Django Management
```bash
python manage.py <command>  # migrate, makemigrations, createsuperuser, shell, etc.
```

### Testing
```bash
pytest                           # run all tests (uses test_settings)
pytest path/to/test_file.py      # run specific test file
pytest -k test_name              # run tests matching pattern
```

## Architecture

### Django Apps (11 total)
- `homepage` - Landing page and permissions
- `devices` - Network device management, SSH connections via Netmiko, device discovery, status monitoring
- `configs` - Device configuration management and version control (Git-based)
- `monitoring` - Device metrics collection (CPU, memory, interface stats via SNMP)
- `alerts` - Alert rules and notifications
- `logs` - System and device logs
- `backups` - Configuration backup scheduling
- `accounts` - User accounts and permissions
- `admin_panel` - Custom admin dashboard
- `ipmanagement` - IP address management and subnet scanning
- `network_management` - Core Django project (settings, celery, urls, wsgi, asgi)

### Key Technologies
- **ASGI Server**: Daphne (HTTP + WebSocket)
- **Task Queue**: Celery with Redis (DB 2) and django-celery-beat
- **Cache/Session**: Redis (DB 1)
- **Database**: PostgreSQL
- **WebSocket**: Django Channels with InMemoryChannelLayer
- **Network Protocols**: Netmiko (SSH), pysnmp (SNMP), pygnmi (gNMI telemetry), scapy (packet manipulation)
- **Config Deployment**: Nornir for parallel batch configuration

### App Structure Pattern
Each app follows Django conventions with additions:
- `models.py` - Database models
- `views.py` - HTTP handlers
- `services.py` - Business logic layer
- `tasks.py` - Celery async tasks
- `consumers.py` - WebSocket consumers
- `urls.py` - URL routing
- `templates/` - HTML templates
- `migrations/` - Database migrations

### Celery Task Queues (Priority-based)
- **critical** (P0): Device online checks, alert status - consumed by p0-critical worker
- **metrics** (P1): Device metrics collection - consumed by p1-monitor worker
- **default** (P2): General tasks, subnet discovery - consumed by p2-batch worker
- **low** (P2): Config backups, cleanup tasks - consumed by p2-batch worker

### Celery Beat Scheduled Tasks
- `devices.tasks.check_device_online` - Every 60s (critical queue)
- `alerts.tasks.check_device_status` - Every 60s (critical queue)
- `monitoring.tasks.collect_all_online_devices_metrics` - Every 60s (metrics queue)
- `monitoring.tasks.collect_ap_devices_metrics` - Every 30s (metrics queue)
- `ipmanagement.tasks.discover_subnets` - Every 600s (default queue)
- `ipmanagement.tasks.scan_all_subnets` - Every 300s (default queue)
- `configs.tasks.execute_scheduled_backup` - Every 14400s (low queue)

## Environment Configuration

See `.env` file for configuration. Key variables:
- `DJANGO_DEBUG=True` - Enable debug mode
- `DB_*` - PostgreSQL connection settings
- `REDIS_HOST`, `REDIS_PORT` - Redis connection
- `CELERY_BROKER_URL` - Celery message broker
- `SCHEDULE_*` - Task interval overrides (in seconds)
- `GITLAB_*` - GitLab config backup integration

## Permission System

Custom role-based permission system in `accounts/`:
- Roles: `admin`, `user`, `readonly`
- Permissions stored in `UserProfile.permissions` as dict: `{'devices': ['view', 'edit'], 'configs': ['view']}`
- `PermissionMiddleware` enforces permissions on all requests
- Read-only users cannot access SSH terminal or config deployment

## Important Paths
- `log_files/` - Application logs
- `config_backups/` - Local Git repo for config backups
- `gitlab_configs/` - GitLab config backup clone
- `static/` - Static assets
- `media/` - User-uploaded files
- `staticfiles/` - Collected static files for production
