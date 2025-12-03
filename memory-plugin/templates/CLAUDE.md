# Knowledge Graph

## Session Start

On session start, load the knowledge graph into context.

### Action

Call `kg_read()` to load both user and project knowledge graphs, then `kg_register_session()` to enable sync tracking.

### Sequence

1. `kg_read()` - Full graph load into context
2. `kg_register_session()` - Get session_id, store it for later sync calls

### When This Runs

- New session start
- Context clear (`/clear`)

Does NOT run on:
- Resume (context already has graph)
- Compact (would lose session continuity)

### Why

The knowledge graph contains patterns, insights, and relationships discovered in previous sessions. Loading at start ensures continuity of understanding without manual intervention.

Session registration enables real-time collaboration - other agents/sessions can write to the graph, and this session can pull their changes via `kg_sync(session_id)`.

## Knowledge processing

Extract and remember patterns, insights, and relationships worth preserving across sessions.

**What to capture:**
- Patterns observed (architectural, behavioral, conceptual)
- Relationships discovered (between code, concepts, decisions)
- Corrections and learnings from debugging
- Mental models and named abstractions
- Open questions and technical considerations
- Rationales behind choices made

**When to capture:**
Immediately as insights emerge - capture in the same response where you notice them. Don't defer to end of conversation. Context is freshest at the moment of discovery.

**How to capture:**
Use MCP tools: `kg_put_node` (insights/concepts) or `kg_put_edge` (relationships).
Capture while working, not as a separate step.

**Syncing (conflict resolution):**
- Before important decisions, sync first: call `kg_read` to get latest updates
- Last write wins - frequent syncs ensure you have current context
- Use `/kg-sync` or ask to "sync knowledge graph" when collaborating across sessions

**Subagent coordination:**
When spawning subagents that need domain knowledge:
- Include instruction: "First call kg_read to load knowledge graph"
- For simple tasks (grep, file ops): skip graph load (unnecessary context)
- Subagent contributions automatically visible to parent via shared MCP server

**Key principles:**
- Maximum insight per symbol added
- Prefer edges when connecting existing things, nodes when naming new concepts
- User-level: cross-project wisdom; Project-level: codebase-specific knowledge
- Capture imperfectly rather than lose understanding

For detailed structure and examples: `/skill knowledge-graph`
