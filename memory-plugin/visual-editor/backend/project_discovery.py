"""
Project discovery utilities for visual editor.

Discovers Claude Code projects from ~/.claude/projects/ directory.
"""

import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ScraperStatus:
    """Status of incremental scraper."""
    enabled: bool = False
    started: bool = False
    completed: bool = False
    progress_pct: float = 0.0
    total_tasks: int = 0
    completed_tasks: int = 0
    started_at: Optional[float] = None
    updated_at: Optional[float] = None
    completed_at: Optional[float] = None
    details: dict = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}


@dataclass
class ProjectMetadata:
    """Complete project metadata."""
    project_path: str
    display_name: str
    last_used: float
    conversation_count: int
    has_graph: bool
    node_count: Optional[int] = None
    edge_count: Optional[int] = None
    history_scraper: Optional[dict] = None
    codebase_scraper: Optional[dict] = None


def decode_claude_project_path_from_cwd(project_dir: Path) -> Path | None:
    """
    Get actual project path from .cwd field in session files.

    This is more reliable than decoding the directory name since encoding
    is ambiguous for paths containing hyphens.

    Args:
        project_dir: Path to ~/.claude/projects/<encoded-name>/

    Returns:
        Decoded project path or None if no sessions found
    """
    import json

    # Find any .jsonl file (not agent-)
    session_files = [f for f in project_dir.glob("*.jsonl")
                     if not f.name.startswith("agent-")]

    if not session_files:
        return None

    # Read first line of first session file to get .cwd
    try:
        with open(session_files[0], 'r') as f:
            first_line = f.readline()
            data = json.loads(first_line)
            cwd = data.get('cwd')
            if cwd:
                return Path(cwd)
    except Exception:
        pass

    return None


def decode_claude_project_path(encoded: str) -> Path:
    """
    Decode Claude Code's project directory naming (FALLBACK ONLY).

    WARNING: This is ambiguous for paths containing hyphens!
    Use decode_claude_project_path_from_cwd() when possible.

    Examples:
        "-home-maxim-DevProj-my-project" -> Path("/home/maxim/DevProj/my-project")
        But "-home-maxim-DevProj-claude-plugins-marketplace" could be either:
          - "/home/maxim/DevProj/claude-plugins-marketplace" (correct)
          - "/home/maxim/DevProj/claude/plugins/marketplace" (wrong)

    Args:
        encoded: Encoded directory name from ~/.claude/projects/

    Returns:
        Decoded Path object (may be incorrect!)
    """
    if encoded.startswith("-"):
        # Absolute path: first - becomes /, rest become /
        decoded = "/" + encoded[1:].replace("-", "/")
        return Path(decoded)
    else:
        # Relative path (rare)
        return Path(encoded)


def format_project_name(project_path: Path) -> str:
    """
    Extract short, readable name from project path.

    Strategy:
    - If path depth >= 2: show parent/name (e.g., "DevProj/my-project")
    - Otherwise: show name only
    - Max length: 50 chars (truncate if needed)

    Args:
        project_path: Absolute path to project root

    Returns:
        Display name for UI
    """
    parts = project_path.parts

    if len(parts) >= 2:
        # Show parent/name
        display = f"{parts[-2]}/{parts[-1]}"
    else:
        # Show name only
        display = parts[-1] if parts else str(project_path)

    # Truncate if too long
    if len(display) > 50:
        display = display[:47] + "..."

    return display


def load_graph_stats(graph_path: Path) -> tuple[bool, Optional[int], Optional[int]]:
    """
    Load graph statistics from graph.json file.

    Args:
        graph_path: Path to .knowledge/graph.json

    Returns:
        Tuple of (has_graph, node_count, edge_count)
    """
    if not graph_path.exists():
        return False, None, None

    try:
        data = json.loads(graph_path.read_text())

        # Graph format: {"nodes": {...}, "edges": {...}}
        nodes = data.get("nodes", {})
        edges = data.get("edges", {})

        node_count = len(nodes) if isinstance(nodes, dict) else 0
        edge_count = len(edges) if isinstance(edges, dict) else 0

        return True, node_count, edge_count
    except Exception as e:
        logger.error(f"Error reading graph {graph_path}: {e}")
        return True, None, None  # File exists but couldn't parse


