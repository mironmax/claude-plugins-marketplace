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
import shutil
from pathlib import Path
from typing import Any
from dataclasses import dataclass
from typing import TypedDict, NotRequired

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


# ============================================================================
# Constants
# ============================================================================

# Token estimation
BASE_NODE_TOKENS = 20
CHARS_PER_TOKEN = 4
TOKENS_PER_EDGE = 15

# Compaction
COMPACTION_TARGET_RATIO = 0.9

# Session
SESSION_ID_LENGTH = 8
SESSION_TTL_SECONDS = 24 * 60 * 60  # 24 hours

# Grace periods
GRACE_PERIOD_DAYS = 7
ORPHAN_GRACE_DAYS = 7

# Backup retention
MAX_RECENT_BACKUPS = 3    # Keep 3 most recent (within hours)
MAX_DAILY_BACKUPS = 7     # Keep 7 daily backups (one per day)
MAX_WEEKLY_BACKUPS = 4    # Keep 4 weekly backups (one per week)
BACKUP_INTERVAL_SECONDS = 3600  # Minimum 1 hour between backups

# Graph levels
LEVELS = ("user", "project")


# ============================================================================
# Type Definitions
# ============================================================================

class Node(TypedDict):
    """Node in the knowledge graph."""
    id: str
    gist: str
    touches: NotRequired[list[str]]
    notes: NotRequired[list[str]]
    _archived: NotRequired[bool]
    _orphaned_ts: NotRequired[float]


class Edge(TypedDict):
    """Edge in the knowledge graph."""
    from_ref: str  # 'from' is reserved, but we use it in dict form
    to: str
    rel: str
    notes: NotRequired[list[str]]


class Graph(TypedDict):
    """Complete graph structure."""
    nodes: dict[str, Node]
    edges: dict[tuple[str, str, str], Edge]


# ============================================================================
# Custom Exceptions
# ============================================================================

class KGError(Exception):
    """Base exception for knowledge graph operations."""
    pass


class NodeNotFoundError(KGError):
    """Raised when a node is not found."""
    def __init__(self, level: str, node_id: str):
        self.level = level
        self.node_id = node_id
        super().__init__(f"Node '{node_id}' not found in {level} graph")


class SessionNotFoundError(KGError):
    """Raised when a session is not found."""
    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(f"Unknown session: {session_id}")


class NodeNotArchivedError(KGError):
    """Raised when trying to recall a non-archived node."""
    def __init__(self, level: str, node_id: str):
        self.level = level
        self.node_id = node_id
        super().__init__(f"Node '{node_id}' is not archived in {level} graph")


# ============================================================================
# Configuration
# ============================================================================

@dataclass(frozen=True)
class KGConfig:
    """Knowledge graph configuration."""
    max_tokens: int = 5000
    orphan_grace_days: int = ORPHAN_GRACE_DAYS
    grace_period_days: int = GRACE_PERIOD_DAYS
    save_interval: int = 30
    session_ttl: int = SESSION_TTL_SECONDS
    user_path: Path = Path.home() / ".claude/knowledge/user.json"
    project_path: Path = Path(".knowledge/graph.json")

    @classmethod
    def from_env(cls) -> "KGConfig":
        """Create configuration from environment variables."""
        return cls(
            max_tokens=int(os.getenv("KG_MAX_TOKENS", "5000")),
            orphan_grace_days=int(os.getenv("KG_ORPHAN_GRACE_DAYS", str(ORPHAN_GRACE_DAYS))),
            grace_period_days=int(os.getenv("KG_GRACE_PERIOD_DAYS", str(GRACE_PERIOD_DAYS))),
            save_interval=int(os.getenv("KG_SAVE_INTERVAL", "30")),
            session_ttl=int(os.getenv("KG_SESSION_TTL", str(SESSION_TTL_SECONDS))),
            user_path=Path(os.getenv("KG_USER_PATH", str(cls.user_path))),
            project_path=Path(os.getenv("KG_PROJECT_PATH", str(cls.project_path))),
        )


# ============================================================================
# Token Estimator
# ============================================================================

