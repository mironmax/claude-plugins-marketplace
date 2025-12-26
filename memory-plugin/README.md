# Knowledge Graph, Memory Plugin for Claude Code

Extract and remember patterns, insights, and relationships worth preserving across sessions.

## Features

- 🧠 **Persistent Memory** — Knowledge survives across sessions
- ⚡ **Fast Operations** — In-memory with periodic disk sync
- 🔄 **Multi-Session** — Share knowledge across parallel sessions and agents
- 🎯 **Two Levels** — User (cross-project) and Project (codebase-specific)
- 🗜️ **Auto-Compaction** — Automatically manages context window size
- ♻️ **Memory Traces** — Archived knowledge remains discoverable

## Important notes

Most of the time system works out of the box. But one useful pattern is this:
1. Do not go for context compaction, it is wasteful, I think. Instead try to finish session with some tangible result, like completing task altogether or writing transient results into. Then clear the session and start anew, now reading this file as input.
2. Before the end of each session, explicitly say that you are wrapping up the session. That would often trigger some additional memory writes. But also take a few minutes for reflection what was working and what's not. This helps to create some overarching learning.

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

To skip permission prompts, add these permissions to your `~/.claude/settings.json`:

**If you don't have a settings.json yet**, create it with:

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

**If you already have a settings.json**, add the permissions to your existing `permissions.allow` array:

```json
{
  "permissions": {
    "allow": [
      // ... your existing permissions ...
      "mcp__plugin_memory_kg__kg_read",
      "mcp__plugin_memory_kg__kg_register_session",
      "mcp__plugin_memory_kg__kg_put_node",
      "mcp__plugin_memory_kg__kg_put_edge",
      "mcp__plugin_memory_kg__kg_sync",
      "mcp__plugin_memory_kg__kg_delete_node",
      "mcp__plugin_memory_kg__kg_delete_edge",
      "mcp__plugin_memory_kg__kg_recall"
    ],
    "deny": [/* ... your existing denies ... */]
  }
}
```

⚠️ **Important**: Don't append the entire JSON object if you already have settings — merge the permissions into your existing `allow` array to avoid JSON syntax errors.

## Usage

### Server Management

The plugin uses a **shared MCP server** that runs in the background. The server starts automatically on first use, but you have full control over it.

**Check server status:**
```bash
cd ~/.claude/plugins/memory/server
./manage_server.sh status
```

**Manual control (if needed):**
```bash
# Start server
./manage_server.sh start

# Stop server
./manage_server.sh stop

# Restart server
./manage_server.sh restart

# View logs
./manage_server.sh logs
```

**If server is not running:**
- The plugin will show an error when you try to use memory tools
- Simply run `./manage_server.sh start` from the server directory
- Or restart Claude Code to auto-start the server

**Server details:**
- Endpoint: `http://127.0.0.1:8765/`
- Health check: `http://127.0.0.1:8765/health`
- Logs: `/tmp/mcp_server.log`
- PID file: `~/.claude/plugins/memory/server/.mcp_server.pid`

**Advanced: systemd service (optional)**

For auto-start on boot and auto-restart on crashes (Linux only):

```bash
# Link service file
mkdir -p ~/.config/systemd/user
ln -s ~/.claude/plugins/memory/server/memory-mcp.service ~/.config/systemd/user/

# Enable and start
systemctl --user enable memory-mcp.service
systemctl --user start memory-mcp.service

# Check status
systemctl --user status memory-mcp.service
```

Note: Using systemd service is optional. The default `manage_server.sh` approach gives you more direct control.

### Working with Knowledge Graph

Once the server is running:

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

## Backup and Recovery

The plugin automatically creates tiered backups to protect against data corruption or accidental changes:

### Backup Tiers

1. **Recent backups** (3 copies) — `.json.bak.1`, `.bak.2`, `.bak.3`
   - Created hourly (minimum 1 hour between backups)
   - Most recent snapshots

2. **Daily backups** (7 copies) — `.json.bak.daily.1` through `.bak.daily.7`
   - One backup per day, kept for 7 days
   - Provides coverage for recent changes

3. **Weekly backups** (4 copies) — `.json.bak.weekly.1` through `.bak.weekly.4`
   - One backup per week, kept for 4 weeks
   - Long-term recovery option

### Recovery

If you need to restore from a backup:

```bash
# For user-level graph:
cp ~/.claude/knowledge/user.json.bak.1 ~/.claude/knowledge/user.json

# For project-level graph:
cp .knowledge/graph.json.bak.daily.3 .knowledge/graph.json
```

Choose the appropriate backup tier based on when the corruption occurred. The plugin will automatically reload on next session.

### Atomic Writes

All saves use atomic writes (write-to-temp, then rename) to prevent corruption from interrupted writes.

## Uninstallation

```bash
/plugin uninstall memory@maxim-plugins
```

Your knowledge data is preserved in the locations above.

## License

MIT License — see [LICENSE](LICENSE)

## Version

0.4.2

### Changelog

**0.4.2**
- Fixed backup tier promotion logic (oldest backups now properly promote to next tier)
- Added session_id tracking to recall() for sync consistency
- Removed unused helper methods and TypeVar
- Moved static utility methods to module level for cleaner code
- Added level validation to all public methods
- Standardized type hints to use Python 3.10+ `X | None` syntax

**0.4.1**
- Code refactoring and tiered backup strategy improvements

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
