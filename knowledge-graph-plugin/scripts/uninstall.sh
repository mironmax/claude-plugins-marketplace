#!/bin/bash

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KNOWLEDGE_DIR="${HOME}/.claude/knowledge"

echo "🗑️  Uninstalling Knowledge Graph Plugin..."

# Ask about data
echo ""
read -p "Keep knowledge graph data in ${KNOWLEDGE_DIR}? (Y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Nn]$ ]]; then
    rm -rf "$KNOWLEDGE_DIR"
    echo "✓ Knowledge graph data removed"
else
    echo "ℹ Knowledge graph data preserved in ${KNOWLEDGE_DIR}"
fi

# Remove venv
VENV_DIR="${PLUGIN_DIR}/server/venv"
if [ -d "$VENV_DIR" ]; then
    rm -rf "$VENV_DIR"
    echo "✓ Virtual environment removed"
fi

echo ""
echo "✅ Knowledge Graph Plugin uninstalled"
echo ""
echo "📋 Manual cleanup (optional):"
echo "   - Remove Knowledge Graph section from ~/.claude/CLAUDE.md"
echo "   - Plugin directory: ${PLUGIN_DIR}"
