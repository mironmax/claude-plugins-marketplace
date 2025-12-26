# Memory Plugin - Architecture Documentation

## Origin & Evolution

### The Problem Space

Daily work with Claude Code revealed recurring patterns:
- **Repetitive prompting** - Same context repeated across sessions  
- **Token waste** - Re-explaining established patterns and preferences
- **Brittle solutions** - Hardcoded CLAUDE.md files couldn't evolve
- **Missing continuity** - No learning from past sessions

**Need identified:** A self-improving, evolving knowledge structure that captures patterns, preferences, and insights automatically.

### Iteration 1: Cipher + Embeddings + Graph DB (2024, Rejected)

**System:** ByteRover/Cipher engine with external dependencies

**Architecture:**
```
Cipher Engine (librarian/retrieval LLM)
  ↓
Local Docker Containers:
  - Qdrant (vector embeddings)
  - Neo4j (graph database)
  ↓
External API Services:
  - Embedding API (text → vectors)
  - LLM API (semantic search)
```

**Why it failed:**

1. **Cost & Latency**
   - Required external embedding service (API costs)
   - LLM "librarian" for every retrieval (extra API calls)
   - Network latency on local containers
   - Operational complexity (Docker management)

2. **Embeddings Were Not Useful Enough**
   - Captured semantic similarity, not critical facts
   - Missed "always relevant" knowledge
   - No guarantee important details surfaced
   - Lost nuance in vector space compression

3. **Graph Database Overhead**
   - Complex Neo4j setup and queries
   - Over-engineered for actual needs
   - Graph structure didn't provide expected value
   - Query complexity >> benefit

4. **Concurrent Access Issues**
   - Container coordination complexity
   - File/DB sync problems

**Conclusion:** Complicated system with marginal results.

---

### Iteration 2: Claude Self-Developed MCP (Early 2024)

**Key innovations:**

1. **JSON as Knowledge Container** ✅  
   - **Brilliant insight**: Use simple JSON files
   - Local, no external dependencies  
   - Human-readable and editable
   - Version controllable (git)
   - LLMs read JSON natively (no transformation)

2. **User-Defined Memory Pattern** ✅
   - CLAUDE.md instructions guide what to capture
   - LLM decides relevance during conversation
   - Flexible schema, evolves with needs

**Problems:**
- ❌ Concurrent access → file corruption (simultaneous writes)
- ❌ Retrieval relevance gaps (missed important facts)
- ❌ No automatic pruning/evolution

---

### Iteration 3: Advanced Retrieval Algorithms (Mid 2024)

**Approach:** Solve retrieval problem with sophisticated search

**Implementation:**
```
Query Processing:
1. Extract important terms from query
2. TF-IDF search for "entry points" into graph
3. Steiner tree algorithm (find optimal paths between entry points)
4. Centrality avoidance (surface peripheral, non-central facts)
```

**Improvements:**
- ✅ Much better relevance than embeddings
- ✅ Found connections between concepts  
- ✅ Avoided over-representing central nodes
- ✅ Based on research papers (rigorous approach)

**Still insufficient:**
- ❌ Retrieval-time complexity didn't solve root cause
- ❌ Important non-connected facts still missed
- ❌ Over-reliance on graph structure
- ❌ Added algorithmic complexity without proportional benefit

**Key realization:** The problem isn't retrieval—it's **what** and **how** we store.

---

### Current Design: Compression-First Architecture (Late 2024 - Present)

**Paradigm shift:** Move complexity from **retrieval** to **entry** and **curation**.

#### Core Principles

1. **Compress on Entry, Not Retrieval**
   - **Insight**: LLM best at compression during creation, not search
   - Capture knowledge in distilled form immediately
   - Store only what truly matters (human-curated by AI)
   - No need for complex retrieval if storage is right

2. **Automatic Pruning & Evolution**  
   - Archival system based on usage, connectivity, recency
   - Auto-compaction when token limits reached
   - Self-cleaning (orphan node removal after grace period)
   - Knowledge graph evolves like living memory

3. **LLM-Native Format** 
   - LLMs read JSON graphs directly, fluently
   - No transformation layer (embeddings, queries, etc.)
   - Direct loading into context window
   - Simple beats clever

4. **Dual-Mode Access**
   - **Always loaded**: Core knowledge in every session (~5000 tokens)
   - **Recall on demand**: Archived nodes retrieved when needed
   - **Memory traces**: Edges to archived nodes guide discovery
   - Sequential reading surfaces "hidden" knowledge

#### Why This Works

**Load everything by default:**
- 5000 token budget for active knowledge
- LLM scans entire graph in milliseconds
- No query language or retrieval algorithms
- Simple `kg_read()` → full context

**When memory grows beyond limit:**
- Archival scores nodes by: recency (50%) + connectivity (30%) + file mentions (20%)
- Archive bottom 20% least-important nodes
- Keep edges to archived nodes (memory traces)
- `kg_recall(id)` resurrects archived nodes on demand

