#!/bin/bash
# Management script for MCP SSE Server

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDFILE="${SCRIPT_DIR}/.mcp_server.pid"
LOGFILE="${SCRIPT_DIR}/.mcp_server.log"
PORT="${KG_HTTP_PORT:-8765}"
HOST="${KG_HTTP_HOST:-127.0.0.1}"
HEALTH_URL="http://${HOST}:${PORT}/health"

# Function to check if server is running
is_running() {
    curl -s -f "${HEALTH_URL}" > /dev/null 2>&1
    return $?
}

# Start server
start() {
    if is_running; then
        echo "Server already running at ${HEALTH_URL}"
        status
        exit 0
    fi

    echo "Starting MCP SSE Server..."
    bash "${SCRIPT_DIR}/start_mcp_server.sh"
}

# Stop server
stop() {
    if [ ! -f "${PIDFILE}" ]; then
        echo "No PID file found. Server may not be running."
        exit 1
    fi

    PID=$(cat "${PIDFILE}")

    if ps -p "$PID" > /dev/null 2>&1; then
        echo "Stopping server (PID: ${PID})..."
        kill "$PID"

        # Wait for graceful shutdown
        for i in {1..10}; do
            if ! ps -p "$PID" > /dev/null 2>&1; then
                echo "Server stopped successfully"
                rm -f "${PIDFILE}"
                exit 0
            fi
            sleep 1
        done

        # Force kill if still running
        echo "Force killing server..."
        kill -9 "$PID" 2>/dev/null || true
        rm -f "${PIDFILE}"
        echo "Server stopped (forced)"
    else
        echo "Process ${PID} not found. Cleaning up PID file."
        rm -f "${PIDFILE}"
    fi
}

# Restart server
restart() {
    echo "Restarting server..."
    stop 2>/dev/null || true
    sleep 2
    start
}

# Server status
status() {
    if is_running; then
        RESPONSE=$(curl -s "${HEALTH_URL}")
        echo "Server is running at ${HEALTH_URL}"
        echo "Status: ${RESPONSE}"

        if [ -f "${PIDFILE}" ]; then
            PID=$(cat "${PIDFILE}")
            echo "PID: ${PID}"
        fi
    else
        echo "Server is not running"
        exit 1
    fi
}

# Show logs
logs() {
    if [ -f "${LOGFILE}" ]; then
        tail -f "${LOGFILE}"
    else
        echo "No log file found at ${LOGFILE}"
        exit 1
    fi
}

# Main
case "${1:-}" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    status)
        status
        ;;
    logs)
        logs
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        echo ""
        echo "Commands:"
        echo "  start   - Start the MCP SSE server"
        echo "  stop    - Stop the MCP SSE server"
        echo "  restart - Restart the MCP SSE server"
        echo "  status  - Check server status"
        echo "  logs    - Tail server logs"
        exit 1
        ;;
esac
