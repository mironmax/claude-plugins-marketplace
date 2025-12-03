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

    def __init__(self, user_path: Path, project_path: Path, save_interval: int = 30):
        self.user_path = user_path
        self.project_path = project_path
        self.save_interval = save_interval

        # In-memory graphs (what LLM sees)
        self.graphs = {
            "user": {"nodes": [], "edges": []},
            "project": {"nodes": [], "edges": []}
        }

        # Indexes for O(1) lookups
        self._node_index = {
            "user": {},    # node_id -> list index
            "project": {}
        }
        self._edge_index = {
            "user": {},    # (from, to, rel) tuple -> list index
            "project": {}
        }

        # Version tracking (server-internal, never sent to LLM)
        # Key format: "node:{id}" or "edge:{from}->{to}:{rel}"
        self._versions = {
            "user": {},
            "project": {}
        }

        # Session tracking
        self._sessions = {}  # session_id -> {"start_ts": timestamp, "level": "user"|"project"|"both"}

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

    def _load_all(self):
        """Load graphs from disk."""
        for level, path in [("user", self.user_path), ("project", self.project_path)]:
            if path.exists():
                try:
                    with open(path) as f:
                        data = json.load(f)

                    # Separate graph data from metadata
                    if "_meta" in data:
                        self._versions[level] = data["_meta"].get("versions", {})
                        del data["_meta"]

                    self.graphs[level] = data
                    logger.info(f"Loaded {level} graph: {len(self.graphs[level]['nodes'])} nodes, {len(self.graphs[level]['edges'])} edges")
                except Exception as e:
                    logger.error(f"Failed to load {level} graph: {e}")

        # Rebuild indexes after loading
        self._rebuild_indexes()

    def _rebuild_indexes(self):
        """Rebuild node and edge indexes for fast lookups."""
        for level in ["user", "project"]:
            # Rebuild node index
            self._node_index[level] = {
                node["id"]: i
                for i, node in enumerate(self.graphs[level]["nodes"])
            }
            # Rebuild edge index
            self._edge_index[level] = {
                (edge["from"], edge["to"], edge["rel"]): i
                for i, edge in enumerate(self.graphs[level]["edges"])
            }

    def _save_to_disk(self, level: str):
        """Save graph to disk with metadata."""
        path = self.user_path if level == "user" else self.project_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Combine graph with metadata for persistence
            data = {
                **self.graphs[level],
                "_meta": {"versions": self._versions[level]}
            }
            
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Saved {level} graph to disk")
            return True
        except Exception as e:
            logger.error(f"Failed to save {level} graph: {e}")
            return False

    def _periodic_save(self):
        """Background thread to periodically save dirty graphs."""
        while self.running:
            time.sleep(self.save_interval)
            with self.lock:
                for level in ["user", "project"]:
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
        """Read both graphs (user and project). Never includes _meta."""
        with self.lock:
            return {
                "user": {
                    "nodes": self.graphs["user"]["nodes"].copy(),
                    "edges": self.graphs["user"]["edges"].copy()
                },
                "project": {
                    "nodes": self.graphs["project"]["nodes"].copy(),
                    "edges": self.graphs["project"]["edges"].copy()
                }
            }

    def sync(self, session_id: str, exclude_own: bool = True) -> dict:
        """
        Get changes since session start, optionally excluding own writes.
        Returns only the diff, not full graph.
        """
        with self.lock:
            if session_id not in self._sessions:
                return {"error": "Unknown session. Call register_session first."}
            
            start_ts = self._sessions[session_id]["start_ts"]
            result = {"user": {"nodes": [], "edges": []}, "project": {"nodes": [], "edges": []}}
            
            for level in ["user", "project"]:
                # Find changed nodes
                for node in self.graphs[level]["nodes"]:
                    key = self._version_key_node(node["id"])
                    ver = self._versions[level].get(key, {})
                    
                    if ver.get("ts", 0) > start_ts:
                        # Skip if it's our own write and exclude_own is True
                        if exclude_own and ver.get("session") == session_id:
                            continue
                        result[level]["nodes"].append(node)
                
                # Find changed edges
                for edge in self.graphs[level]["edges"]:
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
            node = {"id": node_id, "gist": gist}
            if touches:
                node["touches"] = touches
            if notes:
                node["notes"] = notes

            # Upsert (using index for O(1) lookup)
            nodes = self.graphs[level]["nodes"]
            existing_idx = self._node_index[level].get(node_id)

            if existing_idx is not None:
                nodes[existing_idx] = node
                action = "updated"
            else:
                new_idx = len(nodes)
                nodes.append(node)
                self._node_index[level][node_id] = new_idx
                action = "added"

            # Track version
            self._bump_version(level, self._version_key_node(node_id), session_id)
            self.dirty[level] = True
            
            logger.info(f"{action.capitalize()} node '{node_id}' in {level} graph")
            return {"action": action, "node": node}

    def put_edge(self, level: str, from_ref: str, to_ref: str, rel: str,
                 notes: Optional[list] = None, session_id: Optional[str] = None) -> dict:
        """Add or update an edge."""
        with self.lock:
            edge = {"from": from_ref, "to": to_ref, "rel": rel}
            if notes:
                edge["notes"] = notes

            # Upsert (using index for O(1) lookup)
            edges = self.graphs[level]["edges"]
            edge_key = (from_ref, to_ref, rel)
            existing_idx = self._edge_index[level].get(edge_key)

            if existing_idx is not None:
                edges[existing_idx] = edge
                action = "updated"
            else:
                new_idx = len(edges)
                edges.append(edge)
                self._edge_index[level][edge_key] = new_idx
                action = "added"

            # Track version
            self._bump_version(level, self._version_key_edge(from_ref, to_ref, rel), session_id)
            self.dirty[level] = True
            
            logger.info(f"{action.capitalize()} edge '{from_ref}' -> '{to_ref}' ({rel}) in {level} graph")
            return {"action": action, "edge": edge}

    def delete_node(self, level: str, node_id: str, session_id: Optional[str] = None) -> dict:
        """Delete a node."""
        with self.lock:
            idx = self._node_index[level].get(node_id)

            if idx is not None:
                # Remove the node
                del self.graphs[level]["nodes"][idx]

                # Rebuild node index for this level (indices shifted after deletion)
                self._node_index[level] = {
                    node["id"]: i
                    for i, node in enumerate(self.graphs[level]["nodes"])
                }

                # Mark as deleted by removing version
                key = self._version_key_node(node_id)
                if key in self._versions[level]:
                    del self._versions[level][key]

                self.dirty[level] = True
                logger.info(f"Deleted node '{node_id}' from {level} graph")
                return {"deleted": True, "node_id": node_id}
            return {"deleted": False, "node_id": node_id}

    def delete_edge(self, level: str, from_ref: str, to_ref: str, rel: str,
                    session_id: Optional[str] = None) -> dict:
        """Delete an edge."""
        with self.lock:
            edge_key = (from_ref, to_ref, rel)
            idx = self._edge_index[level].get(edge_key)

            if idx is not None:
                # Remove the edge
                del self.graphs[level]["edges"][idx]

                # Rebuild edge index for this level (indices shifted after deletion)
                self._edge_index[level] = {
                    (edge["from"], edge["to"], edge["rel"]): i
                    for i, edge in enumerate(self.graphs[level]["edges"])
                }

                # Mark as deleted by removing version
                key = self._version_key_edge(from_ref, to_ref, rel)
                if key in self._versions[level]:
                    del self._versions[level][key]

                self.dirty[level] = True
                logger.info(f"Deleted edge '{from_ref}' -> '{to_ref}' ({rel}) from {level} graph")
                return {"deleted": True, "edge": {"from": from_ref, "to": to_ref, "rel": rel}}
            return {"deleted": False, "edge": {"from": from_ref, "to": to_ref, "rel": rel}}

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
            description="Delete a node from the knowledge graph.",
            inputSchema={
                "type": "object",
                "properties": {
                    "level": {"type": "string", "enum": ["user", "project"]},
                    "id": {"type": "string", "description": "Node ID to delete"},
                    "session_id": {"type": "string", "description": "Optional: your session ID"}
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
                    "rel": {"type": "string"},
                    "session_id": {"type": "string", "description": "Optional: your session ID"}
                },
                "required": ["level", "from", "to", "rel"]
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
                arguments["id"],
                arguments.get("session_id")
            )
            return [TextContent(type="text", text=json.dumps(result))]

        elif name == "kg_delete_edge":
            result = store.delete_edge(
                arguments["level"],
                arguments["from"],
                arguments["to"],
                arguments["rel"],
                arguments.get("session_id")
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
