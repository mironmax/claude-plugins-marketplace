#!/bin/bash
# Knowledge Graph Visual Editor - Startup Script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Configuration
EDITOR_PORT="${EDITOR_PORT:-3001}"
EDITOR_HOST="${EDITOR_HOST:-127.0.0.1}"
MCP_SERVER_URL="${MCP_SERVER_URL:-http://127.0.0.1:8765}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Knowledge Graph Visual Editor${NC}"
echo "================================"
echo ""

# Check if MCP server is running
echo -n "Checking MCP server... "
if curl -s "${MCP_SERVER_URL}/api/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${RED}✗ Not running${NC}"
    echo ""
    echo -e "${YELLOW}Please start the MCP server first:${NC}"
    echo "  cd ../server"
    echo "  ./manage_server.sh start"
    exit 1
fi

# Check/create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "Installing dependencies..."
    venv/bin/pip install -q -r requirements.txt
fi

# Check port availability
if lsof -i :"$EDITOR_PORT" > /dev/null 2>&1; then
    echo -e "${YELLOW}Warning: Port $EDITOR_PORT is already in use${NC}"
    echo "Using alternative port 3002..."
    EDITOR_PORT=3002
fi

# Start the server
echo ""
echo "Starting Visual Editor..."
echo "  URL: http://${EDITOR_HOST}:${EDITOR_PORT}"
echo "  MCP Server: ${MCP_SERVER_URL}"
echo ""
echo -e "${GREEN}Press Ctrl+C to stop${NC}"
echo ""

export EDITOR_PORT
export EDITOR_HOST
export MCP_SERVER_URL

cd backend
exec ../venv/bin/python server.py
