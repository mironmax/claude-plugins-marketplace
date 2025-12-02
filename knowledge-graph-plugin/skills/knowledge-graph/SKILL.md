---
name: knowledge-graph
description: Extract and remember required knowledge from any conversations
---

# Knowledge Graph Extraction

## Approach

Extract patterns, insights, and relationships worth remembering. Anything that might be again needed in future work. Example: decisions, mental models, behavioral patterns, rationales, corrections, learnings from mistakes, open questions, and relationships that make knowledge *legible* and *actionable* across sessions.

Each extracted unit should be atomic and linkable. Prefer discovering a *relationship between existing things* over minting a new concept. Create a new node only when an insight is truly orphan — when it cannot attach to what already exists.

Compressing the senses: use as short entries as you can, while retaining as much information as possible, in the way that human may reconstruct it fluently, maximum recovered insight per added symbol.

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

The test: "Would this make sense to a teammate who cloned the repo?" If yes → project. If it's about you, your personal preferences, working environment or applicable accross all projects → user.

## Usage

The knowledge graph is available via MCP tools (fast, in-memory with auto-persistence)

Most of the time it is read automatically on session start or clear.

**Read the graph:**
```
kg_read()  // Returns both user and project graphs
kg_read(level="user")  // Just user graph
```

**Add or update a node:**
```
kg_put_node(
  level="user",
  id="pattern-name",
  gist="The insight itself",
  touches=["file.py", "concept"],  // optional
  notes=["Context or rationale"]   // optional
)
```

**Add or update an edge:**
```
kg_put_edge(
  level="project",
  from="config.py",
  to="main.py",
  rel="must-load-before",
  notes=["Discovered during debugging"]  // optional
)
```

**Delete operations:**
```
kg_delete_node(level="user", id="node-id")
kg_delete_edge(level="project", from="a", to="b", rel="depends-on")
```

Level is always required: `user` or `project`.

**Timing:** Capture immediately when insights emerge, ideally in the same response where you discover them.

## Principles

- Prefer edges over nodes
- Prefer adding notes to existing entries over creating new ones
- Let content be fluid — capture imperfectly over losing insight
- Level is always required — forces conscious choice about scope
- The graph is a living patch, not a schema to satisfy

## Conflict Resolution & Syncing

**Last write wins:** When multiple sessions modify the same node/edge, the most recent write overwrites previous versions.

**Best practices:**
- Before important architectural decisions, sync first: `kg_read()`
- In collaborative scenarios (multiple agents/sessions), sync frequently
- After major discoveries, consider if other sessions need to sync
- Use explicit sync rather than automatic - maintains clarity and control

**Sync command:**
```
kg_read()  // Fetches latest from MCP server
```

Or ask: "Sync the knowledge graph" / "Check for knowledge updates"

## Multi-Agent Collaboration

**Subagent coordination:**
- When spawning subagents needing domain knowledge, include: "First call kg_read to load knowledge graph"
- For simple tasks (file operations, searches), skip graph load
- Subagent changes immediately visible to parent via shared MCP server
- Parent can sync after subagent completes to review contributions

**Session coordination:**
- All sessions connect to same MCP server (single source of truth)
- Changes are immediately visible to all connected sessions
- Explicit `kg_read()` fetches latest state into your context


## Prunning

- update nodes and edges that are outdated, but partially valid
- delete nodes or edges that are no longer valid
