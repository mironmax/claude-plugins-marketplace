#!/bin/bash
# Startup script for MCP SSE Server
# Ensures server is running before Claude Code connects

set -e

# Configuration
PORT="${KG_HTTP_PORT:-8765}"
HOST="${KG_HTTP_HOST:-127.0.0.1}"
HEALTH_URL="http://${HOST}:${PORT}/health"
MAX_RETRIES=30
RETRY_INTERVAL=1

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDFILE="${SCRIPT_DIR}/.mcp_server.pid"
LOGFILE="${SCRIPT_DIR}/.mcp_server.log"

# Function to check if server is running
check_server() {
    curl -s -f "${HEALTH_URL}" > /dev/null 2>&1
    return $?
}

# Function to start server in background
start_server() {
    echo "Starting MCP SSE Server on ${HOST}:${PORT}..." >&2

    # Start server in background
    nohup python3 "${SCRIPT_DIR}/mcp_sse_server.py" > "${LOGFILE}" 2>&1 &
    SERVER_PID=$!

    # Save PID
    echo $SERVER_PID > "${PIDFILE}"

    echo "Server started with PID ${SERVER_PID}" >&2
    echo "Logs: ${LOGFILE}" >&2
}

# Function to wait for server to be ready
wait_for_server() {
    local retries=0

    while [ $retries -lt $MAX_RETRIES ]; do
        if check_server; then
            echo "Server is ready!" >&2
            return 0
        fi

        retries=$((retries + 1))
        sleep $RETRY_INTERVAL
    done

    echo "ERROR: Server failed to start within ${MAX_RETRIES} seconds" >&2
    echo "Check logs: ${LOGFILE}" >&2
    return 1
}

# Main logic
main() {
    # Check if server is already running
    if check_server; then
        echo "MCP SSE Server already running at ${HEALTH_URL}" >&2
        exit 0
    fi

    # Check if PID file exists but server not responding
    if [ -f "${PIDFILE}" ]; then
        OLD_PID=$(cat "${PIDFILE}")
        if ps -p "$OLD_PID" > /dev/null 2>&1; then
            echo "Stale PID found, killing process ${OLD_PID}..." >&2
            kill "$OLD_PID" 2>/dev/null || true
            sleep 2
        fi
        rm -f "${PIDFILE}"
    fi

    # Start server
    start_server

    # Wait for server to be ready
    if wait_for_server; then
        echo "MCP SSE Server ready at ${HEALTH_URL}" >&2
        exit 0
    else
        exit 1
    fi
}

main "$@"
