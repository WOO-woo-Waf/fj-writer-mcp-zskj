#!/usr/bin/env python
"""
Start the legal article MCP server.

This script starts the FastMCP server on the default endpoint.

Usage:
    python run_server.py
    # Or specify a custom config file:
    python run_server.py --config ../config.ini
"""

import argparse
import sys

from server import mcp


def main():
    parser = argparse.ArgumentParser(
        description="Start legal article MCP server"
    )
    parser.add_argument(
        "--config",
        default="config.ini",
        help="Path to config file (default: config.ini)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Server host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Server port (default: 8000)",
    )

    args = parser.parse_args()

    print("\n╔" + "=" * 78 + "╗")
    print("║" + " " * 15 + "Legal Article MCP Server - FastMCP" + " " * 28 + "║")
    print("╚" + "=" * 78 + "╝\n")

    print(f"📋 Configuration:")
    print(f"  Config file: {args.config}")
    print(f"  Server: {args.host}:{args.port}")
    print(f"\n🚀 Starting server...\n")

    try:
        mcp.settings.host = args.host
        mcp.settings.port = args.port

        # Run MCP with SSE transport for HTTP clients (mcp.client.sse)
        mcp.run(transport="sse")
    except KeyboardInterrupt:
        print("\n\n⛔ Server stopped")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Server error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
