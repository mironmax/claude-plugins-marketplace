"""Graph compaction (archiving low-value nodes)."""

import logging
from .constants import COMPACTION_TARGET_RATIO
from .estimator import TokenEstimator
from .scorer import NodeScorer

logger = logging.getLogger(__name__)


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
