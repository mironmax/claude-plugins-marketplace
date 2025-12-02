# /kg-sync

Sync the knowledge graph - fetch latest updates from other sessions.

## Description

Calls `kg_read()` to pull the latest knowledge graph state from the MCP server. Useful when:
- Working across multiple sessions
- Before making important architectural decisions
- After spawning subagents that may have added knowledge
- Collaborating with other agents

## Usage

```
/kg-sync
```

## What it does

1. Fetches current state from MCP server (in-memory)
2. Loads both user and project level graphs into context
3. Makes latest knowledge immediately available

## Conflict Resolution

Last write wins - this sync ensures you have the most recent version before making decisions.

## Examples

```
Before major decisions:
/kg-sync
"Now let's decide on the architecture..."

After subagent completes:
/kg-sync
"Let's review what the subagent discovered..."

In collaborative scenarios:
/kg-sync
"Check if the other session added any patterns..."
```
