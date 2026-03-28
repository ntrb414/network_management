# Network Management

Django-based Network Management System for managing network devices (routers, switches). Supports SSH/Netmiko connections, SNMP monitoring, device discovery, configuration backups (git-based), IP address management, and real-time WebSocket updates.

## Features

- **Device Management** - Add, edit, and manage network devices (routers, switches)
- **SSH Connections** - Connect to devices via SSH using Netmiko
- **SNMP Monitoring** - Monitor CPU, memory, and interface stats
- **Device Discovery** - Automatic network device discovery
- **Configuration Backups** - Git-based configuration version control
- **IP Address Management** - Subnet scanning and IP address tracking
- **Real-time Updates** - WebSocket support for live status updates
- **Alerts & Notifications** - Configurable alert rules and notifications

## Tech Stack

- **Backend**: Django 4.x
- **ASGI Server**: Daphne
- **Task Queue**: Celery + Redis
- **WebSocket**: Django Channels
- **Network Protocols**: Netmiko (SSH), pysnmp (SNMP), scapy
- **Database**: PostgreSQL
- **Cache/Session**: Redis
