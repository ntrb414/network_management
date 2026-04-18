#!/bin/bash
# systemd 管理脚本：统一管理已注册的项目服务
# 用法：./start.sh [start|stop|restart|status|web|worker|beat|flower]

set -e

WEB_SERVICE="network_management.service"
WORKER_SERVICE="network_management-celery-worker.service"
BEAT_SERVICE="network_management-celery-beat.service"
FLOWER_SERVICE="network_management-flower.service"

run_systemctl() {
    if [[ "$EUID" -ne 0 ]] && command -v sudo >/dev/null 2>&1; then
        sudo systemctl "$@"
    else
        systemctl "$@"
    fi
}

service_exists() {
    systemctl list-unit-files --type=service --no-legend 2>/dev/null | awk '{print $1}' | grep -Fxq "$1"
}

service_status_line() {
    local unit="$1"
    if service_exists "$unit"; then
        local is_active
        is_active=$(systemctl is-active "$unit" 2>/dev/null || true)
        local is_enabled
        is_enabled=$(systemctl is-enabled "$unit" 2>/dev/null || true)
        printf "%-40s active=%-8s enabled=%s\n" "$unit" "$is_active" "$is_enabled"
    else
        printf "%-40s %s\n" "$unit" "not-installed"
    fi
}

start_core() {
    run_systemctl start "$WEB_SERVICE" "$WORKER_SERVICE" "$BEAT_SERVICE"
    if service_exists "$FLOWER_SERVICE"; then
        run_systemctl start "$FLOWER_SERVICE"
    fi
}

stop_core() {
    if service_exists "$FLOWER_SERVICE"; then
        run_systemctl stop "$FLOWER_SERVICE"
    fi
    run_systemctl stop "$BEAT_SERVICE" "$WORKER_SERVICE" "$WEB_SERVICE"
}

status_all() {
    echo "── systemd 服务状态 ─────────────────────────"
    service_status_line "$WEB_SERVICE"
    service_status_line "$WORKER_SERVICE"
    service_status_line "$BEAT_SERVICE"
    service_status_line "$FLOWER_SERVICE"
    echo "────────────────────────────────────────────"
}

case "${1:-status}" in
    start)
        start_core
        status_all
        ;;
    stop)
        stop_core
        status_all
        ;;
    restart)
        run_systemctl restart "$WEB_SERVICE" "$WORKER_SERVICE" "$BEAT_SERVICE"
        if service_exists "$FLOWER_SERVICE"; then
            run_systemctl restart "$FLOWER_SERVICE"
        fi
        status_all
        ;;
    status)
        status_all
        ;;
    web)
        run_systemctl restart "$WEB_SERVICE"
        status_all
        ;;
    worker)
        run_systemctl restart "$WORKER_SERVICE"
        status_all
        ;;
    beat)
        run_systemctl restart "$BEAT_SERVICE"
        status_all
        ;;
    flower)
        if service_exists "$FLOWER_SERVICE"; then
            run_systemctl restart "$FLOWER_SERVICE"
            status_all
        else
            echo "未检测到 $FLOWER_SERVICE"
            exit 1
        fi
        ;;
    *)
        echo "用法：$0 {start|stop|restart|status|web|worker|beat|flower}"
        exit 1
        ;;
esac
