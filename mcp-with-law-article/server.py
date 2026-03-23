"""
MCP server for legal article retrieval.
"""

from __future__ import annotations

import asyncio
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

from mcp.server.fastmcp import FastMCP

# Add the current directory to sys.path to enable absolute imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_connector import LegalDatabaseConnector

mcp = FastMCP("legal-article")


def _extend_allowed_hosts() -> None:
    """Extend FastMCP allowed_hosts for Docker-internal service names."""
    transport_security = mcp.settings.transport_security
    default_hosts = [
        "mcp-service:*",
        "writer-service:*",
        "127.0.0.1:*",
        "localhost:*",
    ]
    env_hosts = [
        item.strip()
        for item in (os.getenv("MCP_ALLOWED_HOSTS", "") or "").split(",")
        if item.strip()
    ]

    for host_pattern in [*default_hosts, *env_hosts]:
        if host_pattern not in transport_security.allowed_hosts:
            transport_security.allowed_hosts.append(host_pattern)


_extend_allowed_hosts()

db = LegalDatabaseConnector("config.ini")
db.connect()

DB_THREAD_WORKERS = max(2, int(os.getenv("MCP_DB_THREAD_WORKERS", "16")))
_db_executor = ThreadPoolExecutor(max_workers=DB_THREAD_WORKERS, thread_name_prefix="mcp-db")


async def _run_db_call(func, *args, **kwargs):
    """Run blocking psycopg2 calls in a dedicated thread pool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_db_executor, lambda: func(*args, **kwargs))


@mcp.tool()
async def get_article(number: str, title: str) -> Dict[str, Any]:
    """Get a single article by section number and law title."""
    record = await _run_db_call(db.get_article, number, title)
    return record or {}


@mcp.tool()
async def search_article(
    text: str,
    page: int | str = 1,
    page_size: int | str = 10,
    sort_by: str = "relevance",
    order: str = "desc",
) -> List[Dict[str, Any]]:
    """Search articles by keyword with paging and sorting."""
    return await _run_db_call(
        db.search_articles,
        text,
        page,
        page_size,
        sort_by,
        order,
    )


if __name__ == "__main__":
    mcp.run()
