# Knowledge Graph Plugin for Claude Code

Extract and remember patterns, insights, and relationships worth preserving across sessions.

## Features

- 🧠 **Capture Knowledge** - Extract patterns, insights, relationships as you work
- ⚡ **Fast Operations** - In-memory operations via MCP server for instant access
- 🔄 **Git-Style Sync** - Pull latest updates before decisions, last-write-wins
- 🌐 **Multi-Session** - Share knowledge across all Claude Code sessions and agents
- 🎯 **Two Levels** - User (cross-project) and Project (codebase-specific)
- 📝 **Immediate Capture** - Extract insights as they emerge, not at end of session
- 🗜️ **Auto-Compaction** - Automatically archives low-value nodes when over token limit
- ♻️ **Smart Archiving** - Recoverable nodes with memory traces (edges remain visible)

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
      "mcp__plugin_memory_kg__kg_delete_edge",
      "mcp__plugin_memory_kg__kg_recall"
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
- `kg_recall(level, id)` - Retrieve an archived node back into active context

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

The plugin is configured via `.mcp.json` in the plugin directory. After installation, you can customize these values by editing `~/.claude/plugins/memory/.mcp.json`:

```json
{
  "mcpServers": {
    "kg": {
      "command": "bash",
      "args": ["${CLAUDE_PLUGIN_ROOT}/server/start.sh"],
      "env": {
        "KG_USER_PATH": "${HOME}/.claude/knowledge/user.json",
        "KG_PROJECT_PATH": ".knowledge/graph.json",
        "KG_SAVE_INTERVAL": "30",
        "KG_MAX_TOKENS": "5000",
        "KG_ORPHAN_GRACE_DAYS": "7",
        "KG_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

**Variable descriptions:**
- `KG_USER_PATH` - User-level graph location (cross-project knowledge)
- `KG_PROJECT_PATH` - Project-level graph location (codebase-specific)
- `KG_SAVE_INTERVAL` - Auto-save interval in seconds (default: 30)
- `KG_MAX_TOKENS` - Token limit before compaction triggers (default: 5000)
- `KG_ORPHAN_GRACE_DAYS` - Days before orphaned archived nodes are permanently deleted (default: 7)
- `KG_LOG_LEVEL` - Logging verbosity: DEBUG, INFO, WARNING, ERROR (default: INFO)

### Auto-Compaction

The knowledge graph automatically manages its size to stay within context window limits:

**How it works:**
- Archives low-value nodes when exceeding `KG_MAX_TOKENS`
- Nodes are scored by recency (7-day half-life), connectedness, and richness
- Session-protected: nodes created/modified in current session never archived
- Archived nodes remain on disk, recoverable via `kg_recall(level, id)`
- Orphaned archived nodes (no connections to active nodes) deleted after grace period
- "Memory traces": edges to archived nodes remain visible, indicating recoverable knowledge

**Tuning compaction:**
- Lower `KG_MAX_TOKENS` (e.g., 3000) for more aggressive compaction
- Higher values (e.g., 8000) to keep more nodes active
- Adjust `KG_ORPHAN_GRACE_DAYS` to control how long disconnected nodes are kept

See `/skill memory` for detailed compaction behavior and scoring algorithm.

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

0.4.0

**Changes in 0.4.0:**
- **Auto-Compaction**: Automatically archives low-value nodes when over token limit
- **Smart Archiving**: Archived nodes remain on disk with recoverable "memory traces"
- **Node Scoring**: Multi-factor scoring (recency, connectedness, richness) for intelligent archiving
- **Session Protection**: Nodes from current session never archived
- **Orphan Cleanup**: Automatic deletion of disconnected archived nodes after grace period
- **New Tool**: `kg_recall(level, id)` to retrieve archived nodes back into context
- **Configuration**: Added `KG_MAX_TOKENS` and `KG_ORPHAN_GRACE_DAYS` environment variables
- **Documentation**: Comprehensive docs on compaction behavior and tuning

**Changes in 0.3.1:**
- Performance improvements and consistency fixes
- Improved logging and operational efficiency

**Changes in 0.3.0:**
- Simplified `kg_read()` API (removed optional level parameter)
- Added permissions setup documentation
- Improved multi-session collaboration docs
