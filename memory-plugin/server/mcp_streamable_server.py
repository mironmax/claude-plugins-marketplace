#!/usr/bin/env python3
"""
MCP Streamable HTTP Server for Knowledge Graph
Uses Streamable HTTP transport (replaces deprecated SSE).
"""

import asyncio
import contextlib
import logging
import os
import sys
from pathlib import Path

from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse

# Add server directory to path
sys.path.insert(0, str(Path(__file__).parent))

from mcp_http.session_manager import HTTPSessionManager
from mcp_http.store import MultiProjectGraphStore, GraphConfig
from mcp_http.websocket import ConnectionManager
from core.exceptions import (
    KGError,
    NodeNotFoundError,
    SessionNotFoundError,
    NodeNotArchivedError,
)

# Configure logging
log_level = os.getenv("KG_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

# Global state
store: MultiProjectGraphStore | None = None
session_manager: HTTPSessionManager | None = None
connection_manager: ConnectionManager | None = None
mcp_server: Server | None = None


def create_mcp_server() -> Server:
    """Create and configure MCP server with all tools."""
    server = Server("knowledge-graph-mcp")

    # ========================================================================
    # Tool Definitions
    # ========================================================================

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List all available tools."""
        return [
            Tool(
                name="kg_read",
                description="Read the full knowledge graph (user + project levels)",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            ),
            Tool(
                name="kg_register_session",
                description="Register a session for sync tracking. Call once at session start.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {
                            "type": "string",
                            "description": "Optional path to project graph.json"
                        }
                    }
                }
            ),
            Tool(
                name="kg_put_node",
                description="Add or update a node in the knowledge graph",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "level": {
                            "type": "string",
                            "enum": ["user", "project"],
                            "description": "Graph level"
                        },
                        "id": {
                            "type": "string",
                            "description": "Node ID (kebab-case)"
                        },
                        "gist": {
                            "type": "string",
                            "description": "Node description"
                        },
                        "notes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Additional context"
                        },
                        "touches": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Related artifacts"
                        },
                        "session_id": {
                            "type": "string",
                            "description": "Session ID (from kg_register_session)"
                        }
                    },
                    "required": ["level", "id", "gist"]
                }
            ),
            Tool(
                name="kg_put_edge",
                description="Add or update an edge in the knowledge graph",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "level": {
                            "type": "string",
                            "enum": ["user", "project"],
                            "description": "Graph level"
                        },
                        "from": {
                            "type": "string",
                            "description": "Source node ID"
                        },
                        "to": {
                            "type": "string",
                            "description": "Target node ID"
                        },
                        "rel": {
                            "type": "string",
                            "description": "Relationship (kebab-case)"
                        },
                        "notes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Additional context"
                        },
                        "session_id": {
                            "type": "string",
                            "description": "Session ID"
                        }
                    },
                    "required": ["level", "from", "to", "rel"]
                }
            ),
            Tool(
                name="kg_delete_node",
                description="Delete a node and its connected edges",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "level": {
                            "type": "string",
                            "enum": ["user", "project"]
                        },
                        "id": {
                            "type": "string",
                            "description": "Node ID to delete"
                        },
                        "session_id": {
                            "type": "string"
                        }
                    },
                    "required": ["level", "id"]
                }
            ),
            Tool(
                name="kg_delete_edge",
                description="Delete an edge from the knowledge graph",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "level": {
                            "type": "string",
                            "enum": ["user", "project"]
                        },
                        "from": {
                            "type": "string"
                        },
                        "to": {
                            "type": "string"
                        },
                        "rel": {
                            "type": "string"
                        },
                        "session_id": {
                            "type": "string"
                        }
                    },
                    "required": ["level", "from", "to", "rel"]
                }
            ),
            Tool(
                name="kg_recall",
                description="Retrieve an archived node back into active context",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "level": {
                            "type": "string",
                            "enum": ["user", "project"]
                        },
                        "id": {
                            "type": "string",
                            "description": "Node ID to recall"
                        },
                        "session_id": {
                            "type": "string"
                        }
                    },
                    "required": ["level", "id"]
                }
            ),
            Tool(
                name="kg_sync",
                description="Get changes since session start from other sessions",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Your session ID"
                        }
                    },
                    "required": ["session_id"]
                }
            ),
            Tool(
                name="kg_ping",
                description="Health check for MCP connectivity",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
        ]

    # ========================================================================
    # Tool Handlers
    # ========================================================================

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        """Handle tool calls."""
        global store, session_manager

        try:
            if name == "kg_ping":
                return [TextContent(
                    type="text",
                    text=f"OK - Server version 0.5.0, {session_manager.count() if session_manager else 0} active sessions"
                )]

            elif name == "kg_register_session":
                project_path = arguments.get("project_path")
                result = session_manager.register(project_path)
                return [TextContent(
                    type="text",
                    text=f"Session registered: {result['session_id']}\nStart time: {result['start_ts']}"
                )]

            elif name == "kg_read":
                session_id = arguments.get("session_id")
                graphs = store.read_graphs(session_id)

                # Format output
                user_nodes = len(graphs["user"]["nodes"])
                user_edges = len(graphs["user"]["edges"])
                proj_nodes = len(graphs["project"]["nodes"])
                proj_edges = len(graphs["project"]["edges"])

                import json
                return [TextContent(
                    type="text",
                    text=f"Knowledge Graph:\n\nUser level: {user_nodes} nodes, {user_edges} edges\nProject level: {proj_nodes} nodes, {proj_edges} edges\n\n{json.dumps(graphs, indent=2)}"
                )]

            elif name == "kg_put_node":
                result = store.put_node(
                    level=arguments["level"],
                    node_id=arguments["id"],
                    gist=arguments["gist"],
                    notes=arguments.get("notes"),
                    touches=arguments.get("touches"),
                    session_id=arguments.get("session_id")
                )
                return [TextContent(
                    type="text",
                    text=f"Node '{arguments['id']}' saved to {arguments['level']} graph"
                )]

            elif name == "kg_put_edge":
                result = store.put_edge(
                    level=arguments["level"],
                    from_ref=arguments["from"],
                    to_ref=arguments["to"],
                    rel=arguments["rel"],
                    notes=arguments.get("notes"),
                    session_id=arguments.get("session_id")
                )
                return [TextContent(
                    type="text",
                    text=f"Edge {arguments['from']}->{arguments['to']}:{arguments['rel']} saved to {arguments['level']} graph"
                )]

            elif name == "kg_delete_node":
                result = store.delete_node(
                    level=arguments["level"],
                    node_id=arguments["id"],
                    session_id=arguments.get("session_id")
                )
                return [TextContent(
                    type="text",
                    text=f"Deleted node '{arguments['id']}' and {result['edges_deleted']} connected edges from {arguments['level']} graph"
                )]

            elif name == "kg_delete_edge":
                result = store.delete_edge(
                    level=arguments["level"],
                    from_ref=arguments["from"],
                    to_ref=arguments["to"],
                    rel=arguments["rel"],
                    session_id=arguments.get("session_id")
                )
                status = "deleted" if result["deleted"] else "not found"
                return [TextContent(
                    type="text",
                    text=f"Edge {status}: {arguments['from']}->{arguments['to']}:{arguments['rel']}"
                )]

            elif name == "kg_recall":
                result = store.recall_node(
                    level=arguments["level"],
                    node_id=arguments["id"],
                    session_id=arguments.get("session_id")
                )
                return [TextContent(
                    type="text",
                    text=f"Recalled node '{arguments['id']}' from {arguments['level']} graph archive"
                )]

            elif name == "kg_sync":
                session_id = arguments["session_id"]
                start_ts = session_manager.get_start_ts(session_id)
                updates = store.get_sync_diff(session_id, start_ts)

                user_updates = len(updates["user"]["nodes"]) + len(updates["user"]["edges"])
                proj_updates = len(updates["project"]["nodes"]) + len(updates["project"]["edges"])

                if user_updates == 0 and proj_updates == 0:
                    return [TextContent(type="text", text="No updates from other sessions")]

                import json
                return [TextContent(
                    type="text",
                    text=f"Updates from other sessions:\n\nUser: {user_updates} changes\nProject: {proj_updates} changes\n\n{json.dumps(updates, indent=2)}"
                )]

            else:
                raise ValueError(f"Unknown tool: {name}")

        except NodeNotFoundError as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]
        except SessionNotFoundError as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]
        except NodeNotArchivedError as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]
        except KGError as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]
        except Exception as e:
            logger.error(f"Tool error: {e}", exc_info=True)
            return [TextContent(type="text", text=f"Internal error: {str(e)}")]

    return server


async def main():
    """Main entry point."""
    global store, session_manager, connection_manager, mcp_server

    # Load configuration
    config = GraphConfig(
        max_tokens=int(os.getenv("KG_MAX_TOKENS", "5000")),
        orphan_grace_days=int(os.getenv("KG_ORPHAN_GRACE_DAYS", "7")),
        grace_period_days=int(os.getenv("KG_GRACE_PERIOD_DAYS", "7")),
        save_interval=int(os.getenv("KG_SAVE_INTERVAL", "30")),
        user_path=Path(os.getenv("KG_USER_PATH", str(Path.home() / ".claude/knowledge/user.json"))),
    )

    session_manager = HTTPSessionManager()
    connection_manager = ConnectionManager()

    # Broadcast callback for WebSocket
    async def broadcast_callback(project_path: str | None, message: dict, exclude_session: str | None):
        await connection_manager.broadcast_to_project(
            project_path, message, exclude_session, session_manager
        )

    store = MultiProjectGraphStore(config, session_manager, broadcast_callback)
    mcp_server = create_mcp_server()

    # Create Streamable HTTP session manager
    mcp_session_manager = StreamableHTTPSessionManager(
        app=mcp_server,
        event_store=None,  # No resumability for now
        json_response=False,  # Use SSE responses (streaming)
        stateless=False,  # Maintain session state
    )

    # Health check endpoint
    async def health_check(request):
        return JSONResponse({
            "status": "ok",
            "version": "0.5.0",
            "transport": "streamable-http",
            "active_sessions": session_manager.count(),
            "loaded_graphs": len(store.graphs)
        })

    # Create Starlette app with custom ASGI routing
    async def app_asgi(scope, receive, send):
        """ASGI app that routes between MCP and health endpoints."""
        path = scope.get("path", "")

        if path == "/health":
            # Handle health check
            response = JSONResponse({
                "status": "ok",
                "version": "0.5.0",
                "transport": "streamable-http",
                "active_sessions": session_manager.count(),
                "loaded_graphs": len(store.graphs)
            })
            await response(scope, receive, send)
        elif path == "/":
            # Handle MCP requests
            await mcp_session_manager.handle_request(scope, receive, send)
        else:
            # 404 for other paths
            from starlette.responses import PlainTextResponse
            response = PlainTextResponse("Not Found", status_code=404)
            await response(scope, receive, send)

    routes = []  # No routes needed, using raw ASGI

    @contextlib.asynccontextmanager
    async def lifespan(scope):
        """Manage application lifespan."""
        logger.info("Starting MCP Streamable HTTP Server...")

        # Start MCP session manager
        async with mcp_session_manager.run():
            logger.info("MCP session manager running")
            yield

        # Shutdown
        if store:
            store.shutdown()
        logger.info("Server stopped")

    # Wrap ASGI app with lifespan
    class AppWithLifespan:
        async def __call__(self, scope, receive, send):
            if scope["type"] == "lifespan":
                async with lifespan(scope):
                    while True:
                        message = await receive()
                        if message["type"] == "lifespan.startup":
                            await send({"type": "lifespan.startup.complete"})
                        elif message["type"] == "lifespan.shutdown":
                            await send({"type": "lifespan.shutdown.complete"})
                            return
            else:
                await app_asgi(scope, receive, send)

    app = AppWithLifespan()

    port = int(os.getenv("KG_HTTP_PORT", "8765"))
    host = os.getenv("KG_HTTP_HOST", "127.0.0.1")

    logger.info(f"MCP Streamable HTTP endpoint: http://{host}:{port}/")
    logger.info(f"Health check: http://{host}:{port}/health")

    import uvicorn

    # Run uvicorn server
    config_uvi = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level=log_level.lower()
    )
    server_uvi = uvicorn.Server(config_uvi)
    await server_uvi.serve()


if __name__ == "__main__":
    asyncio.run(main())
