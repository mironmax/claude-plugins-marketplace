# Maxim's Claude Code Plugins Marketplace

A collection of Claude Code plugins for enhanced development workflows.

## Available Plugins

### Memory (Knowledge Graph)
Extract and remember patterns, insights, and relationships worth preserving across sessions.

**Features:**
- 🧠 Capture knowledge as you work
- ⚡ Fast in-memory operations (persistent MCP server)
- 🔄 Session tracking with diff-based sync (v1.1.0)
- 🤝 Real-time multi-session collaboration
- 🎯 User & Project level knowledge separation
- 📝 Immediate capture with conflict resolution

**Location:** `memory-plugin/` in this marketplace repository

## Installation

### 1. Add This Marketplace

```
/plugin marketplace add mironmax/claude-plugins-marketplace
```

### 2. Install Plugins

```
/plugin install memory@maxim-plugins
```

### 3. Enable Auto-Loading (Important!)

Add the knowledge graph instructions to your Claude configuration:

```bash
# If you don't have ~/.claude/CLAUDE.md yet:
cp ~/.claude/plugins/memory/templates/CLAUDE.md ~/.claude/CLAUDE.md

# If you already have ~/.claude/CLAUDE.md:
# Manually append the content from ~/.claude/plugins/memory/templates/CLAUDE.md
# to your existing file
```

**Why this matters:** The template contains instructions that tell Claude to automatically load the knowledge graph at session start and register for sync tracking. Without it, you'll need to manually call tools each session.

### 4. Restart Claude Code

The plugin will be available after restart.

## Manual Installation

If you prefer manual installation, see each plugin's repository for instructions.

## Contributing

Have a plugin to add? Open a PR with updates to `.claude-plugin/marketplace.json`

## License

Each plugin has its own license. See individual plugin repositories for details.
