I'll review the repository for opportunities to streamline and any inconsistencies. Here's my analysis:

---

## Streamlining Recommendations

### 1. **Redundant Documentation**
- `CLAUDE.md` template and `SKILL.md` overlap significantly (session workflow, capture principles, sync instructions). Consolidate: CLAUDE.md should be minimal hook instructions only; SKILL.md holds all detail.

### 2. **README.md Bloat**
- Installation shown twice (marketplace + manual) with nearly identical steps
- "Multi-Session Collaboration" section repeats what's in SKILL.md
- Quick Start code examples duplicate the SKILL.md examples
- **→ Trim README to: install, one usage example, link to `/skill memory` for details**

### 3. **Unused `session_id` Parameter**
- `kg_put_node`, `kg_put_edge`, `kg_delete_*` all accept `session_id` for tracking, but the delete methods don't actually use it (they remove version info instead of bumping it)
- Either track deletions properly or remove the param from delete signatures

### 4. **Server Logging Verbosity**
- Every put/delete logs at INFO level. For high-frequency ops this clutters. Consider DEBUG for individual ops, INFO only for session lifecycle.

### 5. **Index Rebuild Inefficiency**
- `delete_node` and `delete_edge` rebuild entire index after one deletion. For bulk deletes this is O(n²). Consider lazy rebuild or tombstone marking.

---

## Inconsistencies

| Location | Issue |
|----------|-------|
| `plugin.json` says v0.3.0, matches `marketplace.json` ✓ | — |
| README says "v1.1.0" for session tracking feature | Contradicts v0.3.0 everywhere else |
| `CLAUDE.md`: "Does NOT run on: Resume, Compact" | No mechanism enforces this; it's just guidance |
| `.mcp.json` uses `kg` as server name | Server code uses `"knowledge-graph"` — mismatch (cosmetic but confusing) |
| README auto-approval permissions use `mcp__plugin_memory_kg__*` | Assumes specific plugin install path; may not match actual MCP server registration |

---

## Quick Wins
1. **Remove** the "v1.1.0" reference in README (or update version consistently)
2. **Align** MCP server name: `kg` everywhere or `knowledge-graph` everywhere
3. **Dedupe** by making CLAUDE.md ~10 lines (just the hook), everything else lives in SKILL.md
4. **Drop** `session_id` param from delete methods (it's unused)