class TokenEstimator:
    """Estimates token costs for nodes and graphs."""

    @staticmethod
    def estimate_node(node: dict) -> int:
        """Estimate token cost for a single node."""
        gist_tokens = len(node.get("gist", "")) // CHARS_PER_TOKEN
        notes_tokens = sum(len(n) // CHARS_PER_TOKEN for n in node.get("notes", []))
        return BASE_NODE_TOKENS + gist_tokens + notes_tokens

    @staticmethod
    def estimate_graph(nodes: dict, edges: dict, include_archived: bool = False) -> int:
        """Estimate total token cost for a graph level."""
        if include_archived:
            node_tokens = sum(TokenEstimator.estimate_node(n) for n in nodes.values())
        else:
            node_tokens = sum(
                TokenEstimator.estimate_node(n)
                for n in nodes.values()
                if not n.get("_archived")
            )

        edge_tokens = len(edges) * TOKENS_PER_EDGE
        return node_tokens + edge_tokens


# ============================================================================
# Node Scorer
# ============================================================================

class NodeScorer:
    """Scores nodes for compaction decisions."""

    def __init__(self, grace_period_days: int):
        self.grace_period_seconds = grace_period_days * 24 * 60 * 60

    def score_all(self, nodes: dict, edges: dict, versions: dict) -> dict[str, float]:
        """
        Score all eligible nodes using percentile-based ranking.

        Returns dict of {node_id: score} for nodes past grace period.
        Higher score = more valuable = keep longer.
        """
        current_time = time.time()

        # Count edges per node
        edge_count = {}
        for edge in edges.values():
            edge_count[edge["from"]] = edge_count.get(edge["from"], 0) + 1
            edge_count[edge["to"]] = edge_count.get(edge["to"], 0) + 1

        # Collect eligible nodes (past grace period, not archived)
        eligible = []
        for node_id, node in nodes.items():
            if node.get("_archived"):
                continue

            version_key = f"node:{node_id}"
            version = versions.get(version_key, {})
            last_update = version.get("ts", current_time)
            age_seconds = current_time - last_update

            # Skip nodes within grace period
            if age_seconds < self.grace_period_seconds:
                continue

            eligible.append({
                "id": node_id,
                "recency_raw": -age_seconds,  # Negative so higher = fresher
                "connectedness_raw": edge_count.get(node_id, 0) + len(node.get("touches", [])),
                "richness_raw": len(node.get("gist", "")) + sum(len(n) for n in node.get("notes", []))
            })

        if not eligible:
            return {}

        # Percentile ranking
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
            scores[item["id"]] = (
                item["recency_pct"] *
                item["connectedness_pct"] *
                item["richness_pct"]
            )

        return scores


# ============================================================================
# Compactor
# ============================================================================

class Compactor:
    """Handles graph compaction (archiving low-value nodes)."""

    def __init__(self, scorer: NodeScorer, estimator: TokenEstimator, max_tokens: int):
        self.scorer = scorer
        self.estimator = estimator
        self.max_tokens = max_tokens

    def compact_if_needed(self, nodes: dict, edges: dict, versions: dict) -> list[str]:
        """
        Archive nodes if graph exceeds token limit.
        Returns list of archived node IDs.
        """
        estimated_tokens = self.estimator.estimate_graph(nodes, edges, include_archived=False)

        if estimated_tokens <= self.max_tokens:
            return []

        logger.info(f"Compacting graph: {estimated_tokens} tokens > {self.max_tokens} limit")

        # Score eligible nodes
        scores = self.scorer.score_all(nodes, edges, versions)

        if not scores:
            logger.debug("No nodes eligible for archiving (all within grace period)")
            return []

        # Sort by score (ascending - lowest scores archived first)
        sorted_nodes = sorted(scores.items(), key=lambda x: x[1])

        # Archive until we're under target
        target = int(self.max_tokens * COMPACTION_TARGET_RATIO)
        archived = []

        for node_id, score in sorted_nodes:
            if estimated_tokens <= target:
                break

            node = nodes.get(node_id)
            if node and not node.get("_archived"):
                # Calculate token cost
                token_cost = self.estimator.estimate_node(node)

                # Archive the node
                node["_archived"] = True

                # Update estimate
                estimated_tokens -= token_cost
                archived.append(node_id)

                logger.debug(f"Archived node '{node_id}' (score: {score:.2f}, tokens: {token_cost})")

        logger.info(f"Compaction complete: archived {len(archived)} nodes, now ~{estimated_tokens} tokens")
        return archived


# ============================================================================
# Session Manager
# ============================================================================

class SessionManager:
    """Manages session registration and lifecycle."""

    def __init__(self, session_ttl: int):
        self.session_ttl = session_ttl
        self._sessions: dict[str, dict] = {}

    def register(self, session_id: str) -> dict:
        """Register a new session."""
        ts = time.time()
        self._sessions[session_id] = {"start_ts": ts}
        logger.info(f"Session registered: {session_id}")
        return {"session_id": session_id, "start_ts": ts}

    def get_start_ts(self, session_id: str) -> float | None:
        """Get session start timestamp, or None if not found."""
        session = self._sessions.get(session_id)
        return session["start_ts"] if session else None

    def is_valid(self, session_id: str) -> bool:
        """Check if session exists."""
        return session_id in self._sessions

    def cleanup_expired(self) -> int:
        """Remove expired sessions. Returns count of removed sessions."""
        current_time = time.time()
        expired = [
            sid for sid, data in self._sessions.items()
            if current_time - data["start_ts"] > self.session_ttl
        ]
        for sid in expired:
            del self._sessions[sid]
            logger.info(f"Session expired: {sid}")
        return len(expired)

    def count(self) -> int:
        """Return number of active sessions."""
        return len(self._sessions)


# ============================================================================
# Graph Persistence with Atomic Writes and Tiered Backups
# ============================================================================

class GraphPersistence:
    """Handles graph persistence with atomic writes and tiered backup strategy."""

    def __init__(self, path: Path):
        self.path = path
        self.backup_marker = path.with_suffix(".last_backup")

    def load(self) -> tuple[dict, dict]:
        """
        Load graph and versions from disk.
        Returns (graph_data, versions_dict).
        """
        if not self.path.exists():
            return {"nodes": {}, "edges": {}}, {}

        try:
            with open(self.path) as f:
                data = json.load(f)

            # Extract versions
            versions = data.get("_meta", {}).get("versions", {})

            # Load nodes
            nodes = {k: v for k, v in data.get("nodes", {}).items() if k != "_meta"}

            # Load edges (convert string keys to tuple keys internally)
            edges_data = data.get("edges", {})
            edges = {}
            for key, edge in edges_data.items():
                tuple_key = (edge["from"], edge["to"], edge["rel"])
                edges[tuple_key] = edge

            graph = {"nodes": nodes, "edges": edges}

            logger.info(f"Loaded graph from {self.path}: {len(nodes)} nodes, {len(edges)} edges")
            return graph, versions

        except Exception as e:
            logger.error(f"Failed to load graph from {self.path}: {e}")
            return {"nodes": {}, "edges": {}}, {}

    def save(self, graph: dict, versions: dict) -> bool:
        """
        Save graph to disk with atomic write.
        Returns True on success, False on failure.
        """
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)

            # Convert edges from tuple keys to string keys for JSON
            edges_for_disk = {
                edge_storage_key(e["from"], e["to"], e["rel"]): e
                for e in graph["edges"].values()
            }

            data = {
                "nodes": graph["nodes"],
                "edges": edges_for_disk,
                "_meta": {"versions": versions}
            }

            # Atomic write: write to temp file, then rename
            temp_path = self.path.with_suffix(".tmp")

            with open(temp_path, 'w') as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())  # Ensure written to disk

            # Atomic rename (POSIX guarantees atomicity)
            temp_path.replace(self.path)

            logger.debug(f"Saved graph to {self.path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save graph to {self.path}: {e}")
            # Cleanup failed temp file
            temp_path = self.path.with_suffix(".tmp")
            if temp_path.exists():
                temp_path.unlink()
            return False

    def maybe_backup(self) -> bool:
        """
        Create tiered backups if enough time has passed.
        Returns True if backup was created.
        """
        if not self.path.exists():
            return False

        # Check if enough time has passed since last backup
        if self.backup_marker.exists():
            last_backup_time = self.backup_marker.stat().st_mtime
            if time.time() - last_backup_time < BACKUP_INTERVAL_SECONDS:
                return False

        # Perform backup rotation
        self._rotate_backups()

        # Update marker
        self.backup_marker.touch()
        return True

    def _rotate_backups(self):
        """
        Rotate backups into three tiers:
        - Recent: .bak.1, .bak.2, .bak.3 (most recent, hourly)
        - Daily: .bak.daily.1 through .bak.daily.7 (one per day)
        - Weekly: .bak.weekly.1 through .bak.weekly.4 (one per week)
        """
        if not self.path.exists():
            return

        current_time = time.time()

        # Promote oldest recent backup BEFORE rotation
        oldest_recent = self.path.with_suffix(f".json.bak.{MAX_RECENT_BACKUPS}")
        if oldest_recent.exists():
            self._promote_to_daily(oldest_recent, current_time)

        # Shift remaining: .bak.2 -> .bak.3, .bak.1 -> .bak.2
        for i in range(MAX_RECENT_BACKUPS - 1, 0, -1):
            old_backup = self.path.with_suffix(f".json.bak.{i}")
            new_backup = self.path.with_suffix(f".json.bak.{i + 1}")
            if old_backup.exists():
                shutil.copy2(old_backup, new_backup)

        # Create new .bak.1
        shutil.copy2(self.path, self.path.with_suffix(".json.bak.1"))
        logger.debug(f"Created recent backup: {self.path.with_suffix('.json.bak.1')}")

    def _promote_to_daily(self, source: Path, current_time: float):
        """Promote a recent backup to daily tier if a day has passed."""
        daily_1 = self.path.with_suffix(".json.bak.daily.1")

        if daily_1.exists():
            age_days = (current_time - daily_1.stat().st_mtime) / (24 * 60 * 60)
            if age_days < 1.0:
                return

        # Promote oldest daily BEFORE rotation
        oldest_daily = self.path.with_suffix(f".json.bak.daily.{MAX_DAILY_BACKUPS}")
        if oldest_daily.exists():
            self._promote_to_weekly(oldest_daily, current_time)

        # Shift remaining
        for i in range(MAX_DAILY_BACKUPS - 1, 0, -1):
            old_daily = self.path.with_suffix(f".json.bak.daily.{i}")
            new_daily = self.path.with_suffix(f".json.bak.daily.{i + 1}")
            if old_daily.exists():
                shutil.copy2(old_daily, new_daily)

        shutil.copy2(source, daily_1)
        logger.debug(f"Promoted to daily backup: {daily_1}")

    def _promote_to_weekly(self, source: Path, current_time: float):
        """Promote a daily backup to weekly tier if a week has passed."""
        weekly_1 = self.path.with_suffix(".json.bak.weekly.1")

        if weekly_1.exists():
            age_weeks = (current_time - weekly_1.stat().st_mtime) / (7 * 24 * 60 * 60)
            if age_weeks < 1.0:
                return

        # Shift (oldest drops off naturally)
        for i in range(MAX_WEEKLY_BACKUPS - 1, 0, -1):
            old_weekly = self.path.with_suffix(f".json.bak.weekly.{i}")
            new_weekly = self.path.with_suffix(f".json.bak.weekly.{i + 1}")
            if old_weekly.exists():
                shutil.copy2(old_weekly, new_weekly)

        shutil.copy2(source, weekly_1)
        logger.debug(f"Promoted to weekly backup: {weekly_1}")


