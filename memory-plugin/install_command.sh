#!/bin/bash
# Install kg-memory global command
# This creates a symlink in ~/.local/bin so you can run 'kg-memory' from anywhere

set -e

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
COMMAND_NAME="kg-memory"

# Create ~/.local/bin if it doesn't exist
mkdir -p "$BIN_DIR"

# Create symlink
ln -sf "$PLUGIN_DIR/server/manage_server.sh" "$BIN_DIR/$COMMAND_NAME"
chmod +x "$PLUGIN_DIR/server/manage_server.sh"

echo "✓ Installed: $COMMAND_NAME → $BIN_DIR/$COMMAND_NAME"

# Check if ~/.local/bin is in PATH
if [[ ":$PATH:" == *":$BIN_DIR:"* ]]; then
    echo "✓ $BIN_DIR is in your PATH"
    echo ""
    echo "You can now run:"
    echo "  kg-memory start"
    echo "  kg-memory stop"
    echo "  kg-memory status"
    echo "  kg-memory restart"
    echo "  kg-memory logs"
else
    echo ""
    echo "⚠ $BIN_DIR is NOT in your PATH"
    echo ""
    echo "Add this to your ~/.bashrc or ~/.zshrc:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
    echo "Then run: source ~/.bashrc (or restart your terminal)"
fi
