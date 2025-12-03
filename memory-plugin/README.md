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

### Manual Installation

```bash
# 1. Clone the marketplace repository
git clone https://github.com/mironmax/claude-plugins-marketplace.git /tmp/claude-marketplace

# 2. Copy the plugin to Claude Code plugins directory
cp -r /tmp/claude-marketplace/memory-plugin ~/.claude/plugins/memory

# 3. Add CLAUDE.md instructions to your config
# Append content from ~/.claude/plugins/memory/templates/CLAUDE.md
# to ~/.claude/CLAUDE.md (create if it doesn't exist)

# 4. Restart Claude Code
```

## Quick Start

Once installed with `CLAUDE.md` template, the knowledge graph automatically:
1. Loads at session start via `kg_read()`
2. Registers session via `kg_register_session()` for sync tracking

### Optional: Enable Auto-Approval

To avoid permission prompts for memory plugin tools, add to `~/.claude/settings.json`:

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

This applies globally to all projects. Create the file if it doesn't exist. Without this, Claude will ask for approval on first use of each tool.

**Capture knowledge immediately:**
```javascript
// When you discover a pattern
kg_put_node(
  level="user",
  id="prefer-composition",
  gist="Prefer composition over inheritance in Python",
  notes=["Increases flexibility and testability"]
)

// When you find a relationship
kg_put_edge(
  level="project",
  from="config.py",
  to="main.py",
  rel="must-load-before",
  notes=["Config needs to initialize before main runs"]
)
```

**Sync to see changes from other sessions/agents:**
```javascript
// Pull latest updates before important decisions
kg_sync(session_id="your-session-id")

// Or use the slash command
/kg-sync
```

**For subagents needing domain knowledge:**
```
When spawning: "First call kg_read to load knowledge graph"
```

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

## Conflict Resolution

**Last write wins** - sync frequently when collaborating:
- Before important decisions: `/kg-sync`
- When running multiple parallel sessions
- After spawning subagents that may have contributed

## Multi-Session Collaboration

The knowledge graph supports real-time collaboration across parallel sessions using session tracking and diff-based sync.

### How It Works

**Session Tracking (v1.1.0+):**
1. Each session registers via `kg_register_session()` → receives unique `session_id`
2. All writes track: version number, timestamp, and originating session
3. `kg_sync(session_id)` returns **only changes** since that session started
4. Metadata stored server-side, never sent to LLM (memory-efficient)

**Example - Parallel Sessions Workflow:**
```javascript
// Session A (Terminal 1)
kg_register_session()  // → {session_id: "abc123", start_ts: 1234567890}

// Meanwhile, Session B (Terminal 2) writes:
// node-1, node-2, edge-1

// Session A syncs to see B's changes
kg_sync("abc123")
// Returns: {total_changes: 3, changes: {nodes: [node-1, node-2], edges: [edge-1]}}
// Only diffs, not full graph!
```

### Use Cases

**Parallel Sessions:**
- Run multiple Claude Code instances simultaneously
- All sessions share the same MCP server
- Changes from any session visible to others via `kg_sync()`
- Common when working on related tasks in parallel

**Subagent Coordination:**
- Include "First call kg_read to load knowledge graph" when spawning for domain tasks
- Skip for simple operations (grep, file ops)
- Subagent writes immediately visible to parent via `kg_sync()`

**Best Practices:**
- Call `kg_sync()` before important decisions to pull latest updates
- Last write wins - sync frequently when collaborating
- Each session maintains its own view until explicit sync

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

0.3.0

**Changes in 0.3.0:**
- Simplified `kg_read()` API (removed optional level parameter)
- Added permissions setup documentation
- Improved multi-session collaboration docs
