"""Node scoring for compaction decisions."""

import time


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
