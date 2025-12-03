---
name: memory
description: Extract and remember knowledge across sessions
---

# Knowledge Graph — Full Reference

## Concept

The knowledge graph captures patterns, insights, and relationships worth remembering. Each entry should be atomic and linkable. The goal: maximum recovered insight per added symbol.

Two entry types:

**Nodes** — Named concepts, patterns, or insights
```json
{
  "id": "silent-dependency-pattern",
  "gist": "hidden load-order dependencies that fail late",
  "touches": ["config.py", "db/init.py"],
  "notes": ["seen three times, worth a lint rule?"]
}
```

**Edges** — Relationships between things (files, concepts, nodes)
```json
{
  "from": "config.py",
  "to": "db/init.py",
  "rel": "must-load-before",
  "notes": ["discovered during cold-start debugging"]
}
```

Use short descriptive kebab-case for `id` and `rel`. Reference artifacts directly by path or path:line — no need to wrap them in nodes.

The `touches` field is for light, tentative references — when you sense relevance but the relationship isn't crisp enough to be an edge yet.

The `notes` field holds caveats, rationale, open questions, or any other context. Optional on both edges and nodes.

1. Prefer edges and connect existing things.
2. Create nodes when relationship is not capturing what is needed.
3. Add notes when creating node or edge does not make sense.
4. Add touches, to mark things that may evolve


Compress the meaning: use entries as short as possible while retaining maximum information, in a way humans can reconstruct fluently. Maximum recovered insight per added symbol.

## Levels

**User level** (`~/.claude/knowledge/user.json`):
- Cross-project patterns
- Personal preferences and heuristics
- Reusable concepts
- Never shared

**Project level** (`.knowledge/graph.json`):
- Codebase-specific relationships
- Project decisions and rationales
- Local conventions
- Shareable via git

Test: "Would this make sense to a teammate who cloned the repo?" → Project. Otherwise → User.

## API Reference

### Reading

**`kg_read()`**
Returns both user and project graphs. Active nodes only.
```
→ {"user": {"nodes": [...], "edges": [...]}, "project": {...}}
```

**`kg_sync(session_id)`**
Returns changes since session start, excluding your own writes.
```
→ {"since_ts": 1234567890, "changes": {...}, "total_changes": 5}
```

### Writing

**`kg_put_node(level, id, gist, touches?, notes?, session_id?)`**
Add or update a node.
- `level`: "user" or "project"
- `id`: kebab-case identifier
- `gist`: the insight itself
- `touches`: optional list of related nodes
- `notes`: optional context, caveats, rationale

**`kg_put_edge(level, from, to, rel, notes?, session_id?)`**
Add or update an edge.
- `from`/`to`: node IDs or artifact paths
- `rel`: relationship type (kebab-case)

### Deleting

**`kg_delete_node(level, id)`**
Removes node and all connected edges.

**`kg_delete_edge(level, from, to, rel)`**
Removes a specific edge.

### Session Management

**`kg_register_session()`**
Register for sync tracking. Returns your `session_id`.

**`kg_recall(level, id)`**
Read the archived node and retrieve back into active context.

**`kg_ping()`**
Health check. Returns node/edge counts and active sessions.

## Auto-Compaction

The graph automatically manages its size to fit context windows.

### How It Works

1. Every 30 seconds, system checks token estimate against limit (default: 5000)
2. If over limit, lowest-scored nodes are archived until under 90% of limit
3. Archived nodes remain on disk but hidden from `kg_read()` or `kg_sync()` 
4. Edges from active to archived nodes remain visible ("memory traces")
5. Orphaned archived nodes (no active connections) deleted after grace period

### Scoring Algorithm

Nodes updated within **7 days are protected** — never archived regardless of score.

For older nodes, percentile ranking across three dimensions:

1. **Recency** — When was it last updated? (fresher = higher percentile)
2. **Connectedness** — How many edges + touches? (more = higher percentile)
3. **Richness** — How much content in gist + notes? (more = higher percentile)

Final score = recency_pct × connectedness_pct × richness_pct

Lowest scores archived first.

### Memory Traces

When a node is archived, edges pointing to it from active nodes remain visible. You'll see relationships like:

```
active-node → archived-node-id (relationship)
```

This is intentional — it hints that relevant knowledge exists. When you encounter a memory trace that might be relevant to your current task:

1. Note the archived node ID from the edge
2. Call `kg_recall(level, id)` to bring it back
3. Node returns to active context with refreshed timestamp

This lets you "drill down" into dusty knowledge when you need deeper context.

### Keeping Nodes Alive

Nodes stay active by:
- Being updated (refreshes timestamp → 7-day grace restarts)
- Having edges to active nodes (connectedness score)

If you need to preserve a node, update it occasionally or connect it to active knowledge.

## Multi-Session Collaboration

All sessions share the same MCP server. Changes are eventually shared between with each write and sync.

### Workflow

1. Session A writes a node
2. Session B calls `kg_sync(session_id)` 
3. Session B sees the new node (if written by a different session)

### Conflict Resolution

**Last write wins.** Mitigated by:
- Pull-before-push discipline (sync before important writes)
- Small atomic entries (reduce conflict surface)
- Frequent syncs in collaborative scenarios (ping to know active sessions)

### Subagent Coordination

When spawning subagents/tasks that need domain context:
- Include: "First call kg_read to load knowledge graph"
- Skip for simple tasks (file ops, searches) — unnecessary context

Subagent writes are visible to parent via shared server (eventually). After subagent completes, parent can `kg_sync` to see discoveries.

## Examples

### Capturing a Pattern

```
kg_put_node(
  level="project",
  id="config-load-order",
  gist="Config must load before DB init or connections fail silently",
  touches=["config.py", "db/init.py"],
  notes=["Discovered debugging cold-start issue, took 2 hours"]
)
```

### Recording a Relationship

```
kg_put_edge(
  level="project",
  from="config.py",
  to="db/init.py",
  rel="must-load-before"
)
```

### Recalling Archived Knowledge

You see an edge: `auth-module → old-security-decision (influenced-by)`

```
kg_recall(level="project", id="old-security-decision")
→ {"recalled": true, "node": {"id": "old-security-decision", "gist": "..."}}
```

Now you have context for why auth works the way it does.

## Best Practices

1. **Capture immediately** — Don't defer to end of session. Context is freshest at discovery.

2. **Prefer edges** — Connect existing things rather than creating new nodes.

3. **Be terse** — Maximum insight per symbol. Short gists, minimal notes.

4. **Level consciously** — User for personal wisdom, project for team knowledge.

5. **Sync before push** — In collaborative scenarios, pull updates first.

6. **Follow memory traces** — When you see edges to missing nodes, consider (from its id) if that context matters for your current task.
