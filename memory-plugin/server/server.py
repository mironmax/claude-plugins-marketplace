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
from datetime import datetime

# Configure logging to stderr (never stdout for MCP)
logging.basicConfig(
    level=logging.INFO,
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

    def __init__(self, user_path: Path, project_path: Path, save_interval: int = 30):
        self.user_path = user_path
        self.project_path = project_path
        self.save_interval = save_interval

        # In-memory graphs (what LLM sees)
        self.graphs = {
            "user": {"nodes": [], "edges": []},
            "project": {"nodes": [], "edges": []}
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

    def read(self, level: Optional[str] = None) -> dict:
        """Read graph(s). If level is None, return both. Never includes _meta."""
        with self.lock:
            if level:
                return {
                    "nodes": self.graphs[level]["nodes"].copy(),
                    "edges": self.graphs[level]["edges"].copy()
                }
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

            # Upsert
            nodes = self.graphs[level]["nodes"]
            existing_idx = next((i for i, n in enumerate(nodes) if n["id"] == node_id), None)

            if existing_idx is not None:
                nodes[existing_idx] = node
                action = "updated"
            else:
                nodes.append(node)
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

            # Upsert
            edges = self.graphs[level]["edges"]
            existing_idx = next((i for i, e in enumerate(edges)
                               if e["from"] == from_ref and e["to"] == to_ref and e["rel"] == rel),
                              None)

            if existing_idx is not None:
                edges[existing_idx] = edge
                action = "updated"
            else:
                edges.append(edge)
                action = "added"

            # Track version
            self._bump_version(level, self._version_key_edge(from_ref, to_ref, rel), session_id)
            self.dirty[level] = True
            
            logger.info(f"{action.capitalize()} edge '{from_ref}' -> '{to_ref}' ({rel}) in {level} graph")
            return {"action": action, "edge": edge}

    def delete_node(self, level: str, node_id: str, session_id: Optional[str] = None) -> dict:
        """Delete a node."""
        with self.lock:
            nodes = self.graphs[level]["nodes"]
            original_count = len(nodes)
            self.graphs[level]["nodes"] = [n for n in nodes if n["id"] != node_id]

            if len(self.graphs[level]["nodes"]) < original_count:
                # Mark as deleted by removing version (or could track deletions separately)
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
            edges = self.graphs[level]["edges"]
            original_count = len(edges)
            self.graphs[level]["edges"] = [
                e for e in edges
                if not (e["from"] == from_ref and e["to"] == to_ref and e["rel"] == rel)
            ]

            if len(self.graphs[level]["edges"]) < original_count:
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
                "properties": {
                    "level": {
                        "type": "string",
                        "enum": ["user", "project"],
                        "description": "Optional: specific level to read. If omitted, returns both."
                    }
                }
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
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""
    global store

    try:
        if name == "kg_read":
            level = arguments.get("level")
            result = store.read(level)
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

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        logger.error(f"Tool call error: {e}", exc_info=True)
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def main():
    """Main entry point."""
    global store

    # Initialize store with paths from environment or defaults
    user_path = Path(os.getenv("KG_USER_PATH", Path.home() / ".claude/knowledge/user.json"))
    project_path = Path(os.getenv("KG_PROJECT_PATH", ".knowledge/graph.json"))
    save_interval = int(os.getenv("KG_SAVE_INTERVAL", "30"))

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
