# Knowledge Graph Plugin - Summary

## What Was Built

A complete Claude Code plugin for knowledge graph management with sub-millisecond operations.

## Directory Structure

```
~/.claude/plugins/knowledge-graph/
├── .claude-plugin/
│   └── plugin.json          # Plugin manifest
├── server/
│   ├── server.py            # MCP server (in-memory, fast)
│   ├── requirements.txt     # Dependencies (mcp>=0.9.0)
│   └── venv/               # Python virtual environment
├── skills/
│   └── knowledge-graph/
│       └── SKILL.md        # Detailed usage instructions
├── templates/
│   └── CLAUDE.md           # Brief reminder template
├── scripts/
│   ├── install.sh          # Installation script
│   └── uninstall.sh        # Cleanup script
├── .mcp.json              # MCP server definition (reference)
└── README.md              # Complete documentation
```

## Components

### 1. MCP Server
- **Location**: `server/server.py`
- **Type**: stdio transport
- **Performance**: < 1ms operations
- **Storage**: In-memory with periodic disk sync (30s)
- **Tools**: kg_read, kg_put_node, kg_put_edge, kg_delete_node, kg_delete_edge

### 2. Skill
- **Location**: `skills/knowledge-graph/SKILL.md`
- **Purpose**: Detailed principles, structure, examples
- **Invocation**: `/skill knowledge-graph`

### 3. User Instructions
- **Location**: `~/.claude/CLAUDE.md`
- **Purpose**: Brief reminder about when/how to capture
- **Scope**: Always visible to Claude

### 4. Data Storage
- **User graph**: `~/.claude/knowledge/user.json`
- **Project graph**: `.knowledge/graph.json` (per-project)

## Installation & Configuration

### Install
```bash
~/.claude/plugins/knowledge-graph/scripts/install.sh
```

### Configure (choose one scope)

**User-level (global):**
```bash
claude mcp add --transport stdio --scope user knowledge-graph -- \
  ~/.claude/plugins/knowledge-graph/server/venv/bin/python3 \
  ~/.claude/plugins/knowledge-graph/server/server.py
```

**Project-level:**
```bash
claude mcp add --transport stdio --scope project knowledge-graph -- \
  ~/.claude/plugins/knowledge-graph/server/venv/bin/python3 \
  ~/.claude/plugins/knowledge-graph/server/server.py
```

## Architecture Decisions

### Why MCP Server?
- Sub-millisecond operations vs 150ms Python script startup
- Persistent in-memory state
- Multi-agent support
- Real-time updates

### Why Two Levels?
- **User**: Cross-project patterns, personal heuristics
- **Project**: Codebase-specific relationships, decisions

### Why Immediate Capture?
- Context is freshest at moment of discovery
- Prevents forgetting to capture at end
- More natural workflow

### Why Edges Over Nodes?
- Prefer connecting existing things
- Only create nodes for truly orphan concepts
- Maximum insight per symbol

## Usage Philosophy

**Capture patterns, insights, and relationships worth remembering:**
- Architectural decisions & rationales
- Relationships between code/concepts
- Patterns observed (behavioral, architectural)
- Corrections from debugging
- Mental models & abstractions
- Open questions & technical debt

**When:** Immediately as insights emerge, in the same response
**How:** MCP tools (kg_put_node, kg_put_edge)
**Where:** User-level for general wisdom, Project-level for codebase-specific

## Performance

- Read: < 1ms
- Write: < 1ms
- Auto-save: Every 30s
- Crash protection: Max 30s data loss
- No Python startup overhead

## Future Enhancements

- Search/query capabilities
- Graph visualization
- Auto-extraction suggestions
- Conflict resolution for concurrent edits
- Export formats (GraphML, DOT)
- Integration with git history

## Distribution

The plugin is self-contained and can be:
- Copied to other machines
- Committed to version control
- Shared via git repository
- Packaged as tarball

Simply copy `~/.claude/plugins/knowledge-graph/` and run the installation script.
