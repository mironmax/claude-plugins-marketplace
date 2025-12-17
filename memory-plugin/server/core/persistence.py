"""Graph persistence with atomic writes and tiered backup strategy."""

import json
import logging
import os
import shutil
import time
from pathlib import Path
from .constants import (
    MAX_RECENT_BACKUPS,
    MAX_DAILY_BACKUPS,
    MAX_WEEKLY_BACKUPS,
    BACKUP_INTERVAL_SECONDS,
)
from .utils import edge_storage_key

logger = logging.getLogger(__name__)


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
