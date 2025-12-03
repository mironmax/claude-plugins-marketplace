# Knowledge Graph Plugin for Claude Code

Extract and remember patterns, insights, and relationships worth preserving across sessions.

## Features

- 🧠 **Capture Knowledge** - Extract patterns, insights, relationships as you work
- ⚡ **Fast Operations** - In-memory operations via MCP server for instant access
- 🔄 **Git-Style Sync** - Pull latest updates before decisions, last-write-wins
- 🌐 **Multi-Session** - Share knowledge across all Claude Code sessions and agents
- 🎯 **Two Levels** - User (cross-project) and Project (codebase-specific)
- 📝 **Immediate Capture** - Extract insights as they emerge, not at end of session

## Installation

### Via Marketplace (Recommended)

```bash
# 1. Add the marketplace
/plugin marketplace add mironmax/claude-plugins-marketplace

# 2. Install the plugin
/plugin install memory@maxim-plugins

# 3. Add CLAUDE.md instructions (append to existing or create new)
# If you don't have ~/.claude/CLAUDE.md:
cp ~/.claude/plugins/memory/templates/CLAUDE.md ~/.claude/CLAUDE.md
# If you already have it, manually append the content from the template

# 4. Restart Claude Code
```

The plugin automatically:
- Sets up Python environment on first use
- Configures user-level MCP server
- Creates knowledge directories

**Important:** The `CLAUDE.md` template contains instructions for Claude to automatically load and use the knowledge graph. If you already have `~/.claude/CLAUDE.md`, append the template content instead of overwriting. Without these instructions, you'll need to manually call `kg_read()` at the start of each session.

## Quick Start

Once installed with `CLAUDE.md` template, the knowledge graph loads automatically at session start.

### Enable Auto-Approval (Optional)

To avoid permission prompts, add to `~/.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "mcp__plugin_memory_kg__kg_read",
      "mcp__plugin_memory_kg__kg_register_session",
      "mcp__plugin_memory_kg__kg_put_node",
      "mcp__plugin_memory_kg__kg_put_edge",
      "mcp__plugin_memory_kg__kg_sync",
      "mcp__plugin_memory_kg__kg_delete_node",
      "mcp__plugin_memory_kg__kg_delete_edge"
    ]
  }
}
```

This applies globally to all projects. Without this, Claude will ask for approval on first use of each tool.

For detailed usage examples and best practices, run `/skill memory`.

## Usage

### Available Tools

- `kg_read()` - Read full knowledge graph (returns both user and project levels)
- `kg_register_session()` - Register session for sync tracking (returns session_id)
- `kg_sync(session_id)` - Get changes since this session started (diff-based)
- `kg_put_node(level, id, gist, ...)` - Add/update insights and concepts
- `kg_put_edge(level, from, to, rel, ...)` - Add/update relationships
- `kg_delete_node(level, id)` - Remove a node
- `kg_delete_edge(level, from, to, rel)` - Remove an edge

### Commands

- `/kg-sync` - Sync latest updates from other sessions
- `/skill memory` - Detailed documentation

### When to Capture

Capture **immediately** as insights emerge:
- Architectural decisions & rationales
- Relationships between code/concepts
- Patterns observed
- Corrections from debugging
- Mental models & abstractions
- Open questions & technical debt

### User vs Project Level

**User level** (`~/.claude/knowledge/user.json`):
- Cross-project patterns
- Personal preferences
- General wisdom

**Project level** (`.knowledge/graph.json`):
- Codebase-specific relationships
- Project decisions
- Local conventions

**Test:** "Would this make sense to a teammate who cloned the repo?" → Project. Otherwise → User.

## Architecture

```
MCP Server (stdio transport)
├── In-memory graphs (user + project)
├── Version tracking (internal, never sent to LLM)
├── Session registry for sync
├── Thread-safe concurrent access
├── Periodic disk sync (30s)
└── Graceful shutdown with final persist
```

**Performance:**
- Fast in-memory operations (read/write/sync)
- Diff-based sync (returns only changes, not full graph)
- No Python startup overhead (persistent MCP server)

## Multi-Session Collaboration

The knowledge graph supports real-time collaboration across parallel sessions using session tracking and diff-based sync. All sessions share the same MCP server, and changes are visible via `kg_sync()`.

**Last write wins** - sync frequently when collaborating. Use `/kg-sync` or `/skill memory` for details.

## Configuration

### Environment Variables

Set in MCP configuration:
- `KG_USER_PATH` - User graph location (default: `~/.claude/knowledge/user.json`)
- `KG_PROJECT_PATH` - Project graph location (default: `.knowledge/graph.json`)
- `KG_SAVE_INTERVAL` - Auto-save interval in seconds (default: `30`)

## Documentation

- **Auto-loading instructions**: `~/.claude/CLAUDE.md` (copy from `templates/CLAUDE.md`)
  - Tells Claude to load knowledge graph at session start
  - Enables automatic session registration
  - Must be manually copied after installation
- **Detailed guide**: `/skill memory` - In-depth usage and examples
- **This README**: Overview, installation, and quick start

## Uninstallation

```bash
/plugin uninstall memory@maxim-plugins
```

Your knowledge graph data will be preserved in `~/.claude/knowledge/` and `.knowledge/`.

## Development

```bash
# Clone for development
git clone https://github.com/mironmax/knowledge-graph-plugin.git
cd knowledge-graph-plugin

# Install dependencies
cd server
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Contributing

Issues and pull requests welcome!

## License

MIT License - see [LICENSE](LICENSE) file

## Version

0.3.1

**Changes in 0.3.1:**
- Performance improvements and consistency fixes
- Improved logging and operational efficiency

**Changes in 0.3.0:**
- Simplified `kg_read()` API (removed optional level parameter)
- Added permissions setup documentation
- Improved multi-session collaboration docs
