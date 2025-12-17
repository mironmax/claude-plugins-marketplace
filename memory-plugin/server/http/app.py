"""FastAPI HTTP server for shared MCP knowledge graph."""

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from http.session_manager import HTTPSessionManager
from http.store import MultiProjectGraphStore, GraphConfig
from http.websocket import ConnectionManager
from core.exceptions import KGError, NodeNotFoundError, SessionNotFoundError, NodeNotArchivedError

# Configure logging
log_level = os.getenv("KG_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)


# ============================================================================
# Request/Response Models
# ============================================================================

class SessionRegisterRequest(BaseModel):
    """Request to register a new session."""
    project_path: str | None = Field(None, description="Path to project graph.json file")


class SessionRegisterResponse(BaseModel):
    """Response from session registration."""
    session_id: str
    start_ts: float


class NodeRequest(BaseModel):
    """Request to create/update a node."""
    level: str = Field(..., description="Graph level: 'user' or 'project'")
    id: str = Field(..., description="Node ID (kebab-case)")
    gist: str = Field(..., description="Node description")
    notes: list[str] | None = Field(None, description="Additional notes")
    touches: list[str] | None = Field(None, description="Related file paths")
    session_id: str | None = Field(None, description="Session ID (required for project level)")


class EdgeRequest(BaseModel):
    """Request to create/update an edge."""
    level: str = Field(..., description="Graph level: 'user' or 'project'")
    from_: str = Field(..., alias="from", description="Source node ID")
    to: str = Field(..., description="Target node ID")
    rel: str = Field(..., description="Relationship type (kebab-case)")
    notes: list[str] | None = Field(None, description="Additional notes")
    session_id: str | None = Field(None, description="Session ID (required for project level)")


class RecallRequest(BaseModel):
    """Request to recall an archived node."""
    level: str = Field(..., description="Graph level: 'user' or 'project'")
    id: str = Field(..., description="Node ID to recall")
    session_id: str | None = Field(None, description="Session ID (required for project level)")


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    active_sessions: int
    loaded_graphs: int


# ============================================================================
# Global State
# ============================================================================

store: MultiProjectGraphStore | None = None
session_manager: HTTPSessionManager | None = None
connection_manager: ConnectionManager | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global store, session_manager, connection_manager

    # Startup
    logger.info("Starting Knowledge Graph HTTP Server...")

    config = GraphConfig(
        max_tokens=int(os.getenv("KG_MAX_TOKENS", "5000")),
        orphan_grace_days=int(os.getenv("KG_ORPHAN_GRACE_DAYS", "7")),
        grace_period_days=int(os.getenv("KG_GRACE_PERIOD_DAYS", "7")),
        save_interval=int(os.getenv("KG_SAVE_INTERVAL", "30")),
        user_path=Path(os.getenv("KG_USER_PATH", str(Path.home() / ".claude/knowledge/user.json"))),
    )

    session_manager = HTTPSessionManager()
    connection_manager = ConnectionManager()

    # Create broadcast callback
    async def broadcast_callback(project_path: str | None, message: dict, exclude_session: str | None):
        """Broadcast changes to connected WebSocket clients."""
        await connection_manager.broadcast_to_project(
            project_path,
            message,
            exclude_session,
            session_manager
        )

    store = MultiProjectGraphStore(config, session_manager, broadcast_callback)

    logger.info("Server ready")

    yield

    # Shutdown
    if store:
        store.shutdown()

    logger.info("Server stopped")


# Create FastAPI app
app = FastAPI(
    title="Knowledge Graph MCP Server",
    description="Shared HTTP server for knowledge graph operations",
    version="0.5.0",
    lifespan=lifespan
)


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "version": "0.5.0",
        "active_sessions": session_manager.count() if session_manager else 0,
        "loaded_graphs": len(store.graphs) if store else 0,
    }


@app.post("/api/sessions/register", response_model=SessionRegisterResponse)
async def register_session(request: SessionRegisterRequest):
    """
    Register a new session with optional project path.
    Returns session_id and start_ts.
    """
    if not session_manager:
        raise HTTPException(status_code=500, detail="Session manager not initialized")

    result = session_manager.register(request.project_path)
    return result


