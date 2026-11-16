#!/usr/bin/env bash
# Start, stop and inspect the KC-X server (a thin wrapper around docker compose).
# Usage: ./kcx.sh {start|stop|restart|status|logs|reset|help}
set -euo pipefail

cd "$(dirname "$0")"

URL="http://localhost:8080"
SERVICE="kcx"
WAIT_SECONDS=30

# ---- helpers

die() {
    echo "error: $*" >&2
    exit 1
}

usage() {
    cat <<EOF
Usage: ./kcx.sh <command>

Commands:
  start     Build and start KC-X in the background, then print the URL
  stop      Stop KC-X (your attempt history is kept)
  restart   Stop, rebuild and start again (use after editing questions or code)
  status    Show whether KC-X is running
  logs      Follow the server logs (Ctrl+C to quit)
  reset     Stop KC-X and wipe all attempt history (asks first)
  help      Show this help
EOF
}

preflight() {
    command -v docker >/dev/null 2>&1 || die "docker is not installed. See https://docs.docker.com/get-docker/"
    docker compose version >/dev/null 2>&1 || die "Docker Compose v2 ('docker compose') is required."
    docker info >/dev/null 2>&1 || die "cannot reach the Docker daemon. Is Docker running?"
}

is_running() {
    [[ -n "$(docker compose ps --status running -q "$SERVICE" 2>/dev/null)" ]]
}

is_ready() {
    if command -v curl >/dev/null 2>&1; then
        curl -fsS -o /dev/null "$URL/" 2>/dev/null
    else
        is_running
    fi
}

# ---- commands

cmd_start() {
    docker compose up -d --build
    echo "Waiting for KC-X to come up..."
    for _ in $(seq "$WAIT_SECONDS"); do
        if is_ready; then
            echo "KC-X is running at $URL"
            return 0
        fi
        sleep 1
    done
    echo "error: KC-X did not respond within ${WAIT_SECONDS}s. Last log lines:" >&2
    docker compose logs --tail=30 "$SERVICE" >&2 || true
    exit 1
}

cmd_stop() {
    docker compose down
    echo "KC-X stopped. Your history is kept; './kcx.sh reset' wipes it."
}

cmd_status() {
    if is_running; then
        docker compose ps "$SERVICE"
        echo "KC-X is running at $URL"
    else
        echo "KC-X is not running. Start it with './kcx.sh start'."
    fi
}

cmd_logs() {
    docker compose logs -f --tail=100 "$SERVICE"
}

cmd_reset() {
    local answer
    read -r -p "Wipe all attempt history? This cannot be undone. [y/N] " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        docker compose down -v
        echo "KC-X stopped and history wiped."
    else
        echo "Cancelled."
    fi
}

# ---- main

case "${1:-help}" in
    start)   preflight; cmd_start ;;
    stop)    preflight; cmd_stop ;;
    restart) preflight; cmd_stop; cmd_start ;;
    status)  preflight; cmd_status ;;
    logs)    preflight; cmd_logs ;;
    reset)   preflight; cmd_reset ;;
    help|-h|--help) usage ;;
    *)       usage >&2; exit 1 ;;
esac
