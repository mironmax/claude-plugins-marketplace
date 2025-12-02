#!/usr/bin/env python3
"""
Knowledge Graph MCP Server
Maintains in-memory knowledge graph with periodic disk persistence.
Provides sub-millisecond read/write operations.
"""

import asyncio
import json
import sys
import logging
from pathlib import Path
from typing import Any, Optional
from collections import defaultdict
import threading
import time

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
    """Thread-safe in-memory knowledge graph with periodic persistence."""

    def __init__(self, user_path: Path, project_path: Path, save_interval: int = 30):
        self.user_path = user_path
        self.project_path = project_path
        self.save_interval = save_interval

        # In-memory graphs
        self.graphs = {
            "user": {"nodes": [], "edges": []},
            "project": {"nodes": [], "edges": []}
        }

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
                        self.graphs[level] = json.load(f)
                    logger.info(f"Loaded {level} graph: {len(self.graphs[level]['nodes'])} nodes, {len(self.graphs[level]['edges'])} edges")
                except Exception as e:
                    logger.error(f"Failed to load {level} graph: {e}")

    def _save_to_disk(self, level: str):
        """Save graph to disk."""
        path = self.user_path if level == "user" else self.project_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w') as f:
                json.dump(self.graphs[level], f, indent=2)
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

    def read(self, level: Optional[str] = None) -> dict:
        """Read graph(s). If level is None, return both."""
        with self.lock:
            if level:
                return self.graphs[level].copy()
            return {
                "user": self.graphs["user"].copy(),
                "project": self.graphs["project"].copy()
            }

    def put_node(self, level: str, node_id: str, gist: str,
                 touches: Optional[list] = None, notes: Optional[list] = None) -> dict:
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

            self.dirty[level] = True
            logger.info(f"{action.capitalize()} node '{node_id}' in {level} graph")
            return {"action": action, "node": node}

    def put_edge(self, level: str, from_ref: str, to_ref: str, rel: str,
                 notes: Optional[list] = None) -> dict:
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

            self.dirty[level] = True
            logger.info(f"{action.capitalize()} edge '{from_ref}' -> '{to_ref}' ({rel}) in {level} graph")
            return {"action": action, "edge": edge}

    def delete_node(self, level: str, node_id: str) -> dict:
        """Delete a node."""
        with self.lock:
            nodes = self.graphs[level]["nodes"]
            original_count = len(nodes)
            self.graphs[level]["nodes"] = [n for n in nodes if n["id"] != node_id]

            if len(self.graphs[level]["nodes"]) < original_count:
                self.dirty[level] = True
                logger.info(f"Deleted node '{node_id}' from {level} graph")
                return {"deleted": True, "node_id": node_id}
            return {"deleted": False, "node_id": node_id}

    def delete_edge(self, level: str, from_ref: str, to_ref: str, rel: str) -> dict:
        """Delete an edge."""
        with self.lock:
            edges = self.graphs[level]["edges"]
            original_count = len(edges)
            self.graphs[level]["edges"] = [
                e for e in edges
                if not (e["from"] == from_ref and e["to"] == to_ref and e["rel"] == rel)
            ]

            if len(self.graphs[level]["edges"]) < original_count:
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
            description="Read the knowledge graph. Returns both user and project graphs.",
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
            name="kg_put_node",
            description="Add or update a node in the knowledge graph.",
            inputSchema={
                "type": "object",
                "properties": {
                    "level": {"type": "string", "enum": ["user", "project"], "description": "Graph level"},
                    "id": {"type": "string", "description": "Node ID (kebab-case)"},
                    "gist": {"type": "string", "description": "The insight/concept"},
                    "touches": {"type": "array", "items": {"type": "string"}, "description": "Related artifacts"},
                    "notes": {"type": "array", "items": {"type": "string"}, "description": "Additional context"}
                },
                "required": ["level", "id", "gist"]
            }
        ),
        Tool(
            name="kg_put_edge",
            description="Add or update an edge in the knowledge graph.",
            inputSchema={
                "type": "object",
                "properties": {
                    "level": {"type": "string", "enum": ["user", "project"], "description": "Graph level"},
                    "from": {"type": "string", "description": "Source reference"},
                    "to": {"type": "string", "description": "Target reference"},
                    "rel": {"type": "string", "description": "Relationship (kebab-case)"},
                    "notes": {"type": "array", "items": {"type": "string"}, "description": "Additional context"}
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

        elif name == "kg_put_node":
            result = store.put_node(
                arguments["level"],
                arguments["id"],
                arguments["gist"],
                arguments.get("touches"),
                arguments.get("notes")
            )
            return [TextContent(type="text", text=json.dumps(result))]

        elif name == "kg_put_edge":
            result = store.put_edge(
                arguments["level"],
                arguments["from"],
                arguments["to"],
                arguments["rel"],
                arguments.get("notes")
            )
            return [TextContent(type="text", text=json.dumps(result))]

        elif name == "kg_delete_node":
            result = store.delete_node(arguments["level"], arguments["id"])
            return [TextContent(type="text", text=json.dumps(result))]

        elif name == "kg_delete_edge":
            result = store.delete_edge(
                arguments["level"],
                arguments["from"],
                arguments["to"],
                arguments["rel"]
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
    import os
    asyncio.run(main())
