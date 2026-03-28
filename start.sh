#!/bin/bash
# 启动脚本：Daphne + Celery Worker + Celery Beat
# 使用 Daphne 处理 HTTP+WebSocket，Celery 处理异步任务
# 用法：./start.sh [start|stop|restart|status|worker|beat]

set -e

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$BASE_DIR/venv"
DAPHNE="$VENV/bin/daphne"
CELERY="$VENV/bin/celery"

PID_DIR="$BASE_DIR/run"
LOG_DIR="$BASE_DIR/log_files"
PID_FILE="$PID_DIR/daphne.pid"
WORKER_PID_FILE="$PID_DIR/celery_worker.pid"
BEAT_PID_FILE="$PID_DIR/celery_beat.pid"
DAPHNE_LOG="$LOG_DIR/daphne.log"
WORKER_LOG="$LOG_DIR/celery_worker.log"
BEAT_LOG="$LOG_DIR/celery_beat.log"

HTTP_PORT=8000

mkdir -p "$PID_DIR" "$LOG_DIR"

is_running() {
    [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null
}

start_daphne() {
    if is_running "$PID_FILE"; then
        echo "Daphne 已在运行 (PID $(cat "$PID_FILE"))"
        return
    fi

    echo "启动 Daphne (:$HTTP_PORT)..."
    cd "$BASE_DIR"
    source "$VENV/bin/activate"
    nohup "$DAPHNE" \
        -b 0.0.0.0 \
        -p "$HTTP_PORT" \
        "$BASE_DIR/network_management.asgi:application" \
        > "$DAPHNE_LOG" 2>&1 &
    echo $! > "$PID_FILE"
    echo "Daphne 已启动 (PID $(cat "$PID_FILE"))"
}

start_celery_worker() {
    if is_running "$WORKER_PID_FILE"; then
        echo "Celery Worker 已在运行 (PID $(cat "$WORKER_PID_FILE"))"
        return
    fi

    echo "启动 Celery Worker..."
    cd "$BASE_DIR"
    source "$VENV/bin/activate"
    nohup "$CELERY" \
        -A network_management \
        worker \
        --loglevel=info \
        --logfile="$WORKER_LOG" \
        --pidfile="$WORKER_PID_FILE" \
        --detach

    echo "Celery Worker 已启动 (PID $(cat "$WORKER_PID_FILE"))"
}

start_celery_beat() {
    if is_running "$BEAT_PID_FILE"; then
        echo "Celery Beat 已在运行 (PID $(cat "$BEAT_PID_FILE"))"
        return
    fi

    echo "启动 Celery Beat..."
    cd "$BASE_DIR"
    source "$VENV/bin/activate"
    nohup "$CELERY" \
        -A network_management \
        beat \
        --loglevel=info \
        --logfile="$BEAT_LOG" \
        --pidfile="$BEAT_PID_FILE" \
        --scheduler django_celery_beat.schedulers:DatabaseScheduler \
        --detach

    echo "Celery Beat 已启动 (PID $(cat "$BEAT_PID_FILE"))"
}

stop_service() {
    local pid_file=$1
    local name=$2

    if is_running "$pid_file"; then
        local pid
        pid=$(cat "$pid_file")
        echo "停止 $name (PID $pid)..."
        kill "$pid"
        for i in $(seq 1 10); do
            kill -0 "$pid" 2>/dev/null || break
            sleep 1
        done
        kill -0 "$pid" 2>/dev/null && kill -9 "$pid"
        rm -f "$pid_file"
        echo "$name 已停止"
    else
        echo "$name 未在运行"
    fi
}

start() {
    start_daphne
    start_celery_worker
    start_celery_beat
}

stop() {
    stop_service "$PID_FILE" "Daphne"
    stop_service "$WORKER_PID_FILE" "Celery Worker"
    stop_service "$BEAT_PID_FILE" "Celery Beat"
}

status() {
    echo "── 服务状态 ──────────────────────"
    if is_running "$PID_FILE"; then
        echo "Daphne       ✓ 运行中 (PID $(cat "$PID_FILE"), :$HTTP_PORT)"
    else
        echo "Daphne       ✗ 未运行"
    fi

    if is_running "$WORKER_PID_FILE"; then
        echo "Celery Worker ✓ 运行中 (PID $(cat "$WORKER_PID_FILE"))"
    else
        echo "Celery Worker ✗ 未运行"
    fi

    if is_running "$BEAT_PID_FILE"; then
        echo "Celery Beat   ✓ 运行中 (PID $(cat "$BEAT_PID_FILE"))"
    else
        echo "Celery Beat   ✗ 未运行"
    fi
    echo "──────────────────────────────────"
}

case "${1:-start}" in
    start)
        start
        status
        ;;
    stop)
        stop
        ;;
    restart)
        stop
        sleep 1
        start
        status
        ;;
    status)
        status
        ;;
    worker)
        start_celery_worker
        ;;
    beat)
        start_celery_beat
        ;;
    *)
        echo "用法：$0 {start|stop|restart|status|worker|beat}"
        exit 1
        ;;
esac
