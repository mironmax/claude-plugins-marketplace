"""WebSocket connection manager for real-time graph updates."""

import logging
from typing import Any
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections and broadcasts."""

    def __init__(self):
        # Map: session_id -> WebSocket
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        """Accept and register a WebSocket connection."""
        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info(f"WebSocket connected: {session_id}")

    def disconnect(self, session_id: str):
        """Remove a WebSocket connection."""
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            logger.info(f"WebSocket disconnected: {session_id}")

    async def send_personal(self, session_id: str, message: dict):
        """Send message to a specific session."""
        if session_id in self.active_connections:
            try:
                await self.active_connections[session_id].send_json(message)
            except Exception as e:
                logger.error(f"Error sending to {session_id}: {e}")
                self.disconnect(session_id)

    async def broadcast_to_project(
        self,
        project_path: str | None,
        message: dict,
        exclude_session: str | None = None,
        session_manager=None
    ):
        """
        Broadcast message to all sessions watching a project.

        Args:
            project_path: Project path to broadcast to (None = user graph only)
            message: Message to send
            exclude_session: Session ID to exclude from broadcast (typically the source)
            session_manager: Session manager to get project paths
        """
        if not session_manager:
            return

        # Determine which sessions to notify
        target_sessions = []

        for session_id in list(self.active_connections.keys()):
            # Skip excluded session
            if session_id == exclude_session:
                continue

            # For user-level changes, broadcast to everyone
            if message.get("level") == "user":
                target_sessions.append(session_id)
                continue

            # For project-level changes, only broadcast to sessions watching this project
            if project_path:
                try:
                    session_project = session_manager.get_project_path(session_id)
                    if session_project == project_path:
                        target_sessions.append(session_id)
                except Exception:
                    # Session might be invalid
                    pass

        # Send to all target sessions
        for session_id in target_sessions:
            await self.send_personal(session_id, message)

        if target_sessions:
            logger.debug(f"Broadcast to {len(target_sessions)} sessions: {message.get('type')}")

    async def broadcast_all(self, message: dict):
        """Broadcast message to all connected sessions."""
        disconnected = []

        for session_id, connection in self.active_connections.items():
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to {session_id}: {e}")
                disconnected.append(session_id)

        # Clean up disconnected sessions
        for session_id in disconnected:
            self.disconnect(session_id)

    def count(self) -> int:
        """Return number of active connections."""
        return len(self.active_connections)
