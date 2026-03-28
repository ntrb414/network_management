# Gunicorn configuration for production deployment
# NOTE: Gunicorn does NOT support WebSocket. Use Daphne instead:
#   daphne -b 0.0.0.0 -p 8000 network_management.asgi:application
# Run with: gunicorn network_management.wsgi:application --bind 0.0.0.0:8000 --workers 4 --timeout 120

import multiprocessing

# Server socket
bind = '0.0.0.0:8000'
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = 'sync'
worker_connections = 1000
timeout = 120
keepalive = 5

# Logging
accesslog = '/var/log/gunicorn/access.log'
errorlog = '/var/log/gunicorn/error.log'
loglevel = 'info'

# Process naming
proc_name = 'network_management'

# Server mechanics
daemon = False
pidfile = '/var/run/gunicorn.pid'
user = 'www-data'
group = 'www-data'
tmp_upload_dir = None

# SSL (if needed)
# keyfile = '/path/to/key.pem'
# certfile = '/path/to/cert.pem'
