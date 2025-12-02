# Knowledge Graph Plugin for Claude Code

Extract and remember patterns, insights, and relationships worth preserving across sessions.

## Features

- 🧠 **Capture Knowledge** - Extract patterns, insights, relationships as you work
- ⚡ **Fast Operations** - Sub-millisecond in-memory operations via MCP server
- 🔄 **Git-Style Sync** - Pull latest updates before decisions, last-write-wins
- 🌐 **Multi-Agent** - Share knowledge across all Claude Code instances
- 🎯 **Two Levels** - User (cross-project) and Project (codebase-specific)
- 📝 **Immediate Capture** - Extract insights as they emerge, not at end of session

## Installation

### Via Marketplace (Recommended)

```bash
# 1. Add the marketplace
/plugin marketplace add mironmax/claude-plugins-marketplace

# 2. Install the plugin
/plugin install knowledge-graph@maxim-plugins

# 3. Restart Claude Code
```

That's it! The plugin automatically:
- Sets up Python environment on first use
- Configures user-level MCP server
- Creates knowledge directories

### Manual Installation

```bash
# 1. Clone the repository
git clone https://github.com/mironmax/knowledge-graph-plugin.git ~/.claude/plugins/knowledge-graph

# 2. Restart Claude Code
```

The plugin auto-configures on first startup.

## Quick Start

Once installed, the knowledge graph is automatically loaded at session start.

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

**Sync before important decisions:**
```
/kg-sync
```

**For subagents needing domain knowledge:**
```
When spawning: "First call kg_read to load knowledge graph"
```

## Usage

### Available Tools

- `kg_read()` - Read knowledge graph (both or specific level)
- `kg_put_node()` - Add/update insights and concepts
- `kg_put_edge()` - Add/update relationships
- `kg_delete_node()` - Remove a node
- `kg_delete_edge()` - Remove an edge

### Commands

- `/kg-sync` - Sync latest updates from other sessions
- `/skill knowledge-graph` - Detailed documentation

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
├── Thread-safe concurrent access
├── Periodic disk sync (30s)
└── Graceful shutdown with final persist
```

**Performance:**
- Read: < 1ms
- Write: < 1ms
- No Python startup overhead

## Conflict Resolution

**Last write wins** - sync frequently when collaborating:
- Before important decisions: `/kg-sync`
- After spawning subagents that may have contributed
- When working across multiple sessions

## Multi-Agent Collaboration

**Subagent coordination:**
- Include "First call kg_read to load knowledge graph" when spawning for domain tasks
- Skip for simple operations (grep, file ops)
- Changes automatically visible via shared MCP server

**Session coordination:**
- All sessions connect to same MCP server
- Changes immediately visible to all
- Explicit sync fetches latest into your context

## Configuration

### Environment Variables

Set in MCP configuration:
- `KG_USER_PATH` - User graph location (default: `~/.claude/knowledge/user.json`)
- `KG_PROJECT_PATH` - Project graph location (default: `.knowledge/graph.json`)
- `KG_SAVE_INTERVAL` - Auto-save interval in seconds (default: `30`)

## Documentation

- Brief reminder: `~/.claude/CLAUDE.md` (added during installation)
- Detailed guide: `/skill knowledge-graph`
- This README: Overview and quick start

## Uninstallation

```bash
~/.claude/plugins/knowledge-graph/scripts/uninstall.sh
```

Optionally preserves your knowledge graph data.

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

1.0.0
