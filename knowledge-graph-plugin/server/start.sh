#!/bin/bash
# Auto-setup wrapper for knowledge-graph MCP server

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
SERVER_PY="$SCRIPT_DIR/server.py"

# Create venv and install dependencies if needed
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR" >/dev/null 2>&1
    "$VENV_DIR/bin/pip" install -q -r "$SCRIPT_DIR/requirements.txt" >/dev/null 2>&1
fi

# Create knowledge directory
mkdir -p "${HOME}/.claude/knowledge" 2>/dev/null

# Run the server
exec "$VENV_DIR/bin/python3" "$SERVER_PY"
