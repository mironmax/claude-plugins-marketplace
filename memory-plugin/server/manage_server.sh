#!/bin/bash
# Knowledge Graph MCP Server Management Script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python"
SERVER_SCRIPT="$SCRIPT_DIR/mcp_streamable_server.py"
PID_FILE="$SCRIPT_DIR/.mcp_server.pid"

start() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Server already running (PID: $PID)"
            return 1
        else
            rm "$PID_FILE"
        fi
    fi

    echo "Starting MCP Streamable HTTP Server..."
    nohup "$VENV_PYTHON" "$SERVER_SCRIPT" > /tmp/mcp_server.log 2>&1 &
    echo $! > "$PID_FILE"
    sleep 2

    if ps -p $(cat "$PID_FILE") > /dev/null 2>&1; then
        echo "Server started (PID: $(cat "$PID_FILE"))"
        echo "Logs: /tmp/mcp_server.log"
    else
        echo "Failed to start server. Check /tmp/mcp_server.log"
        rm "$PID_FILE"
        return 1
    fi
}

stop() {
    if [ ! -f "$PID_FILE" ]; then
        echo "Server is not running"
        return 1
    fi

    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "Stopping server (PID: $PID)..."
        kill "$PID"
        sleep 2

        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Force killing..."
            kill -9 "$PID"
        fi

        rm "$PID_FILE"
        echo "Server stopped"
    else
        echo "Server not running (stale PID file)"
        rm "$PID_FILE"
    fi
}

status() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Server is running (PID: $PID)"
            curl -s http://127.0.0.1:8765/health | python3 -m json.tool 2>/dev/null
            return 0
        else
            echo "Server is not running (stale PID file)"
            return 1
        fi
    else
        echo "Server is not running"
        return 1
    fi
}

restart() {
    stop
    sleep 1
    start
}

logs() {
    tail -f /tmp/mcp_server.log
}

case "$1" in
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
        exit 1
        ;;
esac
