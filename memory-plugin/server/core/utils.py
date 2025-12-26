"""Utility functions for knowledge graph operations."""

from .constants import LEVELS
from .exceptions import KGError


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
