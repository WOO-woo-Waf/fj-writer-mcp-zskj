"""
MCP server for legal article retrieval.
"""

from __future__ import annotations

import os
import sys
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


@mcp.tool()
def get_article(number: str, title: str) -> Dict[str, Any]:
    """Get a single article by section number and law title."""
    record = db.get_article(number, title)
    return record or {}


@mcp.tool()
def search_article(
    text: str,
    page: int | str = 1,
    page_size: int | str = 10,
    sort_by: str = "relevance",
    order: str = "desc",
) -> List[Dict[str, Any]]:
    """Search articles by keyword with paging and sorting."""
    return db.search_articles(
        text,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        order=order,
    )


if __name__ == "__main__":
    mcp.run()