@app.get("/api/graph/read")
async def read_graphs(session_id: str | None = None):
    """
    Read all accessible graphs for a session.
    Returns dict with "user" and "project" graphs.
    """
    if not store:
        raise HTTPException(status_code=500, detail="Store not initialized")

    try:
        return store.read_graphs(session_id)
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error reading graphs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/graph/nodes")
async def put_node(request: NodeRequest):
    """Create or update a node."""
    if not store:
        raise HTTPException(status_code=500, detail="Store not initialized")

    try:
        result = store.put_node(
            level=request.level,
            node_id=request.id,
            gist=request.gist,
            notes=request.notes,
            touches=request.touches,
            session_id=request.session_id,
        )
        return result
    except (SessionNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KGError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error putting node: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/graph/nodes/{node_id}")
async def delete_node(node_id: str, level: str, session_id: str | None = None):
    """Delete a node and its connected edges."""
    if not store:
        raise HTTPException(status_code=500, detail="Store not initialized")

    try:
        result = store.delete_node(level=level, node_id=node_id, session_id=session_id)
        return result
    except NodeNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (SessionNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KGError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting node: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/graph/edges")
async def put_edge(request: EdgeRequest):
    """Create or update an edge."""
    if not store:
        raise HTTPException(status_code=500, detail="Store not initialized")

    try:
        result = store.put_edge(
            level=request.level,
            from_ref=request.from_,
            to_ref=request.to,
            rel=request.rel,
            notes=request.notes,
            session_id=request.session_id,
        )
        return result
    except (SessionNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KGError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error putting edge: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/graph/edges")
async def delete_edge(
    level: str,
    from_: str = Field(..., alias="from"),
    to: str = ...,
    rel: str = ...,
    session_id: str | None = None
):
    """Delete an edge."""
    if not store:
        raise HTTPException(status_code=500, detail="Store not initialized")

    try:
        result = store.delete_edge(
            level=level,
            from_ref=from_,
            to_ref=to,
            rel=rel,
            session_id=session_id,
        )
        return result
    except (SessionNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KGError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting edge: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/graph/recall")
async def recall_node(request: RecallRequest):
    """Recall (unarchive) an archived node."""
    if not store:
        raise HTTPException(status_code=500, detail="Store not initialized")

    try:
        result = store.recall_node(
            level=request.level,
            node_id=request.id,
            session_id=request.session_id,
        )
        return result
    except NodeNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except NodeNotArchivedError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (SessionNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KGError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error recalling node: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/graph/sync")
async def sync_graph(session_id: str, start_ts: float):
    """
    Get changes since a timestamp for a session.
    Returns updates from other sessions.
    """
    if not store:
        raise HTTPException(status_code=500, detail="Store not initialized")

    try:
        result = store.get_sync_diff(session_id, start_ts)
        return result
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error syncing graph: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time graph updates.
    Clients connect with: ws://localhost:8765/ws?session_id=xxx
    """
    if not connection_manager or not session_manager:
        await websocket.close(code=1011, reason="Server not initialized")
        return

    # Verify session exists
    if not session_manager.is_valid(session_id):
        await websocket.close(code=1008, reason="Invalid session_id")
        return

    await connection_manager.connect(websocket, session_id)

    try:
        # Keep connection alive and receive messages (for heartbeat/ping)
        while True:
            data = await websocket.receive_text()
            # Echo back for heartbeat
            await websocket.send_json({"type": "pong", "message": data})

    except WebSocketDisconnect:
        connection_manager.disconnect(session_id)
        logger.info(f"WebSocket disconnected: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error for {session_id}: {e}")
        connection_manager.disconnect(session_id)


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("KG_HTTP_PORT", "8765"))
    host = os.getenv("KG_HTTP_HOST", "127.0.0.1")

    logger.info(f"Starting server on {host}:{port}")

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level.lower(),
    )
