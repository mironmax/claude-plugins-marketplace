"""Multi-project knowledge graph store for HTTP MCP server."""

import logging
import threading
import time
from pathlib import Path
from typing import Any
from dataclasses import dataclass

from ..core import (
    TokenEstimator,
    NodeScorer,
    Compactor,
    GraphPersistence,
    Graph,
    GRACE_PERIOD_DAYS,
    ORPHAN_GRACE_DAYS,
    is_archived,
    version_key_node,
    version_key_edge,
    NodeNotFoundError,
    NodeNotArchivedError,
    validate_level,
)
from .session_manager import HTTPSessionManager

logger = logging.getLogger(__name__)


@dataclass
class GraphConfig:
    """Configuration for knowledge graph."""
    max_tokens: int = 5000
    orphan_grace_days: int = ORPHAN_GRACE_DAYS
    grace_period_days: int = GRACE_PERIOD_DAYS
    save_interval: int = 30
    user_path: Path = Path.home() / ".claude/knowledge/user.json"


class MultiProjectGraphStore:
    """
    Multi-project knowledge graph store.

    Structure:
    - graphs["user"] = shared user graph
    - graphs["project:/path/to/graph.json"] = project-specific graphs
    """

    def __init__(self, config: GraphConfig, session_manager: HTTPSessionManager):
        self.config = config
        self.session_manager = session_manager

        # Initialize components
        self.estimator = TokenEstimator()
        self.scorer = NodeScorer(config.grace_period_days)
        self.compactor = Compactor(self.scorer, self.estimator, config.max_tokens)

        # Graph storage: key = "user" or "project:/path/to/graph.json"
        self.graphs: dict[str, Graph] = {}
        self._versions: dict[str, dict] = {}
        self._persistence: dict[str, GraphPersistence] = {}

        # Thread safety
        self.lock = threading.RLock()
        self.dirty: dict[str, bool] = {}

        # Background saver
        self.running = True
        self.saver_thread = threading.Thread(target=self._periodic_save, daemon=True)

        # Load user graph
        self._load_user_graph()
        self.saver_thread.start()

        logger.info("Multi-project graph store initialized")

    def _load_user_graph(self):
        """Load the shared user graph."""
        with self.lock:
            user_key = "user"
            persistence = GraphPersistence(self.config.user_path)
            graph, versions = persistence.load()

            self.graphs[user_key] = graph
            self._versions[user_key] = versions
            self._persistence[user_key] = persistence
            self.dirty[user_key] = False

            logger.info(f"Loaded user graph: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")

    def _ensure_project_loaded(self, project_path: str):
        """Load a project graph if not already loaded. Caller must hold lock."""
        project_key = f"project:{project_path}"

        if project_key in self.graphs:
            return

        # Load from disk
        persistence = GraphPersistence(Path(project_path))
        graph, versions = persistence.load()

        self.graphs[project_key] = graph
        self._versions[project_key] = versions
        self._persistence[project_key] = persistence
        self.dirty[project_key] = False

        logger.info(f"Loaded project graph from {project_path}: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")

    def _get_graph_key(self, level: str, session_id: str | None) -> str:
        """Get the graph storage key for a level and session."""
        validate_level(level)

        if level == "user":
            return "user"
        else:  # level == "project"
            if not session_id:
                raise ValueError("session_id required for project-level operations")

            project_path = self.session_manager.get_project_path(session_id)
            if not project_path:
                raise ValueError(f"Session {session_id} has no project_path registered")

            return f"project:{project_path}"

    def _bump_version(self, graph_key: str, key: str, session_id: str | None = None) -> dict:
        """Increment version for a key and return new version. Caller must hold lock."""
        ts = time.time()
        current = self._versions[graph_key].get(key, {"v": 0})
        new_ver = {"v": current["v"] + 1, "ts": ts, "session": session_id}
        self._versions[graph_key][key] = new_ver
        return new_ver

    # ========================================================================
    # Public API
    # ========================================================================

    def read_graphs(self, session_id: str | None = None) -> dict:
        """
        Read all accessible graphs for a session.
        Returns dict with "user" and "project" keys.
        """
        with self.lock:
            result = {
                "user": {
                    "nodes": list(self.graphs["user"]["nodes"].values()),
                    "edges": list(self.graphs["user"]["edges"].values()),
                },
                "project": {"nodes": [], "edges": []}
            }

            # Add project graph if session has one
            if session_id:
                try:
                    project_path = self.session_manager.get_project_path(session_id)
                    if project_path:
                        project_key = f"project:{project_path}"
                        self._ensure_project_loaded(project_path)

                        result["project"] = {
                            "nodes": list(self.graphs[project_key]["nodes"].values()),
                            "edges": list(self.graphs[project_key]["edges"].values()),
                        }
                except Exception as e:
                    logger.warning(f"Could not load project graph for session {session_id}: {e}")

            return result

    def put_node(
        self,
        level: str,
        node_id: str,
        gist: str,
        notes: list[str] | None = None,
        touches: list[str] | None = None,
        session_id: str | None = None,
    ) -> dict:
        """Create or update a node."""
        with self.lock:
            graph_key = self._get_graph_key(level, session_id)

            # Ensure project graph is loaded
            if graph_key.startswith("project:"):
                project_path = graph_key.split(":", 1)[1]
                self._ensure_project_loaded(project_path)

            nodes = self.graphs[graph_key]["nodes"]

            # Create or update node
            node = nodes.get(node_id, {"id": node_id})
            node["gist"] = gist
            if notes is not None:
                node["notes"] = notes
            if touches is not None:
                node["touches"] = touches

            # If updating archived node, unarchive it
            if "_archived" in node:
                del node["_archived"]
            if "_orphaned_ts" in node:
                del node["_orphaned_ts"]

            nodes[node_id] = node

            # Update version
            ver_key = version_key_node(node_id)
            self._bump_version(graph_key, ver_key, session_id)

            self.dirty[graph_key] = True

            # Run compaction if needed
            self._maybe_compact(graph_key)

            logger.debug(f"Put node '{node_id}' in {level} graph")
            return {"node": node, "level": level}

    def put_edge(
        self,
        level: str,
        from_ref: str,
        to_ref: str,
        rel: str,
        notes: list[str] | None = None,
        session_id: str | None = None,
    ) -> dict:
        """Create or update an edge."""
        with self.lock:
            graph_key = self._get_graph_key(level, session_id)

            # Ensure project graph is loaded
            if graph_key.startswith("project:"):
                project_path = graph_key.split(":", 1)[1]
                self._ensure_project_loaded(project_path)

            edges = self.graphs[graph_key]["edges"]
            edge_key = (from_ref, to_ref, rel)

            # Create or update edge
            edge = edges.get(edge_key, {"from": from_ref, "to": to_ref, "rel": rel})
            if notes is not None:
                edge["notes"] = notes

            edges[edge_key] = edge

            # Update version
            ver_key = version_key_edge(from_ref, to_ref, rel)
            self._bump_version(graph_key, ver_key, session_id)

            self.dirty[graph_key] = True

            logger.debug(f"Put edge {from_ref}->{to_ref}:{rel} in {level} graph")
            return {"edge": edge, "level": level}

    def delete_node(self, level: str, node_id: str, session_id: str | None = None) -> dict:
        """Delete a node and its connected edges."""
        with self.lock:
            graph_key = self._get_graph_key(level, session_id)

            # Ensure project graph is loaded
            if graph_key.startswith("project:"):
                project_path = graph_key.split(":", 1)[1]
                self._ensure_project_loaded(project_path)

            nodes = self.graphs[graph_key]["nodes"]
            edges = self.graphs[graph_key]["edges"]

            if node_id not in nodes:
                raise NodeNotFoundError(level, node_id)

            # Delete connected edges
            edges_to_delete = [
                key for key, edge in edges.items()
                if edge["from"] == node_id or edge["to"] == node_id
            ]

            for key in edges_to_delete:
                del edges[key]

            # Delete node
            del nodes[node_id]

            self.dirty[graph_key] = True

            logger.info(f"Deleted node '{node_id}' and {len(edges_to_delete)} edges from {level} graph")
            return {"deleted": node_id, "level": level, "edges_deleted": len(edges_to_delete)}

    def delete_edge(
        self,
        level: str,
        from_ref: str,
        to_ref: str,
        rel: str,
        session_id: str | None = None,
    ) -> dict:
        """Delete an edge."""
        with self.lock:
            graph_key = self._get_graph_key(level, session_id)

            # Ensure project graph is loaded
            if graph_key.startswith("project:"):
                project_path = graph_key.split(":", 1)[1]
                self._ensure_project_loaded(project_path)

            edges = self.graphs[graph_key]["edges"]
            edge_key = (from_ref, to_ref, rel)

            if edge_key in edges:
                del edges[edge_key]
                self.dirty[graph_key] = True
                logger.debug(f"Deleted edge {from_ref}->{to_ref}:{rel} from {level} graph")
                return {"deleted": True, "level": level}
            else:
                return {"deleted": False, "level": level}

    def recall_node(self, level: str, node_id: str, session_id: str | None = None) -> dict:
        """Recall (unarchive) an archived node."""
        with self.lock:
            graph_key = self._get_graph_key(level, session_id)

            # Ensure project graph is loaded
            if graph_key.startswith("project:"):
                project_path = graph_key.split(":", 1)[1]
                self._ensure_project_loaded(project_path)

            nodes = self.graphs[graph_key]["nodes"]

            if node_id not in nodes:
                raise NodeNotFoundError(level, node_id)

            node = nodes[node_id]

            if not is_archived(node):
                raise NodeNotArchivedError(level, node_id)

            # Unarchive
            del node["_archived"]
            if "_orphaned_ts" in node:
                del node["_orphaned_ts"]

            # Update version
            ver_key = version_key_node(node_id)
            self._bump_version(graph_key, ver_key, session_id)

            self.dirty[graph_key] = True

            logger.info(f"Recalled node '{node_id}' in {level} graph")
            return {"node": node, "level": level}

    def get_sync_diff(self, session_id: str, start_ts: float) -> dict:
        """
        Get changes since a timestamp for a session.
        Returns dict with "user" and "project" diffs.
        """
        with self.lock:
            def get_updates(graph_key: str) -> dict:
                versions = self._versions[graph_key]
                updates = {
                    "nodes": {},
                    "edges": {},
                }

                for key, ver in versions.items():
                    if ver["ts"] > start_ts and ver.get("session") != session_id:
                        if key.startswith("node:"):
                            node_id = key.split(":", 1)[1]
                            if node_id in self.graphs[graph_key]["nodes"]:
                                updates["nodes"][node_id] = self.graphs[graph_key]["nodes"][node_id]
                        elif key.startswith("edge:"):
                            # Parse edge key
                            edge_part = key.split(":", 1)[1]
                            # Find matching edge
                            for edge in self.graphs[graph_key]["edges"].values():
                                edge_id = f"{edge['from']}->{edge['to']}:{edge['rel']}"
                                if edge_part == edge_id:
                                    updates["edges"][edge_id] = edge
                                    break

                return updates

            result = {
                "user": get_updates("user"),
                "project": {"nodes": {}, "edges": {}}
            }

            # Add project updates if session has one
            try:
                project_path = self.session_manager.get_project_path(session_id)
                if project_path:
                    project_key = f"project:{project_path}"
                    if project_key in self.graphs:
                        result["project"] = get_updates(project_key)
            except Exception as e:
                logger.warning(f"Could not get project updates for session {session_id}: {e}")

            return result

    # ========================================================================
    # Maintenance
    # ========================================================================

    def _maybe_compact(self, graph_key: str):
        """Compact graph if over token limit. Caller must hold lock."""
        archived = self.compactor.compact_if_needed(
            self.graphs[graph_key]["nodes"],
            self.graphs[graph_key]["edges"],
            self._versions[graph_key]
        )

        if archived:
            self.dirty[graph_key] = True

    def _prune_orphans(self, graph_key: str):
        """Prune orphaned archived nodes after grace period. Caller must hold lock."""
        nodes = self.graphs[graph_key]["nodes"]
        edges = self.graphs[graph_key]["edges"]

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
                    self.dirty[graph_key] = True
            else:
                # Orphaned
                if "_orphaned_ts" not in node:
                    # Newly orphaned
                    node["_orphaned_ts"] = current_time
                    self.dirty[graph_key] = True
                    logger.debug(f"Node '{node_id}' orphaned in {graph_key}")
                else:
                    # Check if grace expired
                    orphaned_duration = current_time - node["_orphaned_ts"]
                    if orphaned_duration > grace_seconds:
                        to_delete.append(node_id)

        # Delete expired orphans
        for node_id in to_delete:
            # Delete connected edges
            edges_to_delete = [
                key for key, edge in edges.items()
                if edge["from"] == node_id or edge["to"] == node_id
            ]
            for key in edges_to_delete:
                del edges[key]

            del nodes[node_id]
            self.dirty[graph_key] = True
            logger.info(f"Pruned orphaned node '{node_id}' from {graph_key}")

    def _save_to_disk(self, graph_key: str) -> bool:
        """Save a graph to disk. Caller must hold lock."""
        success = self._persistence[graph_key].save(
            self.graphs[graph_key],
            self._versions[graph_key]
        )

        if success:
            self._persistence[graph_key].maybe_backup()

        return success

    def _periodic_save(self):
        """Background thread for periodic saves and maintenance."""
        while self.running:
            time.sleep(self.config.save_interval)

            with self.lock:
                for graph_key in list(self.graphs.keys()):
                    # Run maintenance
                    self._maybe_compact(graph_key)
                    self._prune_orphans(graph_key)

                    # Save if dirty
                    if self.dirty.get(graph_key, False):
                        if self._save_to_disk(graph_key):
                            self.dirty[graph_key] = False

                # Cleanup expired sessions
                self.session_manager.cleanup_expired()

    def shutdown(self):
        """Gracefully shutdown the store."""
        logger.info("Shutting down graph store...")
        self.running = False
        self.saver_thread.join(timeout=5)

        # Final save
        with self.lock:
            for graph_key in self.graphs.keys():
                if self.dirty.get(graph_key, False):
                    self._save_to_disk(graph_key)

        logger.info("Graph store shutdown complete")
