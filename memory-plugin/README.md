# Knowledge Graph, Memory Plugin for Claude Code

Extract and remember patterns, insights, and relationships worth preserving across sessions.

## Features

- 🧠 **Persistent Memory** — Knowledge survives across sessions
- ⚡ **Fast Operations** — In-memory with periodic disk sync
- 🔄 **Multi-Session** — Share knowledge across parallel sessions and agents
- 🎯 **Two Levels** — User (cross-project) and Project (codebase-specific)
- 🗜️ **Auto-Compaction** — Automatically manages context window size
- ♻️ **Memory Traces** — Archived knowledge remains discoverable

## Installation

### Via Marketplace

```bash
# 1. Add the marketplace
/plugin marketplace add mironmax/claude-plugins-marketplace

# 2. Install the plugin
/plugin install memory@maxim-plugins

# 3. Add instructions to your CLAUDE.md
# If you don't have ~/.claude/CLAUDE.md yet:
cp ~/.claude/plugins/memory/templates/CLAUDE.md ~/.claude/CLAUDE.md

# If you already have one, append the template content manually

# 4. Restart Claude Code
```

### Enable Auto-Approval (Optional)

Add to `~/.claude/settings.json` to skip permission prompts:

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

## Usage

Once installed with CLAUDE.md template, the knowledge graph loads automatically.

- Claude captures insights as you work
- Knowledge persists across sessions
- Use `/skill memory` for detailed documentation

## Configuration

Edit `~/.claude/plugins/memory/.mcp.json` to customize:

| Variable | Default | Description |
|----------|---------|-------------|
| `KG_USER_PATH` | `~/.claude/knowledge/user.json` | User-level graph location |
| `KG_PROJECT_PATH` | `.knowledge/graph.json` | Project-level graph location |
| `KG_SAVE_INTERVAL` | `30` | Auto-save interval (seconds) |
| `KG_MAX_TOKENS` | `5000` | Token limit before compaction, per graph file |
| `KG_ORPHAN_GRACE_DAYS` | `90` | Days before orphaned nodes deleted |

## Data Locations

- **User level:** `~/.claude/knowledge/user.json` — Cross-project knowledge, never shared
- **Project level:** `.knowledge/graph.json` — Codebase-specific, shareable via git

## Uninstallation

```bash
/plugin uninstall memory@maxim-plugins
```

Your knowledge data is preserved in the locations above.

## License

MIT License — see [LICENSE](LICENSE)

## Version

0.4.0

### Changelog

**0.4.0**
- Auto-compaction with 7-day grace period
- Percentile-based scoring for archiving decisions
- Memory traces: edges to archived nodes remain visible
- `kg_recall` to retrieve archived knowledge
- Node deletion now removes connected edges
- New dict-based file format (breaking change — delete old files before upgrading)

**0.3.x**
- Initial release with multi-session sync
- User and project level separation
