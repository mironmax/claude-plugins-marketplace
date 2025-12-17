#!/usr/bin/env python3
"""
Startup script for Knowledge Graph HTTP Server.

Usage:
    python start_http_server.py [--port PORT] [--host HOST]

Environment variables:
    KG_HTTP_PORT: Server port (default: 8765)
    KG_HTTP_HOST: Server host (default: 127.0.0.1)
    KG_LOG_LEVEL: Logging level (default: INFO)
    KG_MAX_TOKENS: Max tokens per graph (default: 5000)
    KG_SAVE_INTERVAL: Save interval in seconds (default: 30)
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Ensure server directory is in path
sys.path.insert(0, str(Path(__file__).parent))

logger = logging.getLogger(__name__)


def main():
    """Start the HTTP server."""
    parser = argparse.ArgumentParser(description="Knowledge Graph HTTP Server")
    parser.add_argument("--port", type=int, default=None, help="Server port (default: 8765)")
    parser.add_argument("--host", default=None, help="Server host (default: 127.0.0.1)")
    parser.add_argument("--log-level", default=None, help="Log level (default: INFO)")

    args = parser.parse_args()

    # Set environment variables from args if provided
    if args.port:
        os.environ["KG_HTTP_PORT"] = str(args.port)
    if args.host:
        os.environ["KG_HTTP_HOST"] = args.host
    if args.log_level:
        os.environ["KG_LOG_LEVEL"] = args.log_level.upper()

    # Get final config
    port = int(os.getenv("KG_HTTP_PORT", "8765"))
    host = os.getenv("KG_HTTP_HOST", "127.0.0.1")
    log_level = os.getenv("KG_LOG_LEVEL", "INFO").lower()

    print(f"Starting Knowledge Graph HTTP Server on {host}:{port}")
    print(f"Log level: {log_level.upper()}")
    print(f"Press Ctrl+C to stop")
    print("")

    try:
        import uvicorn
        from mcp_http.app import app

        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level=log_level,
        )
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except Exception as e:
        print(f"Error starting server: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
