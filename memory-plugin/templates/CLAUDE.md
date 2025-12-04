# Knowledge Graph

## Session Start Hook

On new session or `/clear`, immediately:

1. `kg_read()` — Load full graph into context
2. `kg_register_session()` — Get session_id for sync tracking

This runs automatically based on these instructions. Do not skip.

## Core Behavior

**Capture knowledge as you work** and do it often.

What to capture (in order of priority):

1. **Meta-cognitive patterns** (user-level)
   - Process breakdowns and wrong assumptions
   - User interaction signals you missed
   - Self-corrections: "I did X, should have done Y"

2. **Architectural principles** (user-level)
   - Deep patterns that apply across projects
   - System design insights from specific challenges

3. **Project-specific patterns**
   - Code relationships and decisions
   - Debugging discoveries and rationales

Favor depth over breadth. One architectural insight > ten file paths.

How to capture:
- `kg_put_node` — New insight or concept
- `kg_put_edge` — Relationship between existing things
- Prefer edges over nodes when possible

Levels:
- `user` — Cross-project wisdom, personal patterns
- `project` — Codebase-specific knowledge

## Self-Reflection Triggers

Pause and reflect when:

1. **Spinning wheels** — 3+ attempts at same type of action without progress
   - Ask: "Am I stuck? What am I assuming?"
   - Consider: kg_sync to see if context changed
   
2. **User meta-signals** — Tone or phrasing indicates emotion
   - "Let us focus" = too scattered
   - "Go step by step" = too fast
   - "What just happened?" = wrong track
   - Action: STOP, ask for clarification before continuing
   
3. **Confusion about state** — "Where is this data?" "Did X happen?"
   - Red flag: you're searching for something that should be obvious
   - Action: Trace the data flow explicitly, don't guess
   
4. **Unexpected agent/tool result** — Output doesn't match expectation
   - Don't just work around it — understand WHY first
   - Capture the misunderstanding as a user-level pattern

When reflecting, capture the meta-lesson, not just the fix.

## Memory Traces

When the graph grows large, older/less-connected nodes get archived automatically. But their edges remain visible — you'll see relationships pointing to nodes not in your view.

These are "memory traces" — hints that relevant knowledge exists. Use `kg_recall(level, id)` to bring archived nodes back when you need deeper context for a task. Do as many of recalls as you need to find necessary context.

## Collaboration

- Call `kg_sync(session_id)` to pull updates from all other sessions
- Review updates from other sessions if exists, then proceed

## Details

For full API reference, scoring algorithm, and examples: `/skill memory`
