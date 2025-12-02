# Maxim's Claude Code Plugins Marketplace

A collection of Claude Code plugins for enhanced development workflows.

## Available Plugins

### Knowledge Graph
Extract and remember patterns, insights, and relationships worth preserving across sessions.

**Features:**
- 🧠 Capture knowledge as you work
- ⚡ Sub-millisecond operations (in-memory MCP server)
- 🔄 Git-style sync for multi-agent collaboration
- 🎯 User & Project level knowledge separation
- 📝 Immediate capture with conflict resolution

**Repository:** [knowledge-graph-plugin](https://github.com/mironmax/knowledge-graph-plugin)

## Installation

### 1. Add This Marketplace

```
/plugin marketplace add mironmax/claude-plugins-marketplace
```

### 2. Install Plugins

```
/plugin install knowledge-graph@maxim-plugins
```

### 3. Run Plugin Setup

After installation, each plugin requires its setup script to be run:

```bash
# For knowledge-graph plugin:
~/DevProj/knowledge-graph-plugin/scripts/install.sh

# Then follow the prompts to configure the MCP server
```

**Note:** Plugin install clones the repository but doesn't run setup automatically for security reasons.

### 4. Restart Claude Code

The plugin will be available after restart.

## Manual Installation

If you prefer manual installation, see each plugin's repository for instructions.

## Contributing

Have a plugin to add? Open a PR with updates to `.claude-plugin/marketplace.json`

## License

Each plugin has its own license. See individual plugin repositories for details.