# ============================================================================
# Module-Level Utilities
# ============================================================================

def is_archived(node: dict) -> bool:
    """Check if a node is archived."""
    return node.get("_archived", False)


def version_key_node(node_id: str) -> str:
    """Generate version key for a node."""
    return f"node:{node_id}"


def version_key_edge(from_ref: str, to_ref: str, rel: str) -> str:
    """Generate version key for an edge."""
    return f"edge:{from_ref}->{to_ref}:{rel}"


def edge_storage_key(from_ref: str, to_ref: str, rel: str) -> str:
    """Generate string key for edge storage."""
    return f"{from_ref}->{to_ref}:{rel}"


def validate_level(level: str):
    """Validate level parameter. Raises KGError if invalid."""
    if level not in LEVELS:
        raise KGError(f"Invalid level '{level}', must be one of {LEVELS}")


# ============================================================================
# Knowledge Graph Store
# ============================================================================


class KnowledgeGraphStore:
    """Thread-safe in-memory knowledge graph with periodic persistence."""

    def __init__(self, config: KGConfig):
        self.config = config

        # Initialize components
        self.estimator = TokenEstimator()
        self.scorer = NodeScorer(config.grace_period_days)
        self.compactor = Compactor(self.scorer, self.estimator, config.max_tokens)
        self.session_manager = SessionManager(config.session_ttl)

        self.persistence = {
            "user": GraphPersistence(config.user_path),
            "project": GraphPersistence(config.project_path)
        }

        # In-memory graphs
        self.graphs: dict[str, Graph] = {
            "user": {"nodes": {}, "edges": {}},
            "project": {"nodes": {}, "edges": {}}
        }

        # Version tracking (server-internal)
        self._versions: dict[str, dict] = {
            "user": {},
            "project": {}
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

        logger.info(f"Knowledge graph initialized")

    # ========================================================================
    # Version Management
    # ========================================================================

    def _bump_version(self, level: str, key: str, session_id: str | None = None) -> dict:
        """Increment version for a key and return new version."""
        ts = time.time()
        current = self._versions[level].get(key, {"v": 0})
        new_ver = {"v": current["v"] + 1, "ts": ts, "session": session_id}
        self._versions[level][key] = new_ver
        return new_ver

    # ========================================================================
    # Loading and Saving
    # ========================================================================

    def _load_all(self):
        """Load all graphs from disk."""
        for level in LEVELS:
            graph, versions = self.persistence[level].load()
            self.graphs[level] = graph
            self._versions[level] = versions

    def _save_to_disk(self, level: str) -> bool:
        """Save a graph level to disk."""
        success = self.persistence[level].save(self.graphs[level], self._versions[level])
        if success:
            # Maybe create backup
            self.persistence[level].maybe_backup()
        return success

    def _periodic_save(self):
        """Background thread for periodic saves and maintenance."""
        while self.running:
            time.sleep(self.config.save_interval)
            with self.lock:
                for level in LEVELS:
                    # Run maintenance
                    self._maybe_compact(level)
                    self._prune_orphans(level)

                    # Save if dirty
                    if self.dirty[level]:
                        if self._save_to_disk(level):
                            self.dirty[level] = False

                # Cleanup expired sessions
                self.session_manager.cleanup_expired()

    # ========================================================================
    # Compaction and Pruning
    # ========================================================================

    def _maybe_compact(self, level: str):
        """Compact graph if over token limit."""
        archived = self.compactor.compact_if_needed(
            self.graphs[level]["nodes"],
            self.graphs[level]["edges"],
            self._versions[level]
        )

        if archived:
            self.dirty[level] = True

    def _prune_orphans(self, level: str):
        """Prune orphaned archived nodes after grace period."""
        nodes = self.graphs[level]["nodes"]
        edges = self.graphs[level]["edges"]

        # Build set of active node IDs
        active_ids = {node_id for node_id, node in nodes.items() if not is_archived(node)}

        # Build set of reachable archived nodes (connected to active)
        reachable = set()
        for edge in edges.values():
            if edge["from"] in active_ids:
                reachable.add(edge["to"])
            if edge["to"] in active_ids:
                reachable.add(edge["from"])

        # Process archived nodes
        current_time = time.time()
        grace_seconds = self.config.orphan_grace_days * 24 * 60 * 60
        to_delete = []

        for node_id, node in nodes.items():
            if not is_archived(node):
                continue

            if node_id in reachable:
                # Reconnected - clear orphaned timestamp
                if "_orphaned_ts" in node:
                    del node["_orphaned_ts"]
                    self.dirty[level] = True
            else:
                # Orphaned
                if "_orphaned_ts" not in node:
                    # Newly orphaned
                    node["_orphaned_ts"] = current_time
                    self.dirty[level] = True
                    logger.debug(f"Node '{node_id}' orphaned, grace period started")
                else:
                    # Check if grace expired
                    orphaned_duration = current_time - node["_orphaned_ts"]
                    if orphaned_duration > grace_seconds:
                        to_delete.append(node_id)

        # Delete expired orphans
        for node_id in to_delete:
            self._delete_node_internal(level, node_id)
            logger.info(f"Deleted orphaned node '{node_id}' from {level} graph")

    def _delete_node_internal(self, level: str, node_id: str) -> bool:
        """Internal node deletion with edge cleanup. Caller must hold lock."""
        nodes = self.graphs[level]["nodes"]
        edges = self.graphs[level]["edges"]

        if node_id not in nodes:
            return False

        # Delete connected edges
        edges_to_delete = [
            key for key, edge in edges.items()
            if edge["from"] == node_id or edge["to"] == node_id
        ]

        for edge_key in edges_to_delete:
            edge = edges[edge_key]
            del edges[edge_key]

            # Remove version tracking
            version_key = version_key_edge(edge["from"], edge["to"], edge["rel"])
            if version_key in self._versions[level]:
                del self._versions[level][version_key]

        # Delete node
        del nodes[node_id]

        # Remove version tracking
        version_key = version_key_node(node_id)
        if version_key in self._versions[level]:
            del self._versions[level][version_key]

        self.dirty[level] = True
        return True

    # ========================================================================
    # Public API - Session Management
    # ========================================================================

    def register_session(self, session_id: str) -> dict:
        """Register a new session."""
        with self.lock:
            return self.session_manager.register(session_id)

    # ========================================================================
    # Public API - Read Operations
    # ========================================================================

    def read(self) -> dict:
        """
        Read both graphs. Returns only active nodes and their edges.
        Edges included if either endpoint is active (shows memory traces).
        """
        with self.lock:
            result = {}

            for level in LEVELS:
                nodes = self.graphs[level]["nodes"]
                edges = self.graphs[level]["edges"]

                # Filter active nodes
                active_nodes = {
                    node_id: node for node_id, node in nodes.items()
                    if not is_archived(node)
                }

                active_ids = set(active_nodes.keys())

                # Filter edges (include if either endpoint is active)
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
        Returns only active nodes/edges in diff.
        """
        with self.lock:
            if not self.session_manager.is_valid(session_id):
                raise SessionNotFoundError(session_id)

            start_ts = self.session_manager.get_start_ts(session_id)
            result = {"user": {"nodes": [], "edges": []}, "project": {"nodes": [], "edges": []}}

            for level in LEVELS:
                nodes = self.graphs[level]["nodes"]
                edges = self.graphs[level]["edges"]

                # Active node IDs for filtering
                active_ids = {node_id for node_id, node in nodes.items() if not is_archived(node)}

                # Find changed active nodes
                for node_id, node in nodes.items():
                    if is_archived(node):
                        continue

                    key = version_key_node(node_id)
                    ver = self._versions[level].get(key, {})

                    if ver.get("ts", 0) > start_ts:
                        if exclude_own and ver.get("session") == session_id:
                            continue
                        result[level]["nodes"].append(node)

                # Find changed edges (with active endpoints)
                for edge in edges.values():
                    if edge["from"] not in active_ids and edge["to"] not in active_ids:
                        continue

                    key = version_key_edge(edge["from"], edge["to"], edge["rel"])
                    ver = self._versions[level].get(key, {})

                    if ver.get("ts", 0) > start_ts:
                        if exclude_own and ver.get("session") == session_id:
                            continue
                        result[level]["edges"].append(edge)

            total_changes = sum(
                len(result[l]["nodes"]) + len(result[l]["edges"])
                for l in LEVELS
            )

            return {
                "since_ts": start_ts,
                "changes": result,
                "total_changes": total_changes
            }

    # ========================================================================
    # Public API - Write Operations
    # ========================================================================

    def put_node(self, level: str, node_id: str, gist: str,
                 touches: list | None = None, notes: list | None = None,
                 session_id: str | None = None) -> dict:
        """Add or update a node."""
        validate_level(level)
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
            self._bump_version(level, version_key_node(node_id), session_id)
            self.dirty[level] = True

            logger.debug(f"{action.capitalize()} node '{node_id}' in {level} graph")
            return {"action": action, "node": node}

    def put_edge(self, level: str, from_ref: str, to_ref: str, rel: str,
                 notes: list | None = None, session_id: str | None = None) -> dict:
        """Add or update an edge."""
        validate_level(level)
        with self.lock:
            edges = self.graphs[level]["edges"]

            edge = {"from": from_ref, "to": to_ref, "rel": rel}
            if notes:
                edge["notes"] = notes

            edge_key = (from_ref, to_ref, rel)
            action = "updated" if edge_key in edges else "added"
            edges[edge_key] = edge

            # Track version
            self._bump_version(level, version_key_edge(from_ref, to_ref, rel), session_id)
            self.dirty[level] = True

            logger.debug(f"{action.capitalize()} edge '{from_ref}' -> '{to_ref}' ({rel}) in {level} graph")
            return {"action": action, "edge": edge}

    def delete_node(self, level: str, node_id: str) -> dict:
        """Delete a node and its connected edges."""
        validate_level(level)
        with self.lock:
            if node_id not in self.graphs[level]["nodes"]:
                raise NodeNotFoundError(level, node_id)

            self._delete_node_internal(level, node_id)
            logger.debug(f"Deleted node '{node_id}' from {level} graph")
            return {"deleted": True, "node_id": node_id}

    def delete_edge(self, level: str, from_ref: str, to_ref: str, rel: str) -> dict:
        """Delete an edge."""
        validate_level(level)
        with self.lock:
            edges = self.graphs[level]["edges"]
            edge_key = (from_ref, to_ref, rel)

            if edge_key not in edges:
                return {"deleted": False, "edge": {"from": from_ref, "to": to_ref, "rel": rel}}

            del edges[edge_key]

            # Remove version tracking
            version_key = version_key_edge(from_ref, to_ref, rel)
            if version_key in self._versions[level]:
                del self._versions[level][version_key]

            self.dirty[level] = True
            logger.debug(f"Deleted edge '{from_ref}' -> '{to_ref}' ({rel}) from {level} graph")
            return {"deleted": True, "edge": {"from": from_ref, "to": to_ref, "rel": rel}}

    def recall(self, level: str, node_id: str, session_id: str | None = None) -> dict:
        """Retrieve an archived node back into active context."""
        validate_level(level)
        with self.lock:
            nodes = self.graphs[level]["nodes"]

            if node_id not in nodes:
                raise NodeNotFoundError(level, node_id)

            node = nodes[node_id]

            if not is_archived(node):
                raise NodeNotArchivedError(level, node_id)

            # Remove archived flag
            del node["_archived"]

            # Clear orphaned timestamp
            if "_orphaned_ts" in node:
                del node["_orphaned_ts"]

            # Bump version (refreshes recency for scoring)
            self._bump_version(level, version_key_node(node_id), session_id)

            self.dirty[level] = True

            logger.info(f"Recalled node '{node_id}' from {level} graph archive")
            return {"recalled": True, "node": node}

    # ========================================================================
    # Shutdown
    # ========================================================================

    def shutdown(self):
        """Graceful shutdown with final save."""
        logger.info("Shutting down knowledge graph store...")
        self.running = False
        with self.lock:
            for level in LEVELS:
                if self.dirty[level]:
                    self._save_to_disk(level)
        logger.info("Knowledge graph store shutdown complete")


# ============================================================================
# MCP Server
# ============================================================================

# Initialize server
app = Server("knowledge-graph")

# Global store instance
store: KnowledgeGraphStore | None = None


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
                    "id": {"type": "string", "description": "Node ID to recall"},
                    "session_id": {"type": "string", "description": "Optional: your session ID for tracking"}
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
    """Handle tool calls with uniform error handling."""
    global store

    try:
        if name == "kg_read":
            result = store.read()
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "kg_register_session":
            session_id = str(uuid.uuid4())[:SESSION_ID_LENGTH]
            result = store.register_session(session_id)
            return [TextContent(type="text", text=json.dumps(result))]

        elif name == "kg_sync":
            session_id = arguments.get("session_id")
            if not session_id:
                raise KGError("session_id required")
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
                arguments["id"],
                arguments.get("session_id")
            )
            return [TextContent(type="text", text=json.dumps(result))]

        elif name == "kg_ping":
            result = {
                "status": "ok",
                "active_sessions": store.session_manager.count(),
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

    except KGError as e:
        # Structured error response for known errors
        logger.warning(f"KG error in {name}: {e}")
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    except Exception as e:
        # Unexpected errors
        logger.error(f"Unexpected error in {name}: {e}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({"error": f"Internal error: {str(e)}"}))]


async def main():
    """Main entry point."""
    global store

    # Load configuration from environment
    config = KGConfig.from_env()

    # Initialize store
    store = KnowledgeGraphStore(config)

    logger.info("Starting Knowledge Graph MCP Server...")

    try:
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())
    finally:
        if store:
            store.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
