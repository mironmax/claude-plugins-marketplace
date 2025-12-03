# Knowledge Graph

## Session Start Hook

On new session or `/clear`, immediately:

1. `kg_read()` — Load full graph into context
2. `kg_register_session()` — Get session_id for sync tracking

This runs automatically based on these instructions. Do not skip.

## Core Behavior

**Capture knowledge as you work** and do it often.

What to capture:
- All bits important for future work
- Patterns and insights discovered
- Relationships between artefacts, code, concepts, decisions
- Corrections from debugging
- Rationales behind choices
- Learning from mistakes

How to capture:
- `kg_put_node` — New insight or concept
- `kg_put_edge` — Relationship between existing things
- Prefer edges over nodes when possible

Levels:
- `user` — Cross-project wisdom, personal patterns
- `project` — Codebase-specific knowledge

## Memory Traces

When the graph grows large, older/less-connected nodes get archived automatically. But their edges remain visible — you'll see relationships pointing to nodes not in your view.

These are "memory traces" — hints that relevant knowledge exists. Use `kg_recall(level, id)` to bring archived nodes back when you need deeper context for a task. Do as many of recalls as you need to find necessary context.

## Collaboration

- Call `kg_sync(session_id)` to pull updates from all other sessions
- Review updates from other sessions if exists, then proceed

## Details

For full API reference, scoring algorithm, and examples: `/skill memory`
