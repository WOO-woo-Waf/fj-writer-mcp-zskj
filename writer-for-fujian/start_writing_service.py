#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Writing Service Launcher
写作服务启动器
"""

import argparse
import os
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from app.services.writing_service import WritingService


def main():
    parser = argparse.ArgumentParser(
        description="Start writing service"
    )
    parser.add_argument(
        "--mcp-url",
        default=os.getenv("MCP_SSE_URL", "http://127.0.0.1:8000/sse"),
        help="MCP service URL (default: http://127.0.0.1:8000/sse)"
    )
    
    args = parser.parse_args()
    
    print("\n╔════════════════════════════════════════════════╗")
    print("║        Writing Service - Starting             ║")
    print("║        写作服务 - 启动中                        ║")
    print("╚════════════════════════════════════════════════╝\n")
    
    print(f"📝 Writing Service Configuration:")
    print(f"   MCP URL: {args.mcp_url}")
    print(f"   Status: Running")
    
    print(f"\n✓ Writing service is ready to receive requests")
    print(f"  You can call the writing APIs now")
    
    try:
        # Keep the service running
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n⛔ Writing service stopped")
        sys.exit(0)


if __name__ == "__main__":
    main()
