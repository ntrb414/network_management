# Network Management System - Deployment Guide

## System Requirements

- Python 3.8+
- PostgreSQL 12+ (or SQLite for development)
- Redis 5+ (for Celery and caching)
- Nginx (for production)
- Gunicorn (for WSGI)

## Installation Steps

### 1. Clone and Setup Virtual Environment

```bash
cd /opt/network_management
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Database Setup

```bash
# For development (SQLite)
python manage.py migrate

# For production (PostgreSQL)
export DB_ENGINE=django.db.backends.postgresql
export DB_NAME=network_management
export DB_USER=your_user
export DB_PASSWORD=your_password
export DB_HOST=localhost
export DB_PORT=5432
python manage.py migrate
```

### 3. Redis Setup

```bash
# Install and start Redis
sudo apt-get install redis-server
sudo systemctl start redis
```

### 4. Static Files

```bash
python manage.py collectstatic
```

### 5. Celery Setup

```bash
# Start Celery worker
celery -A network_management worker -l info

# Start Celery beat (for scheduled tasks)
celery -A network_management beat -l info
```

### 6. Production Deployment

#### Using Gunicorn (WSGI only, no WebSocket)

```bash
# Test configuration
gunicorn --check-config network_management.wsgi:application

# Start gunicorn
gunicorn network_management.wsgi:application --bind 0.0.0.0:8000 \
    --workers 4 --timeout 120 \
    --config deploy/gunicorn.conf.py
```

#### Using Daphne (Required for WebSocket/SSH support)

Daphne is required for WebSocket support (SSH terminal, real-time monitoring, etc.):

```bash
# Start daphne with ASGI application
daphne -b 0.0.0.0 -p 8000 network_management.asgi:application
```

#### Using Nginx

```bash
# Copy nginx configuration
sudo cp deploy/nginx.conf /etc/nginx/sites-available/network_management
sudo ln -s /etc/nginx/sites-available/network_management /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 7. Systemd Services

Create systemd service files for automatic startup:

```ini
# /etc/systemd/system/network-management.service
[Unit]
Description=Network Management System
After=network.target postgresql.service redis-server.service

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/opt/network_management
Environment="PATH=/opt/network_management/venv/bin"
ExecStart=/opt/network_management/venv/bin/gunicorn network_management.wsgi:application --config deploy/gunicorn.conf.py
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable network-management
sudo systemctl start network-management
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| DEBUG | Debug mode | False |
| SECRET_KEY | Django secret key | Required |
| ALLOWED_HOSTS | Allowed hosts | localhost |
| DB_ENGINE | Database engine | sqlite3 |
| DB_NAME | Database name | db.sqlite3 |
| DB_USER | Database user | - |
| DB_PASSWORD | Database password | - |
| DB_HOST | Database host | localhost |
| DB_PORT | Database port | 5432 |
| REDIS_URL | Redis URL | redis://localhost:6379/0 |
| CELERY_BROKER_URL | Celery broker URL | redis://localhost:6379/0 |

### Celery Scheduled Tasks

The system uses Celery Beat for scheduled tasks:
- Device discovery: Every 2 hours
- Configuration backup: Daily at 2 AM
- Log cleanup: Daily at 3 AM
- Alert cleanup: Daily at 4 AM
- Monitoring collection: Every 5 minutes

## Testing

```bash
# Run all tests
python manage.py test

# Run specific app tests
python manage.py test devices
python manage.py test configs
python manage.py test monitoring
python manage.py test alerts
python manage.py test topology
python manage.py test logs
python manage.py test backups
python manage.py test accounts
```

## Troubleshooting

### Check Celery Status

```bash
celery -A network_management inspect active
celery -A network_management inspect stats
```

### Check Logs

```bash
# Django logs
tail -f /var/log/gunicorn/error.log

# Celery logs
journalctl -u celery -f
```

### Reset Database

```bash
python manage.py flush
python manage.py migrate
```
