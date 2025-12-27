"""Session management for HTTP MCP server with project path tracking."""

import logging
import time
import uuid
from pathlib import Path
from core.constants import SESSION_ID_LENGTH, SESSION_TTL_SECONDS
from core.exceptions import SessionNotFoundError

logger = logging.getLogger(__name__)


class HTTPSessionManager:
    """Manages sessions with project_path tracking for multi-project support."""

    def __init__(self, session_ttl: int = SESSION_TTL_SECONDS):
        self.session_ttl = session_ttl
        self._sessions: dict[str, dict] = {}

    def register(self, project_path: str | None = None) -> dict:
        """
        Register a new session with optional project path.
        Returns {"session_id": str, "start_ts": float}.
        """
        session_id = uuid.uuid4().hex[:SESSION_ID_LENGTH]
        ts = time.time()

        # Resolve project_path to absolute to prevent cwd-dependent behavior
        resolved_project_path = str(Path(project_path).resolve()) if project_path else None

        self._sessions[session_id] = {
            "start_ts": ts,
            "project_path": resolved_project_path,
            "last_activity": ts,
        }

        logger.info(f"Session registered: {session_id} (project: {resolved_project_path or 'none'})")
        return {"session_id": session_id, "start_ts": ts}

    def get_project_path(self, session_id: str) -> str | None:
        """Get project path for a session. Raises SessionNotFoundError if not found."""
        if session_id not in self._sessions:
            raise SessionNotFoundError(session_id)

        self._update_activity(session_id)
        return self._sessions[session_id]["project_path"]

    def get_start_ts(self, session_id: str) -> float:
        """Get session start timestamp. Raises SessionNotFoundError if not found."""
        if session_id not in self._sessions:
            raise SessionNotFoundError(session_id)

        return self._sessions[session_id]["start_ts"]

    def is_valid(self, session_id: str) -> bool:
        """Check if session exists and is not expired."""
        if session_id not in self._sessions:
            return False

        # Check expiration
        session = self._sessions[session_id]
        age = time.time() - session["last_activity"]
        return age <= self.session_ttl

    def _update_activity(self, session_id: str):
        """Update last activity timestamp for a session."""
        if session_id in self._sessions:
            self._sessions[session_id]["last_activity"] = time.time()

    def cleanup_expired(self) -> int:
        """Remove expired sessions. Returns count of removed sessions."""
        current_time = time.time()
        expired = [
            sid for sid, data in self._sessions.items()
            if current_time - data["last_activity"] > self.session_ttl
        ]

        for sid in expired:
            del self._sessions[sid]
            logger.info(f"Session expired: {sid}")

        return len(expired)

    def count(self) -> int:
        """Return number of active sessions."""
        return len(self._sessions)

    def get_all_project_paths(self) -> set[str]:
        """Get all unique project paths from active sessions."""
        return {
            data["project_path"]
            for data in self._sessions.values()
            if data["project_path"] is not None
        }
