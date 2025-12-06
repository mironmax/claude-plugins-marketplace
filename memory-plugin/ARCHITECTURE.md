# Memory — Knowledge Graph Plugin — Architecture

A persistent memory system for Claude Code that captures memories in the form of patterns, insights, and relationships across sessions.
Overall pattern reminiscent of natural memory:
- it is a graph rather then plain text, thing are connected, not repeated, this in itself saves space
- there is always active part, archive, and orphans. Active part contains traces to archived, system can recall memories using traces. Orphans forgotten forever after a while.
- compress on save, system does not save elaborate facts, rather pointers and references

---

## Who This Is For

**Ideal user**: Indie developer or small team using Claude Code who wants:
- Cross-session memory without external services
- Zero ongoing costs (no API calls, no cloud)
- Explicit control over what gets remembered
- Portable data (JSON files you own)

**Not ideal for**:
- Need semantic search (you can use local vector DB)
- Building autonomous long-running agents (you can use specialised file based pipe`lines)
- Enterprise with complex relationship queries (you can use various memory solutions, those are plenty)
- Simple use cases → CLAUDE.md files are built-in and sufficient

---

## Why This Exists

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Memory Approach Spectrum                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  PASSIVE                      HYBRID                     ACTIVE     │
│  (CLAUDE.md)              (This Plugin)            (Mem0, Byterover)│
│                                                                     │
│  • Manual edits            • Explicit capture         • Auto-extract│
│  • No management           • Auto-compaction          • LLM calls   │
│  • Grows forever           • Multi-session sync       • Vector DB   │
│  • Free                    • Free                     • $$ per op   │
│                                                                     │
│  Simple ◄──────────────────────────────────────────────► Powerful   │
│                                 ▲                                   │
│                                 │                                   │
│                          Sweet spot for                             │
│                          indie developers                           │
└─────────────────────────────────────────────────────────────────────┘
```

The plugin fills a gap: smarter than static CLAUDE.md files, simpler than Mem0/Letta/Byterover. 

**Key insight**: The value isn't in storing everything — it's in capturing and compressing *learnings*. The patterns matter more than facts that can be recovered from files.

---

## Core Idea

```
                    Claude Sessions
                         
    ┌─────────┐       ┌─────────┐       ┌─────────┐
    │Session A│       │Session B│       │Session C│
    └────┬────┘       └────┬────┘       └────┬────┘
         │                 │                 │
         └─────────────────┼─────────────────┘
                           ▼
                  ┌────────────────┐
                  │   MCP Server   │  ← Long-running, in-memory
                  │  (persistent)  │    Fast reads/writes, periodic save
                  └───────┬────────┘
                          │
            ┌─────────────┴─────────────┐
            ▼                           ▼
      ┌───────────┐              ┌───────────┐
      │user.json  │              │graph.json │
      │ ~/.claude │              │ .knowledge│
      └───────────┘              └───────────┘
       Cross-project              Project-specific
         wisdom                     knowledge
```

The server stays alive across sessions. Disk sync every 30s.

---

## Data Model

Two primitives: **Nodes** and **Edges**

```
┌─ Node ─────────────────────────────────┐
│ id: silent-dependency-pattern          │
│ gist: hidden load-order deps fail late │
│ touches: [config.py, db/init.py]       │
│ notes: [seen 3x, worth lint rule?]     │
└────────────────────────────────────────┘

┌─ Edge ─────────────────────────────────┐
│ from: config.py                        │
│ to: db/init.py                         │
│ rel: must-load-before                  │
│ notes: [discovered debug cold-start]   │
└────────────────────────────────────────┘
```

**Design principle**: Connect existing things rather than creating new abstractions. Create nodes rather then adding note to existing. Compress information on write.

---

## Two Knowledge Levels

```
┌─ User Level (~/.claude/knowledge/) ────────────────────────┐
│                                                            │
│  [meta-cognitive-trap-1]  [architectural-principle-x]      │
│  [interaction-pattern-focus]                               │
│                                                            │
│  Cross-project wisdom. Travels with you.                   │
└────────────────────────────────────────────────────────────┘
                           │
                           │ informs
                           ▼
┌─ Project Level (.knowledge/) ──────────────────────────────┐
│                                                            │
│  [config-load-order]  [api-v2-migration]  [auth-module]    │
│                                                            │
│  Codebase-specific. Shareable via git (or gitignore).      │
└────────────────────────────────────────────────────────────┘
```

| Level | Scope | Contains |
|-------|-------|----------|
| **User** | All projects | Process insights, interaction patterns, principles |
| **Project** | Single codebase | Code relationships, decisions, debugging discoveries |

---

## Core Scenarios

### 1. Session Lifecycle

```
Session Start:
  Claude ──── kg_read() ────────────► Server
         ◄── {user: {...}, project: {...}} ──┘
  Claude ──── kg_register_session() ► Server
         ◄── {session_id: "a1b2c3d4"} ──────┘

During Work:
  Claude ──── kg_put_node(...) ─────► Server (in-memory)
         ◄── {action: "added"} ─────────────┘

Background (every 30s):
  Server ──── save if dirty ────────► Disk
```

### 2. Multi-Session Sync

```
Session A                    Server                    Session B
    │                          │                           │
    ├── register_session() ───►│◄─── register_session() ───┤
    │◄── session_id: "aaaa" ───┤───► session_id: "bbbb" ──►│
    │                          │                           │
    ├── put_node(discovery-x) ►│                           │
    │                          │                           │
    │                          │◄────── kg_sync("bbbb") ───┤
    │                          ├──► {changes: [discovery-x]}│
    │                          │                           │
    │            Session B sees A's write via sync         │
```

**Pull before push** in collaborative scenarios.

### 3. Auto-Compaction

When graph exceeds threshold (5000 tokens by default), lowest-scored nodes archive:

```
┌─ Active Context ───────────────────────────────────────────┐
│  [recent-bug-fix]  [api-design-decision]  [auth-pattern]   │
└────────────────────────────────────────────────────────────┘
                              │
                              │ edge remains visible
                              ▼ ("memory trace")
┌─ Archived (hidden from kg_read) ───────────────────────────┐
│  [old-migration-note]  [deprecated-pattern]                │
│                                                            │
│  Still on disk. Use kg_recall(id) to restore.              │
└────────────────────────────────────────────────────────────┘
```

**Scoring**: `recency × connectedness × richness` (percentile-based)

- Nodes updated within 7 days = protected (never archived)
- Edges to archived nodes stay visible = memory traces
- `kg_recall(id)` restores archived nodes

### 4. Memory Traces

```
kg_read() returns:
  nodes: [auth-module]
  edges: [auth-module ──influenced-by──► old-security-decision]
                                               │
                                               └─ Not in nodes!
                                                  = memory trace

If relevant to current task:
  kg_recall("old-security-decision")
  └─► Node restored to active context
```

Node id naming is often enough for system to understand that it needs to call this or that node. Memory traces are always present, as being loaded on kg_read.

---

## API Summary

| Tool | Purpose |
|------|---------|
| `kg_read()` | Load full graph (session start) |
| `kg_register_session()` | Get session_id for sync tracking |
| `kg_sync(session_id)` | Get changes from other sessions |
| `kg_put_node(level, id, gist, ...)` | Add/update node |
| `kg_put_edge(level, from, to, rel, ...)` | Add/update edge |
| `kg_delete_node(level, id)` | Remove node + connected edges |
| `kg_delete_edge(level, from, to, rel)` | Remove edge |
| `kg_recall(level, id)` | Restore archived node |
| `kg_ping()` | Health check, stats |

---

## What to Capture

Priority hierarchy (highest value first):

1. **Meta-patterns** — "I tend to search when I should trace"
2. **Principles** — Architectural insights that apply across projects
3. **Patterns** — Recurring code relationships, deliberate decisions
4. **Facts** — Pointers to artifacts (keep minimal, prefer edges)

**Test**: "Would this help avoid a similar mistake in a different project?" → User level
**Test**: "Is this specific to how this codebase works?" → Project level

---

## File Structure

```
memory-plugin/
├── server/
│   ├── server.py        # MCP server, in-memory store, all logic
│   ├── start.sh         # Auto-setup wrapper (venv, deps)
│   └── requirements.txt
├── skills/memory/
│   └── SKILL.md         # Full API reference (/skill memory)
├── templates/
│   └── CLAUDE.md        # Session hooks, behavior guidance
└── .mcp.json            # Server configuration
```

Data locations:
- `~/.claude/knowledge/user.json` — User-level graph
- `.knowledge/graph.json` — Project-level graph
