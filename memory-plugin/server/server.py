#!/usr/bin/env python3
"""
Knowledge Graph MCP Server
Maintains in-memory knowledge graph with periodic disk persistence.
Provides sub-millisecond read/write operations.
Supports session tracking for diff-based sync.
"""

import asyncio
import json
import os
import sys
import logging
import time
import threading
import uuid
from pathlib import Path
from typing import Any, Optional

# Configure logging to stderr (never stdout for MCP)
log_level = os.getenv("KG_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

# MCP Protocol imports
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    logger.error("MCP SDK not installed. Run: pip install mcp")
    sys.exit(1)


class KnowledgeGraphStore:
    """Thread-safe in-memory knowledge graph with periodic persistence and session tracking."""

    # Session TTL: 24 hours (in seconds)
    SESSION_TTL = 24 * 60 * 60

    # Grace period: nodes updated within this period are protected from archiving
    GRACE_PERIOD_DAYS = 7

    # Compaction configuration (overridable via env vars)
    KG_MAX_TOKENS = int(os.getenv("KG_MAX_TOKENS", "5000"))
    KG_ORPHAN_GRACE_DAYS = int(os.getenv("KG_ORPHAN_GRACE_DAYS", "7"))

    def __init__(self, user_path: Path, project_path: Path, save_interval: int = 30):
        self.user_path = user_path
        self.project_path = project_path
        self.save_interval = save_interval

        # In-memory graphs (dict-based for O(1) operations)
        # nodes: {node_id: node_dict}
        # edges: {(from, to, rel): edge_dict}
        self.graphs = {
            "user": {"nodes": {}, "edges": {}},
            "project": {"nodes": {}, "edges": {}}
        }

        # Version tracking (server-internal, never sent to LLM)
        # Key format: "node:{id}" or "edge:{from}->{to}:{rel}"
        self._versions = {
            "user": {},
            "project": {}
        }

        # Session tracking
        self._sessions = {}  # session_id -> {"start_ts": timestamp}

        # Thread safety
        self.lock = threading.RLock()
        self.dirty = {"user": False, "project": False}

        # Background saver
        self.running = True
        self.saver_thread = threading.Thread(target=self._periodic_save, daemon=True)

        # Load from disk
        self._load_all()
        self.saver_thread.start()

        logger.info(f"Knowledge graph initialized: user={user_path}, project={project_path}")

    def _edge_key(self, from_ref: str, to_ref: str, rel: str) -> str:
        """Generate string key for edge storage on disk."""
        return f"{from_ref}->{to_ref}:{rel}"

    def _parse_edge_key(self, key: str) -> tuple[str, str, str]:
        """Parse edge key back to (from, to, rel)."""
        arrow_idx = key.index("->")
        colon_idx = key.rindex(":")
        return key[:arrow_idx], key[arrow_idx + 2:colon_idx], key[colon_idx + 1:]

    def _load_all(self):
        """Load graphs from disk."""
        for level, path in [("user", self.user_path), ("project", self.project_path)]:
            if path.exists():
                try:
                    with open(path) as f:
                        data = json.load(f)

                    # Extract metadata
                    if "_meta" in data:
                        self._versions[level] = data["_meta"].get("versions", {})

                    # Load nodes (already dict format)
                    self.graphs[level]["nodes"] = {
                        k: v for k, v in data.get("nodes", {}).items()
                        if k != "_meta"
                    }

                    # Load edges (convert string keys to tuple keys internally)
                    edges_data = data.get("edges", {})
                    self.graphs[level]["edges"] = {}
                    for key, edge in edges_data.items():
                        tuple_key = (edge["from"], edge["to"], edge["rel"])
                        self.graphs[level]["edges"][tuple_key] = edge

                    logger.info(f"Loaded {level} graph: {len(self.graphs[level]['nodes'])} nodes, {len(self.graphs[level]['edges'])} edges")
                except Exception as e:
                    logger.error(f"Failed to load {level} graph: {e}")

    def _save_to_disk(self, level: str):
        """Save graph to disk."""
        path = self.user_path if level == "user" else self.project_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)

            # Convert edges from tuple keys to string keys for JSON
            edges_for_disk = {
                self._edge_key(e["from"], e["to"], e["rel"]): e
                for e in self.graphs[level]["edges"].values()
            }

            data = {
                "nodes": self.graphs[level]["nodes"],
                "edges": edges_for_disk,
                "_meta": {"versions": self._versions[level]}
            }

            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Saved {level} graph to disk")
            return True
        except Exception as e:
            logger.error(f"Failed to save {level} graph: {e}")
            return False

    def _node_token_cost(self, node: dict) -> int:
        """Per-node token estimate. ~20 tokens overhead + content at ~4 chars/token."""
        return 20 + len(node.get("gist", "")) // 4 + \
               sum(len(n) // 4 for n in node.get("notes", []))

    def _estimate_tokens(self, level: str) -> int:
        """Calculate token estimate for a level. Only active nodes count."""
        nodes = self.graphs[level]["nodes"]
        edges = self.graphs[level]["edges"]

        active_tokens = sum(
            self._node_token_cost(n)
            for n in nodes.values()
            if not n.get("_archived")
        )
        edge_tokens = len(edges) * 15  # ~15 tokens per edge

        return active_tokens + edge_tokens

    def _score_nodes(self, level: str) -> dict[str, float]:
        """
        Percentile-based scoring. Higher score = more valuable = keep longer.

        Nodes within 7-day grace period are excluded (not returned).
        Remaining nodes scored by percentile rank in three dimensions:
        - Recency (last update timestamp)
        - Connectedness (edge count + touches)
        - Richness (gist length + notes length)

        Final score = recency_pct × connectedness_pct × richness_pct
        """
        current_time = time.time()
        grace_period_seconds = self.GRACE_PERIOD_DAYS * 24 * 60 * 60

        # Count edges per node
        edge_count = {}
        for edge in self.graphs[level]["edges"].values():
            edge_count[edge["from"]] = edge_count.get(edge["from"], 0) + 1
            edge_count[edge["to"]] = edge_count.get(edge["to"], 0) + 1

        # Collect eligible nodes (past grace period)
        eligible = []
        for node_id, node in self.graphs[level]["nodes"].items():
            if node.get("_archived"):
                continue

            version_key = self._version_key_node(node_id)
            version = self._versions[level].get(version_key, {})
            last_update = version.get("ts", current_time)
            age_seconds = current_time - last_update

            # Grace period: skip nodes updated within last 7 days
            if age_seconds < grace_period_seconds:
                continue

            eligible.append({
                "id": node_id,
                "recency_raw": -age_seconds,  # Negative so higher = fresher
                "connectedness_raw": edge_count.get(node_id, 0) + len(node.get("touches", [])),
                "richness_raw": len(node.get("gist", "")) + sum(len(n) for n in node.get("notes", []))
            })

        if not eligible:
            return {}

        # Percentile ranking helper
        def assign_percentiles(items: list, raw_key: str, pct_key: str):
            sorted_items = sorted(items, key=lambda x: x[raw_key])
            n = len(sorted_items)
            for i, item in enumerate(sorted_items):
                item[pct_key] = i / (n - 1) if n > 1 else 0.5

        assign_percentiles(eligible, "recency_raw", "recency_pct")
        assign_percentiles(eligible, "connectedness_raw", "connectedness_pct")
        assign_percentiles(eligible, "richness_raw", "richness_pct")

        # Final score = product of percentiles
        scores = {}
        for item in eligible:
            scores[item["id"]] = item["recency_pct"] * item["connectedness_pct"] * item["richness_pct"]

        return scores

    def _maybe_compact(self, level: str):
        """
        Compact graph if over token limit.
        Archive lowest-scored nodes until estimate <= 90% of max.
        """
        # Fresh calculation
        estimated_tokens = self._estimate_tokens(level)

        if estimated_tokens <= self.KG_MAX_TOKENS:
            return

        logger.info(f"Compacting {level} graph: {estimated_tokens} tokens > {self.KG_MAX_TOKENS} limit")

        # Score all active nodes (excluding grace-protected)
        scores = self._score_nodes(level)

        if not scores:
            logger.debug(f"No nodes eligible for archiving in {level} graph (all within grace period)")
            return

        # Sort by score (ascending - lowest scores first)
        sorted_nodes = sorted(scores.items(), key=lambda x: x[1])

        # Archive until we're under 90% of target
        target = int(self.KG_MAX_TOKENS * 0.9)
        archived_count = 0

        for node_id, score in sorted_nodes:
            if estimated_tokens <= target:
                break

            node = self.graphs[level]["nodes"].get(node_id)
            if node and not node.get("_archived"):
                # Calculate token cost before archiving
                token_cost = self._node_token_cost(node)

                # Archive the node
                node["_archived"] = True

                # Update estimate
                estimated_tokens -= token_cost
                archived_count += 1

                logger.debug(f"Archived node '{node_id}' (score: {score:.2f}, tokens: {token_cost})")

        logger.info(f"Compaction complete: archived {archived_count} nodes, now ~{estimated_tokens} tokens")

        if archived_count > 0:
            self.dirty[level] = True

    def _prune_orphans(self, level: str):
        """
        Prune orphaned archived nodes (those with no active connections).
        Sets _orphaned_ts on newly orphaned nodes, deletes after grace period.
        """
        nodes = self.graphs[level]["nodes"]
        edges = self.graphs[level]["edges"]

        # Build set of active node IDs
        active_ids = {node_id for node_id, node in nodes.items() if not node.get("_archived")}

        # Build set of reachable archived nodes (connected to active nodes)
        reachable = set()
        for edge in edges.values():
            if edge["from"] in active_ids:
                reachable.add(edge["to"])
            if edge["to"] in active_ids:
                reachable.add(edge["from"])

        # Process archived nodes
        current_time = time.time()
        grace_seconds = self.KG_ORPHAN_GRACE_DAYS * 24 * 60 * 60
        to_delete = []

        for node_id, node in nodes.items():
            if not node.get("_archived"):
                continue

            if node_id in reachable:
                # Connected to active nodes - clear orphaned timestamp
                if "_orphaned_ts" in node:
                    del node["_orphaned_ts"]
                    self.dirty[level] = True
                    logger.debug(f"Node '{node_id}' reconnected, cleared orphaned timestamp")
            else:
                # Not connected - orphaned
                if "_orphaned_ts" not in node:
                    # Newly orphaned
                    node["_orphaned_ts"] = current_time
                    self.dirty[level] = True
                    logger.debug(f"Node '{node_id}' orphaned, grace period started")
                else:
                    # Check if grace period expired
                    orphaned_duration = current_time - node["_orphaned_ts"]
                    if orphaned_duration > grace_seconds:
                        to_delete.append(node_id)
                        logger.debug(f"Node '{node_id}' grace period expired, marking for deletion")

        # Delete expired orphans
        for node_id in to_delete:
            self._delete_node_internal(level, node_id)
            logger.info(f"Deleted orphaned node '{node_id}' from {level} graph")

    def _delete_node_internal(self, level: str, node_id: str):
        """Internal node deletion with edge cleanup. No lock (caller must hold lock)."""
        nodes = self.graphs[level]["nodes"]
        edges = self.graphs[level]["edges"]

        if node_id not in nodes:
            return False

        # Delete connected edges first
        edges_to_delete = [
            key for key, edge in edges.items()
            if edge["from"] == node_id or edge["to"] == node_id
        ]
        for edge_key in edges_to_delete:
            edge = edges[edge_key]
            del edges[edge_key]
            # Remove version tracking
            version_key = self._version_key_edge(edge["from"], edge["to"], edge["rel"])
            if version_key in self._versions[level]:
                del self._versions[level][version_key]

        # Delete the node
        del nodes[node_id]

        # Remove version tracking
        version_key = self._version_key_node(node_id)
        if version_key in self._versions[level]:
            del self._versions[level][version_key]

        self.dirty[level] = True
        return True

    def _periodic_save(self):
        """Background thread to periodically save dirty graphs."""
        while self.running:
            time.sleep(self.save_interval)
            with self.lock:
                for level in ["user", "project"]:
                    # Run compaction and orphan pruning
                    self._maybe_compact(level)
                    self._prune_orphans(level)

                    # Save if dirty
                    if self.dirty[level]:
                        if self._save_to_disk(level):
                            self.dirty[level] = False
                # Cleanup old sessions
                self._cleanup_old_sessions()

    def _cleanup_old_sessions(self):
        """Remove sessions older than SESSION_TTL."""
        current_time = time.time()
        expired_sessions = [
            session_id for session_id, data in self._sessions.items()
            if current_time - data["start_ts"] > self.SESSION_TTL
        ]
        for session_id in expired_sessions:
            del self._sessions[session_id]
            logger.info(f"Session expired and removed: {session_id}")

    def _version_key_node(self, node_id: str) -> str:
        return f"node:{node_id}"

    def _version_key_edge(self, from_ref: str, to_ref: str, rel: str) -> str:
        return f"edge:{from_ref}->{to_ref}:{rel}"

    def _bump_version(self, level: str, key: str, session_id: Optional[str] = None):
        """Increment version for a key."""
        ts = time.time()
        if key in self._versions[level]:
            self._versions[level][key]["v"] += 1
            self._versions[level][key]["ts"] = ts
            self._versions[level][key]["session"] = session_id
        else:
            self._versions[level][key] = {"v": 1, "ts": ts, "session": session_id}

    def register_session(self, session_id: str) -> dict:
        """Register a new session and return current timestamp."""
        with self.lock:
            ts = time.time()
            self._sessions[session_id] = {"start_ts": ts}
            logger.info(f"Session registered: {session_id}")
            return {"session_id": session_id, "start_ts": ts}

    def read(self) -> dict:
        """
        Read both graphs (user and project). Never includes _meta.
        Returns only active nodes. Edges included if either endpoint is active.
        """
        with self.lock:
            result = {"user": {}, "project": {}}

            for level in ["user", "project"]:
                nodes = self.graphs[level]["nodes"]
                edges = self.graphs[level]["edges"]

                # Filter active nodes only
                active_nodes = {
                    node_id: node for node_id, node in nodes.items()
                    if not node.get("_archived")
                }

                # Build set of active node IDs
                active_ids = set(active_nodes.keys())

                # Filter edges - include if either endpoint is active (shows "memory traces")
                active_edges = [
                    edge for edge in edges.values()
                    if edge["from"] in active_ids or edge["to"] in active_ids
                ]

                result[level] = {
                    "nodes": list(active_nodes.values()),
                    "edges": active_edges
                }

            return result

    def sync(self, session_id: str, exclude_own: bool = True) -> dict:
        """
        Get changes since session start, optionally excluding own writes.
        Returns only the diff, not full graph.
        Same filtering — only returns active nodes in diff.
        """
        with self.lock:
            if session_id not in self._sessions:
                return {"error": "Unknown session. Call register_session first."}

            start_ts = self._sessions[session_id]["start_ts"]
            result = {"user": {"nodes": [], "edges": []}, "project": {"nodes": [], "edges": []}}

            for level in ["user", "project"]:
                nodes = self.graphs[level]["nodes"]
                edges = self.graphs[level]["edges"]

                # Build set of active node IDs for edge filtering
                active_ids = {node_id for node_id, node in nodes.items() if not node.get("_archived")}

                # Find changed nodes (active only)
                for node_id, node in nodes.items():
                    # Skip archived nodes
                    if node.get("_archived"):
                        continue

                    key = self._version_key_node(node_id)
                    ver = self._versions[level].get(key, {})

                    if ver.get("ts", 0) > start_ts:
                        # Skip if it's our own write and exclude_own is True
                        if exclude_own and ver.get("session") == session_id:
                            continue
                        result[level]["nodes"].append(node)

                # Find changed edges (if either endpoint is active)
                for edge in edges.values():
                    # Skip edges with both endpoints archived
                    if edge["from"] not in active_ids and edge["to"] not in active_ids:
                        continue

                    key = self._version_key_edge(edge["from"], edge["to"], edge["rel"])
                    ver = self._versions[level].get(key, {})

                    if ver.get("ts", 0) > start_ts:
                        if exclude_own and ver.get("session") == session_id:
                            continue
                        result[level]["edges"].append(edge)

            # Count changes
            total_changes = sum(
                len(result[l]["nodes"]) + len(result[l]["edges"])
                for l in ["user", "project"]
            )

            return {
                "since_ts": start_ts,
                "changes": result,
                "total_changes": total_changes
            }

    def put_node(self, level: str, node_id: str, gist: str,
                 touches: Optional[list] = None, notes: Optional[list] = None,
                 session_id: Optional[str] = None) -> dict:
        """Add or update a node."""
        with self.lock:
            nodes = self.graphs[level]["nodes"]

            node = {"id": node_id, "gist": gist}
            if touches:
                node["touches"] = touches
            if notes:
                node["notes"] = notes

            action = "updated" if node_id in nodes else "added"
            nodes[node_id] = node

            # Track version
            self._bump_version(level, self._version_key_node(node_id), session_id)
            self.dirty[level] = True

            logger.debug(f"{action.capitalize()} node '{node_id}' in {level} graph")
            return {"action": action, "node": node}

    def put_edge(self, level: str, from_ref: str, to_ref: str, rel: str,
                 notes: Optional[list] = None, session_id: Optional[str] = None) -> dict:
        """Add or update an edge."""
        with self.lock:
            edges = self.graphs[level]["edges"]

            edge = {"from": from_ref, "to": to_ref, "rel": rel}
            if notes:
                edge["notes"] = notes

            edge_key = (from_ref, to_ref, rel)
            action = "updated" if edge_key in edges else "added"
            edges[edge_key] = edge

            # Track version
            self._bump_version(level, self._version_key_edge(from_ref, to_ref, rel), session_id)
            self.dirty[level] = True

            logger.debug(f"{action.capitalize()} edge '{from_ref}' -> '{to_ref}' ({rel}) in {level} graph")
            return {"action": action, "edge": edge}

    def delete_node(self, level: str, node_id: str) -> dict:
        """Delete a node and its connected edges."""
        with self.lock:
            if node_id not in self.graphs[level]["nodes"]:
                return {"deleted": False, "node_id": node_id}

            self._delete_node_internal(level, node_id)
            logger.debug(f"Deleted node '{node_id}' from {level} graph")
            return {"deleted": True, "node_id": node_id}

    def delete_edge(self, level: str, from_ref: str, to_ref: str, rel: str) -> dict:
        """Delete an edge."""
        with self.lock:
            edges = self.graphs[level]["edges"]
            edge_key = (from_ref, to_ref, rel)

            if edge_key not in edges:
                return {"deleted": False, "edge": {"from": from_ref, "to": to_ref, "rel": rel}}

            del edges[edge_key]

            # Remove version tracking
            version_key = self._version_key_edge(from_ref, to_ref, rel)
            if version_key in self._versions[level]:
                del self._versions[level][version_key]

            self.dirty[level] = True
            logger.debug(f"Deleted edge '{from_ref}' -> '{to_ref}' ({rel}) from {level} graph")
            return {"deleted": True, "edge": {"from": from_ref, "to": to_ref, "rel": rel}}

    def recall(self, level: str, node_id: str) -> dict:
        """
        Retrieve an archived node back into active context.
        Removes _archived flag, clears _orphaned_ts, bumps version.
        """
        with self.lock:
            nodes = self.graphs[level]["nodes"]

            if node_id not in nodes:
                return {"error": f"Node '{node_id}' not found in {level} graph"}

            node = nodes[node_id]

            if not node.get("_archived"):
                return {"error": f"Node '{node_id}' is not archived"}

            # Remove archived flag
            del node["_archived"]

            # Clear orphaned timestamp if present
            if "_orphaned_ts" in node:
                del node["_orphaned_ts"]

            # Bump version timestamp (refreshes recency for scoring)
            self._bump_version(level, self._version_key_node(node_id))

            self.dirty[level] = True

            logger.info(f"Recalled node '{node_id}' from {level} graph archive")
            return {"recalled": True, "node": node}

    def shutdown(self):
        """Graceful shutdown with final save."""
        logger.info("Shutting down knowledge graph store...")
        self.running = False
        with self.lock:
            for level in ["user", "project"]:
                if self.dirty[level]:
                    self._save_to_disk(level)
        logger.info("Knowledge graph store shutdown complete")


# Initialize server
app = Server("knowledge-graph")

# Initialize store (will be set on startup)
store: Optional[KnowledgeGraphStore] = None


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available knowledge graph tools."""
    return [
        Tool(
            name="kg_read",
            description="Read the full knowledge graph. Use at session start or when you need complete context. Returns both user and project graphs.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="kg_sync",
            description="Get changes since session start from other sessions/agents. Use for real-time collaboration. Returns only the diff, not full graph. Pull before push.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Your session ID (from kg_register_session)"
                    }
                },
                "required": ["session_id"]
            }
        ),
        Tool(
            name="kg_register_session",
            description="Register this session for sync tracking. Call once at session start, after kg_read. Returns session_id to use with kg_sync.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="kg_put_node",
            description="Add or update a node in the knowledge graph. Pull (kg_sync) before push if collaborating.",
            inputSchema={
                "type": "object",
                "properties": {
                    "level": {"type": "string", "enum": ["user", "project"], "description": "Graph level"},
                    "id": {"type": "string", "description": "Node ID (kebab-case)"},
                    "gist": {"type": "string", "description": "The insight/concept"},
                    "touches": {"type": "array", "items": {"type": "string"}, "description": "Related artifacts"},
                    "notes": {"type": "array", "items": {"type": "string"}, "description": "Additional context"},
                    "session_id": {"type": "string", "description": "Optional: your session ID for tracking"}
                },
                "required": ["level", "id", "gist"]
            }
        ),
        Tool(
            name="kg_put_edge",
            description="Add or update an edge in the knowledge graph. Pull (kg_sync) before push if collaborating.",
            inputSchema={
                "type": "object",
                "properties": {
                    "level": {"type": "string", "enum": ["user", "project"], "description": "Graph level"},
                    "from": {"type": "string", "description": "Source reference"},
                    "to": {"type": "string", "description": "Target reference"},
                    "rel": {"type": "string", "description": "Relationship (kebab-case)"},
                    "notes": {"type": "array", "items": {"type": "string"}, "description": "Additional context"},
                    "session_id": {"type": "string", "description": "Optional: your session ID for tracking"}
                },
                "required": ["level", "from", "to", "rel"]
            }
        ),
        Tool(
            name="kg_delete_node",
            description="Delete a node and its connected edges from the knowledge graph.",
            inputSchema={
                "type": "object",
                "properties": {
                    "level": {"type": "string", "enum": ["user", "project"]},
                    "id": {"type": "string", "description": "Node ID to delete"}
                },
                "required": ["level", "id"]
            }
        ),
        Tool(
            name="kg_delete_edge",
            description="Delete an edge from the knowledge graph.",
            inputSchema={
                "type": "object",
                "properties": {
                    "level": {"type": "string", "enum": ["user", "project"]},
                    "from": {"type": "string"},
                    "to": {"type": "string"},
                    "rel": {"type": "string"}
                },
                "required": ["level", "from", "to", "rel"]
            }
        ),
        Tool(
            name="kg_recall",
            description="Retrieve an archived node back into active context. Use when you see an edge pointing to a node not in your current view.",
            inputSchema={
                "type": "object",
                "properties": {
                    "level": {"type": "string", "enum": ["user", "project"], "description": "Graph level"},
                    "id": {"type": "string", "description": "Node ID to recall"}
                },
                "required": ["level", "id"]
            }
        ),
        Tool(
            name="kg_ping",
            description="Health check for MCP connectivity. Returns server status and statistics.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""
    global store

    try:
        if name == "kg_read":
            result = store.read()
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "kg_register_session":
            session_id = str(uuid.uuid4())[:8]  # Short ID for convenience
            result = store.register_session(session_id)
            return [TextContent(type="text", text=json.dumps(result))]

        elif name == "kg_sync":
            session_id = arguments.get("session_id")
            if not session_id:
                return [TextContent(type="text", text=json.dumps({"error": "session_id required"}))]
            result = store.sync(session_id)
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "kg_put_node":
            result = store.put_node(
                arguments["level"],
                arguments["id"],
                arguments["gist"],
                arguments.get("touches"),
                arguments.get("notes"),
                arguments.get("session_id")
            )
            return [TextContent(type="text", text=json.dumps(result))]

        elif name == "kg_put_edge":
            result = store.put_edge(
                arguments["level"],
                arguments["from"],
                arguments["to"],
                arguments["rel"],
                arguments.get("notes"),
                arguments.get("session_id")
            )
            return [TextContent(type="text", text=json.dumps(result))]

        elif name == "kg_delete_node":
            result = store.delete_node(
                arguments["level"],
                arguments["id"]
            )
            return [TextContent(type="text", text=json.dumps(result))]

        elif name == "kg_delete_edge":
            result = store.delete_edge(
                arguments["level"],
                arguments["from"],
                arguments["to"],
                arguments["rel"]
            )
            return [TextContent(type="text", text=json.dumps(result))]

        elif name == "kg_recall":
            result = store.recall(
                arguments["level"],
                arguments["id"]
            )
            return [TextContent(type="text", text=json.dumps(result))]

        elif name == "kg_ping":
            result = {
                "status": "ok",
                "active_sessions": len(store._sessions),
                "nodes": {
                    "user": len(store.graphs["user"]["nodes"]),
                    "project": len(store.graphs["project"]["nodes"])
                },
                "edges": {
                    "user": len(store.graphs["user"]["edges"]),
                    "project": len(store.graphs["project"]["edges"])
                }
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        logger.error(f"Tool call error: {e}", exc_info=True)
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def main():
    """Main entry point."""
    global store

    # Initialize store with paths from environment or defaults
    user_path = Path(os.getenv("KG_USER_PATH") or (Path.home() / ".claude/knowledge/user.json"))
    project_path = Path(os.getenv("KG_PROJECT_PATH") or ".knowledge/graph.json")
    save_interval = int(os.getenv("KG_SAVE_INTERVAL") or "30")

    store = KnowledgeGraphStore(user_path, project_path, save_interval)

    logger.info("Starting Knowledge Graph MCP Server...")

    try:
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())
    finally:
        if store:
            store.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
