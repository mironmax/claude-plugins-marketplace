#!/usr/bin/env python3
"""
Sync version from plugin.json to version.py
Run this script after updating plugin.json version.
"""

import json
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).parent
PLUGIN_JSON = SCRIPT_DIR.parent / ".claude-plugin" / "plugin.json"
VERSION_PY = SCRIPT_DIR / "version.py"

def sync_version():
    """Read version from plugin.json and write to version.py"""

    # Read plugin.json
    with open(PLUGIN_JSON) as f:
        plugin_data = json.load(f)

    version = plugin_data.get("version")
    if not version:
        raise ValueError("No version found in plugin.json")

    # Write version.py
    version_content = f'''"""Version information for Knowledge Graph MCP Server."""

__version__ = "{version}"
'''

    with open(VERSION_PY, "w") as f:
        f.write(version_content)

    print(f"✓ Synced version {version} to version.py")

if __name__ == "__main__":
    sync_version()