def load_scraper_status(project_path: Path) -> dict:
    """
    Load scraper status from .scraper_status.json file.

    Args:
        project_path: Path to project root

    Returns:
        Dict with "history" and "codebase" scraper status
    """
    status_path = project_path / ".knowledge/.scraper_status.json"

    if status_path.exists():
        try:
            return json.loads(status_path.read_text())
        except Exception as e:
            logger.error(f"Error reading scraper status {status_path}: {e}")

    # Fallback: check old marker files
    history_marker = project_path / ".knowledge/.history_scraped"
    codebase_marker = project_path / ".knowledge/.codebase_scraped"

    return {
        "history": asdict(ScraperStatus(
            enabled=history_marker.exists(),
            completed=history_marker.exists(),
            progress_pct=100.0 if history_marker.exists() else 0.0
        )),
        "codebase": asdict(ScraperStatus(
            enabled=codebase_marker.exists(),
            completed=codebase_marker.exists(),
            progress_pct=100.0 if codebase_marker.exists() else 0.0
        ))
    }


def discover_projects() -> list[dict]:
    """
    Discover all Claude Code projects from ~/.claude/projects/.

    Returns:
        List of project metadata dicts, sorted by last_used (most recent first)
    """
    projects_dir = Path.home() / ".claude" / "projects"

    if not projects_dir.exists():
        logger.warning(f"Projects directory not found: {projects_dir}")
        return []

    projects = []

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue

        # Decode project path from session files (reliable)
        project_path = decode_claude_project_path_from_cwd(project_dir)

        # Fallback: decode from directory name (ambiguous)
        if project_path is None:
            project_path = decode_claude_project_path(project_dir.name)
            logger.warning(f"Using fallback path decoding for {project_dir.name} -> {project_path}")

        # Check if project directory still exists
        project_exists = project_path.exists()

        if not project_exists:
            logger.debug(f"Project directory deleted: {project_path}")
            continue  # Skip deleted projects

        # Get conversation stats from .jsonl files
        jsonl_files = list(project_dir.glob("*.jsonl"))

        # Filter out agent files (optional, or keep them)
        conversation_files = [
            f for f in jsonl_files
            if not f.name.startswith("agent-")
        ]

        if jsonl_files:
            last_used = max((f.stat().st_mtime for f in jsonl_files), default=0)
        else:
            last_used = 0

        # Get graph stats
        graph_path = project_path / ".knowledge" / "graph.json"
        has_graph, node_count, edge_count = load_graph_stats(graph_path)

        # Get scraper status
        scraper_status = load_scraper_status(project_path)

        # Create metadata
        metadata = ProjectMetadata(
            project_path=str(project_path),
            display_name=format_project_name(project_path),
            last_used=last_used,
            conversation_count=len(conversation_files),
            has_graph=has_graph,
            node_count=node_count,
            edge_count=edge_count,
            history_scraper=scraper_status.get("history"),
            codebase_scraper=scraper_status.get("codebase")
        )

        projects.append(asdict(metadata))

    # Sort by last_used descending (most recent first)
    projects.sort(key=lambda p: p["last_used"], reverse=True)

    logger.info(f"Discovered {len(projects)} projects")

    return projects


if __name__ == "__main__":
    # Test discovery
    logging.basicConfig(level=logging.INFO)

    projects = discover_projects()

    print(f"\nFound {len(projects)} projects:\n")

    for p in projects[:5]:  # Show first 5
        print(f"📁 {p['display_name']}")
        print(f"   Path: {p['project_path']}")
        print(f"   Conversations: {p['conversation_count']}")

        if p['has_graph']:
            print(f"   Graph: {p['node_count']} nodes, {p['edge_count']} edges")
        else:
            print(f"   Graph: Not created")

        print()