**Memory traces enable graph traversal:**
- See edge to archived node → know something related exists
- Traverse via `kg_recall()` → surface hidden knowledge
- Sequential reading reconstructs context

**Result:** Simplicity + reliability >> algorithmic complexity

---

## Current Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Claude Code Sessions                      │
│  Session A (project-a)    Session B (project-b)    Session C │
└────────────┬──────────────────────┬───────────────────┬──────┘
             │                      │                   │
             │ HTTP MCP (stateless) │                   │
             └──────────┬───────────┘                   │
                        ↓                               │
             ┌──────────────────────────────┐          │
             │  MCP Streamable HTTP Server  │          │
             │  (mcp_streamable_server.py)  │          │
             │                              │          │
             │  Endpoints:                  │          │
             │  - / (MCP protocol)          │◄─────────┘
             │  - /api/* (REST API)         │
             │  - /health (status)          │
             └──────────┬───────────────────┘
                        │
                        ↓
             ┌──────────────────────────────┐
             │  MultiProjectGraphStore      │
             │  - User graph (singleton)    │
             │  - Project graphs (N)        │
             │  - Auto-save (30s interval)  │
             │  - Auto-compact (5000 tokens)│
             └──────────┬───────────────────┘
                        │
                ┌───────┴────────┐
                ↓                ↓
      ┌─────────────────┐  ┌──────────────────┐
      │  user.json      │  │  project graphs  │
      │  ~/.claude/     │  │  .knowledge/     │
      │  knowledge/     │  │  graph.json      │
      └─────────────────┘  └──────────────────┘
```

---

### Transport Layer: Why Stateless HTTP?

**Decision: Stateless HTTP + Manual Sync (Polling)**

This requires explanation because it seems suboptimal at first glance.

#### The Stateful vs Stateless Question

We have internal "session" mechanism for sync (`kg_sync()`) that seems similar to what push notifications could provide. Multiple agents working in parallel, or even different projects sharing user-level graph—sounds perfect for server-push architecture, right?

**Evaluated options:**

1. **Stateful Streamable HTTP with Push**
   - Server maintains session IDs
   - Pushes updates via Server-Sent Events (SSE)
   - Real-time notification when other agents modify graph

2. **Stateless HTTP with Polling**
   - Each request independent (no session tracking)
   - Agents call `kg_sync()` explicitly to check for updates
   - Manual, not automatic

**Why we chose stateless despite having "session-like" needs:**

#### Claude Code MCP Client Constraints

**From official documentation (verified 2025-12-26):**

Claude Code's MCP client implementation:
- ✅ Supports: HTTP (stateless request/response)
- ❌ Does NOT support: Stateful session ID tracking
- ❌ Does NOT support: Server-sent event (SSE) handling for push notifications
- ⚠️ SSE transport: Deprecated in MCP spec (March 2025)

**Empirical evidence:**
```
With stateless=False (stateful mode):
  Client → POST / (initialize)
  Server → Response with mcp-session-id: abc123
  
  Client → POST / (tools/call kg_ping)
  ❌ No mcp-session-id header sent!
  Server → ERROR: "No valid session ID provided"

With stateless=True:
  Client → POST / (initialize)
  Server → Creates transport, responds ✅
  
  Client → POST / (tools/call kg_ping)  
  Server → Creates new transport, responds ✅
```

**Conclusion:** Claude Code client doesn't preserve session IDs between requests. Stateful mode incompatible with actual client implementation.

#### Why Not Implement Our Own Push?

**WebSocket for push exists** (`mcp_http/websocket.py`) but it's **separate from MCP protocol**.

**Problem:** Can't modify Claude Code's MCP client
- We don't control how Claude Code spawns/manages MCP connections
- Client is part of Claude Code core, not extensible
- MCP SDK client doesn't expose WebSocket hooks

**If we added WebSocket to MCP layer:**
- Claude Code client wouldn't connect to it
- Would require forking/patching Claude Code
- Breaks with updates

**Separation of concerns is cleaner:**
```
MCP Protocol (HTTP) ← Claude Code agents (read-only from our perspective)
WebSocket          ← Visual editor (we control the client)
```

#### Implementation Complexity Analysis

**Stateless HTTP + Polling:**
- Complexity: ⭐ (current state)
- Works with Claude Code client ✅
- Simple mental model ✅
- No connection management ✅
- Debuggable ✅

**Stateful HTTP + Push:**
- Complexity: ⭐⭐⭐
- Requires client support ❌
- Connection management overhead ❌
- Doesn't work with actual client ❌

**WebSocket (for visual editor):**
- Complexity: ⭐⭐ (already implemented!)
- Perfect for browser clients ✅
- Real-time updates ✅
- Separate concern from MCP ✅

#### Why Polling is Acceptable

**"But multiple agents need sync!"** — Yes, and polling handles this fine:

**Low overhead in practice:**
- Few concurrent sessions (typically 1-3 agents)
- Infrequent sync calls (on-demand, not continuous polling)
- Small payloads (JSON diffs, only changed nodes/edges)
- No persistent connection overhead

**Explicit is better than implicit:**
- Agent explicitly calls `kg_sync()` when it needs updates
- Clear in logs when sync happens
- No "ghost" behavior from background push
- Predictable, debuggable

**When polling would be insufficient:**
- 10+ concurrent agents on same project (high contention)
- Sub-second update requirements (we don't have this)
- Thousands of sync calls per minute (we have ~1-10)

#### Future: When to Reconsider

**Revisit push-based MCP if:**
- Claude Code SDK officially supports stateful Streamable HTTP
- MCP spec adds WebSocket transport
- We build custom agent client (not using Claude Code)
- Usage patterns show high sync frequency (>100/min)

**For visual editor (Phase 5): Use WebSocket** ✅
- Browser clients handle WebSocket natively
- Real-time graph visualization needs push
- Already implemented (`ConnectionManager`)
- Clean separation: MCP (polling) + WebSocket (push)

---

### Final Transport Architecture

```
┌─────────────────┐         ┌──────────────┐
│ Claude Agents   │         │ Visual Editor│
│ (Claude Code)   │         │  (Browser)   │
└────────┬────────┘         └──────┬───────┘
         │                         │
   Stateless HTTP            WebSocket
   (MCP protocol)         (Real-time push)
         │                         │
         └────────► Server ◄───────┘
                      ↓
           MultiProjectGraphStore
                      ↓
              Broadcast updates
              (store → WebSocket clients)
```

**Both patterns coexist:**
- MCP tools: Explicit sync via `kg_sync()` (polling)
- Visual editor: Implicit updates via WebSocket (push)
- Same underlying store, different transport needs

**Result:** Best of both worlds, no compromises.

---

## Storage Layer

### File Structure

```
~/.claude/knowledge/
  └── user.json              # Cross-project insights (singleton)

<project-root>/.knowledge/
  └── graph.json             # Project-specific knowledge
```

### Why JSON Files?

**Decision rationale** (learned from Iteration 1 failure):

1. **Human-readable** — Inspect/edit with any text editor
2. **Version controllable** — Git tracks changes, diffs meaningful  
3. **Local** — No external dependencies, databases, or services
4. **Simple** — One concept, one format
5. **LLM-native** — Claude reads JSON fluently, no transformation
6. **Portable** — Copy file = backup/share knowledge

**Trade-off accepted:** File I/O instead of DB transactions (mitigated by in-memory store + atomic writes)

---

## Future Development Directions

### 1. Visual Editor (Phase 5-6)  
- D3.js force-directed graph  
- Real-time via WebSocket ✅ (infrastructure ready)
- CRUD operations
- Multi-panel UI

### 2. History Scraper
- Parse past Claude Code conversation logs
- LLM extracts insights retroactively
- Backfill knowledge graph from existing work
- Bootstrap new graph with historical context

### 3. Codebase Scraper  
- Command: `/memory-scan` (or similar)
- Analyze project architecture, patterns, conventions
- Generate compressed knowledge nodes
- Link to file paths (`touches` field)
- New sessions start with project context pre-loaded

### 4. Planned Features
- Collaborative editing (multi-user visual editor)
- Import/export (share graph snippets)
- Search interface (full-text + graph traversal)
- Analytics (graph metrics, usage patterns)
- Plugin ecosystem (custom archival/scoring algorithms)

---

## Design Philosophy Summary

### Lessons Learned Through Iteration

1. **Simplicity > Algorithmic Sophistication**
   - Complex retrieval (Steiner trees, centrality avoidance) didn't solve core problem
   - Simple loading + good compression >> complex search + poor storage

2. **Compression on Entry > Transformation on Retrieval**
   - LLM best at distillation during creation
   - Store insights, not raw data
   - No retrieval algorithms if storage is right

3. **LLM-Native Formats > Specialized Representations**
   - JSON beats embeddings for our use case
   - Direct context loading beats semantic search
   - Human-readable beats optimized-for-machines

4. **Explicit > Implicit**
   - `kg_sync()` polling beats hidden push notifications
   - Clear when sync happens, visible in logs
   - Debuggable, predictable

5. **Local > External Services**
   - JSON files beat graph databases
   - In-process beats containers/APIs
   - Simple operations, simple debugging

6. **Evolution > Perfection**
   - Archival allows growth while staying focused
   - Memory traces enable discovery without loading everything
   - Self-cleaning via usage patterns

---

**Last Updated:** 2025-12-26  
**Version:** 0.5.12  
**Architecture Status:** Stable (MCP complete, Visual editor pending)
