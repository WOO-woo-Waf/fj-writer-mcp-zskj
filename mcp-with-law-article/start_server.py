#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
One-click MCP Server Launcher
启动法律条文 MCP 服务的一键脚本

支持功能：
1. 自动配置检查
2. 数据库连接验证
3. 服务状态监控
"""

import argparse
import os
import sys
import signal
from pathlib import Path
from typing import Optional

# Add the current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server import mcp, db


class MCPServerLauncher:
    """MCP Server Launcher"""
    
    def __init__(self, config_path: str = "config.ini", host: str = "127.0.0.1", port: int = 8000):
        self.config_path = config_path
        self.host = host
        self.port = port
        self.running = False
    
    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(sig, frame):
            print("\n\n⛔ Received shutdown signal, stopping server...")
            self.shutdown()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def verify_config(self) -> bool:
        """Verify configuration file exists"""
        if not os.path.exists(self.config_path):
            print(f"✗ Config file not found: {self.config_path}")
            example_file = f"{self.config_path.replace('.ini', '.example.ini')}"
            if os.path.exists(example_file):
                print(f"📝 Found example config: {example_file}")
                print(f"   Please copy it to {self.config_path} and configure your database")
            return False
        print(f"✓ Config file found: {self.config_path}")
        return True
    
    def verify_database_connection(self) -> bool:
        """Verify database connection"""
        try:
            print("\n🔗 Verifying database connection...")
            db.connect()
            
            # Test a simple query
            test_result = db.search_articles("test", page=1, page_size=1)
            print(f"✓ Database connection successful")
            print(f"  Host: {db.config.get('host')}")
            print(f"  Database: {db.config.get('database')}")
            return True
        except Exception as e:
            print(f"✗ Database connection failed: {e}")
            print("\n💡 Please check:")
            print("   1. PostgreSQL server is running")
            print("   2. Config file (config.ini) has correct credentials")
            print("   3. Database and tables exist")
            return False
    
    def print_banner(self):
        """Print startup banner"""
        banner = """
╔════════════════════════════════════════════════════════════════════════════╗
║                                                                            ║
║                  Legal Article MCP Server Launcher                         ║
║                     法律条文 MCP 服务启动器                                  ║
║                                                                            ║
╚════════════════════════════════════════════════════════════════════════════╝
        """
        print(banner)
    
    def print_config_info(self):
        """Print configuration info"""
        sse_url = f"http://{self.host}:{self.port}/sse"
        print(f"\n📋 Server Configuration:")
        print(f"  ├─ Host: {self.host}")
        print(f"  ├─ Port: {self.port}")
        print(f"  ├─ Config File: {os.path.abspath(self.config_path)}")
        print(f"  └─ Database: {db.config.get('database', 'unknown')}")
        
        print(f"\n🔧 Available MCP Tools:")
        print(f"  ├─ get_article(number, title) - Get single article by section number")
        print(f"  └─ search_article(text, page, page_size, sort_by, order) - Search articles")
        
        print(f"\n🎯 Next Steps:")
        print(f"  1. Configure your MCP client to connect to this server")
        print(f"  2. For SSE (Server-Sent Events):")
        print(f"     MCP_SSE_URL={sse_url}")
        print(f"  3. Press Ctrl+C to stop the server\n")
    
    def run(self):
        """Run the server"""
        self.print_banner()
        
        # Verify config
        if not self.verify_config():
            return False
        
        # Verify database
        if not self.verify_database_connection():
            return False
        
        # Print configuration
        self.print_config_info()
        
        # Setup signal handlers
        self.setup_signal_handlers()
        
        # Run the server
        try:
            print(f"🚀 Starting MCP server...\n")
            self.running = True

            mcp.settings.host = self.host
            mcp.settings.port = self.port
            
            # Run MCP with SSE transport for HTTP clients (mcp.client.sse)
            mcp.run(transport="sse")
            
        except KeyboardInterrupt:
            print("\n\n⛔ Server interrupted by user")
            self.shutdown()
            return True
        except Exception as e:
            print(f"\n✗ Server error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def shutdown(self):
        """Clean shutdown"""
        self.running = False
        try:
            db.disconnect()
            print("✓ Database connections closed")
        except Exception as e:
            print(f"⚠ Error closing database: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Start legal article MCP server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python start_server.py                          # Use default config.ini
  python start_server.py --config config.ini      # Specify config file
  python start_server.py --host 0.0.0.0           # Bind to all interfaces
  python start_server.py --port 9000              # Use custom port
        """
    )
    
    parser.add_argument(
        "--config",
        default="config.ini",
        help="Path to config file (default: config.ini)"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Server host (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Server port (default: 8000)"
    )
    
    args = parser.parse_args()
    
    launcher = MCPServerLauncher(
        config_path=args.config,
        host=args.host,
        port=args.port
    )
    
    success = launcher.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
