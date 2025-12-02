#!/usr/bin/env python3
"""Read and merge user + project knowledge graphs."""
import json
from pathlib import Path

def get_user_graph_path():
    return Path.home() / ".claude/knowledge" / "user.json"

def get_project_graph_path():
    return Path(".knowledge") / "graph.json"

def load_graph(path):
    if not path.exists():
        return {"nodes": [], "edges": []}
    with open(path) as f:
        return json.load(f)

def main():
    user_graph = load_graph(get_user_graph_path())
    project_graph = load_graph(get_project_graph_path())
    merged = {"user": user_graph, "project": project_graph}
    print(json.dumps(merged, indent=2))

if __name__ == "__main__":
    main()
