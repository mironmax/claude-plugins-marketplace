---
name: knowledge-graph
description: Extract and remember required knowledge from any conversations
---

# Knowledge Graph Extraction

## Approach

Extract patterns, insights, and relationships worth remembering. Anything that might be needed again in future work: decisions, mental models, behavioral patterns, rationales, corrections, learnings from mistakes, open questions, and relationships that make knowledge *legible* and *actionable* across sessions.

Each extracted unit should be atomic and linkable. Prefer discovering a *relationship between existing things* over minting a new concept. Create a new node only when an insight is truly orphan — when it cannot attach to what already exists.

Compressing the senses: use entries as short as possible while retaining maximum information, in a way humans can reconstruct fluently. Maximum recovered insight per added symbol.

## Structure

The graph consists of two types of entries:

**Edges** — relationships discovered between existing things (files, functions, concepts, doc sections).

```json
{
  "from": "config.py",
  "to": "db/init.py",
  "rel": "must-load-before",
  "notes": ["discovered during cold-start debugging"]
}
```

**Nodes** — new concepts, patterns, or named abstractions that emerged and have no home yet.

```json
{
  "id": "silent-dependency-pattern",
  "gist": "hidden load-order dependencies that fail late",
  "touches": ["config.py", "db/init.py"],
  "notes": ["seen three times, worth a lint rule?"]
}
```

Use short descriptive kebab-case for `id` and `rel`. Reference artifacts directly by path or path:line — no need to wrap them in nodes.

The `touches` field is for light, tentative references — when you sense relevance but the relationship isn't crisp enough to be an edge yet.

The `notes` field holds caveats, rationale, open questions, or any other context. Optional on both edges and nodes.

## Levels

**Project level** — lives in project folder (`.knowledge/graph.json`), shareable via git:
- Relationships between this project's artifacts
- Decisions and rationales specific to this codebase
- Discovered patterns in this code
- Open questions about this project

**User level** — lives in home (`~/.claude/knowledge/user.json`), never shared:
- General patterns observed across projects
- Personal preferences and heuristics
- Reusable concepts you've named
- Working style notes

The test: "Would this make sense to a teammate who cloned the repo?" If yes → project. If it's about you, your personal preferences, working environment, or applicable across all projects → user.

## Session Workflow

### Automatic Loading (Hook)

On session start and context clear, the graph loads automatically via hook:
1. `kg_read()` → full graph into context
2. `kg_register_session()` → session_id for sync tracking

You don't need to do this manually.

### During Session

**Capture immediately** when insights emerge:
```
kg_put_node(
  level="user",
  id="pattern-name",
  gist="The insight itself",
  touches=["file.py", "concept"],  // optional
  notes=["Context or rationale"],  // optional
  session_id="your-session-id"     // optional, for tracking
)

kg_put_edge(
  level="project",
  from="config.py",
  to="main.py",
  rel="must-load-before",
  notes=["Discovered during debugging"],
  session_id="your-session-id"
)
```

### Real-Time Collaboration (Sync)

When other sessions or subagents may have written to the graph:

```
kg_sync(session_id="your-session-id")
```

Returns only changes from OTHER sessions since your session started. Your own writes are excluded (already in your context).

**Pull-before-push discipline:**
1. Before important writes, call `kg_sync` first
2. Review diff for relevant new knowledge
3. Reconsider your planned write in light of new info
4. Then write

### Delete Operations

```
kg_delete_node(level="user", id="node-id")
kg_delete_edge(level="project", from="a", to="b", rel="depends-on")
```

## Principles

- Prefer edges over nodes
- Prefer adding notes to existing entries over creating new ones
- Let content be fluid — capture imperfectly over losing insight
- Level is always required — forces conscious choice about scope
- The graph is a living patch, not a schema to satisfy
- Pull before push when collaborating

## Subagent Coordination

**When spawning subagents:**
- For domain tasks needing context: "First call kg_read to load knowledge graph"
- For simple operations (file ops, searches): Skip graph load
- Subagent writes are immediately visible to parent via shared MCP server
- After subagent completes: call `kg_sync` to see what they discovered

**Session coordination:**
- All sessions connect to same MCP server (single source of truth)
- Changes immediately visible to all connected sessions
- Explicit `kg_sync()` fetches latest into your context, excluding your own writes

## Conflict Resolution

**Last write wins.** Mitigated by:
- Pull-before-push discipline
- LLM reconsideration after sync
- Small atomic entries reduce conflict surface
- Frequent syncs in collaborative scenarios

## Pruning

- Update nodes and edges that are outdated but partially valid
- Delete nodes or edges that are no longer valid
- Prefer updating over deleting when in doubt
