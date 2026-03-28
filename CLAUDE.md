# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Django-based Network Management System for managing network devices (routers, switches). Supports SSH/Netmiko connections, SNMP monitoring, device discovery, configuration backups (git-based), IP address management, and real-time WebSocket updates.

## Development Commands

### Running the Application
```bash
cd /opt/network_management
./start.sh [start|stop|restart|status|worker|beat]
```
- Uses Daphne ASGI server on port 8000
- Runs Celery Worker and Celery Beat for async tasks

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
cd /opt/network_management
pytest                           # run all tests
pytest path/to/test_file.py      # run specific test file
pytest -k test_name             # run tests matching pattern
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
- **Task Queue**: Celery with Redis broker (DB 0) and django-celery-beat
- **Cache/Session**: Redis (DB 1)
- **Database**: PostgreSQL
- **WebSocket**: Django Channels with InMemoryChannelLayer
- **Network Protocols**: Netmiko (SSH), pysnmp (SNMP), scapy (packet manipulation)

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

### Celery Beat Scheduled Tasks
- `devices.tasks.check_device_online` - Every 60s
- `devices.tasks.scheduled_device_discovery` - Every 2 hours
- `monitoring.tasks.collect_all_online_devices_metrics` - Every 60s
- `monitoring.tasks.cleanup_old_metrics` - Hourly
- `ipmanagement.tasks.auto_scan_all_subnets` - Hourly

## Environment Configuration

See `.env` file for configuration. Key variables:
- `DJANGO_DEBUG=True` - Enable debug mode
- `DB_*` - PostgreSQL connection settings
- `REDIS_HOST`, `REDIS_PORT` - Redis connection
- `CELERY_BROKER_URL` - Celery message broker

## Important Paths
- `log_files/` - Application logs
- `config_backups/` - Git repo for config backups
- `static/` - Static assets
- `media/` - User-uploaded files
- `staticfiles/` - Collected static files for production
