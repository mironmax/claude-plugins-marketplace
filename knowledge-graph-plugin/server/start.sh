#!/bin/bash
# Auto-setup wrapper for knowledge-graph MCP server
# Provides clear error messages if setup fails

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
SERVER_PY="$SCRIPT_DIR/server.py"

# Error handling
error_exit() {
    echo "ERROR: $1" >&2
    exit 1
}

# Check Python3 exists
if ! command -v python3 &> /dev/null; then
    error_exit "python3 not found. Please install Python 3.8+"
fi

# Create venv if needed
if [ ! -d "$VENV_DIR" ]; then
    echo "First run: setting up virtual environment..." >&2
    
    python3 -m venv "$VENV_DIR" 2>&1 || error_exit "Failed to create venv. Install python3-venv: sudo apt install python3-venv"
    
    echo "Installing dependencies..." >&2
    "$VENV_DIR/bin/pip" install -q -r "$SCRIPT_DIR/requirements.txt" 2>&1 || error_exit "Failed to install dependencies"
    
    echo "Setup complete." >&2
fi

# Create knowledge directories
mkdir -p "${HOME}/.claude/knowledge" 2>/dev/null

# Verify server file exists
if [ ! -f "$SERVER_PY" ]; then
    error_exit "Server file not found: $SERVER_PY"
fi

# Run the server
exec "$VENV_DIR/bin/python3" "$SERVER_PY"
