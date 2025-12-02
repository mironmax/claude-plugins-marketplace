#!/bin/bash
set -e

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KNOWLEDGE_DIR="${HOME}/.claude/knowledge"
VENV_DIR="${PLUGIN_DIR}/server/venv"
SERVER_PATH="${PLUGIN_DIR}/server/server.py"

echo "📦 Installing Knowledge Graph Plugin..."

# Create knowledge directory
mkdir -p "$KNOWLEDGE_DIR"
echo "✓ Created knowledge directory: $KNOWLEDGE_DIR"

# Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "✓ Virtual environment created"
fi

# Install dependencies
echo "Installing dependencies..."
"$VENV_DIR/bin/pip" install -q -r "$PLUGIN_DIR/server/requirements.txt"
echo "✓ Dependencies installed"

# Add CLAUDE.md snippet if not already present
CLAUDE_MD="${HOME}/.claude/CLAUDE.md"
TEMPLATE="${PLUGIN_DIR}/templates/CLAUDE.md"

if [ -f "$TEMPLATE" ]; then
    if [ ! -f "$CLAUDE_MD" ]; then
        cp "$TEMPLATE" "$CLAUDE_MD"
        echo "✓ Created ~/.claude/CLAUDE.md from template"
    else
        # Check if knowledge graph section exists
        if ! grep -q "## Knowledge Graph" "$CLAUDE_MD"; then
            echo "" >> "$CLAUDE_MD"
            cat "$TEMPLATE" >> "$CLAUDE_MD"
            echo "✓ Added Knowledge Graph section to ~/.claude/CLAUDE.md"
        else
            echo "ℹ Knowledge Graph section already exists in CLAUDE.md"
        fi
    fi
fi

echo ""
echo "✅ Knowledge Graph Plugin installed successfully!"
echo ""
echo "📋 Configure MCP server scope:"
echo ""
echo "   User-level (global, all projects):"
echo "   $ claude mcp add --transport stdio --scope user knowledge-graph -- ${VENV_DIR}/bin/python3 ${SERVER_PATH}"
echo ""
echo "   Project-level (this project only):"
echo "   $ claude mcp add --transport stdio --scope project knowledge-graph -- ${VENV_DIR}/bin/python3 ${SERVER_PATH}"
echo ""
echo "   Local (default):"
echo "   $ claude mcp add --transport stdio knowledge-graph -- ${VENV_DIR}/bin/python3 ${SERVER_PATH}"
echo ""
echo "💡 Restart Claude Code after adding the MCP server"
echo "📚 Documentation: /skill knowledge-graph"
echo "📊 Tools: kg_read, kg_put_node, kg_put_edge, kg_delete_node, kg_delete_edge"
