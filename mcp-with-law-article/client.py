"""
Legal MCP Client - Async client for legal article search service.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

try:
    import httpx
    from mcp import ClientSession
    from mcp.client.sse import sse_client
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False


class LegalMCPClient:
    """Async client for legal article MCP service."""

    def __init__(self, sse_url: str | None = None, api_key: str | None = None):
        """
        Initialize MCP client.

        Args:
            sse_url: SSE endpoint URL (e.g., "http://127.0.0.1:8000/sse")
            api_key: Optional API key for authentication
        """
        if not MCP_AVAILABLE:
            raise RuntimeError("mcp not installed. Run: pip install mcp")

        resolved_url = sse_url or os.getenv("MCP_SSE_URL") or "http://127.0.0.1:8000/sse"
        if resolved_url.endswith("/"):
            resolved_url = resolved_url[:-1]
        if not resolved_url.endswith("/sse"):
            resolved_url = f"{resolved_url}/sse"

        self.sse_url = resolved_url
        self.api_key = api_key
        self.headers = {}
        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"

    @staticmethod
    def _parse_text_payload(text: Any) -> Any:
        if not isinstance(text, str):
            return text
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return text

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools."""
        async with sse_client(self.sse_url, headers=self.headers) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                return [
                    {"name": tool.name, "description": tool.description}
                    for tool in result.tools
                ]

    async def get_article(self, number: str, title: str) -> Dict[str, Any]:
        """
        Get article by section number and law title.

        Args:
            number: Section number (e.g., "第264条")
            title: Law title (e.g., "刑法")

        Returns:
            Article data as dictionary
        """
        async with sse_client(self.sse_url, headers=self.headers) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "get_article",
                    arguments={"number": number, "title": title},
                )
                if result.content and len(result.content) > 0:
                    for item in result.content:
                        parsed = self._parse_text_payload(getattr(item, "text", None))
                        if isinstance(parsed, dict):
                            return parsed
                        if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                            return parsed[0]
                return {}

    async def search_article(
        self,
        text: str,
        page: int | str = 1,
        page_size: int | str = 10,
        sort_by: str = "relevance",
        order: str = "desc",
    ) -> List[Dict[str, Any]]:
        """
        Search articles by keyword with pagination and sorting.

        Args:
            text: Search keyword
            page: Page number (starting from 1), supports int or numeric string
            page_size: Items per page (1-100), supports int or numeric string
            sort_by: Sort field (relevance/updated_at/created_at/id)
            order: Sort order (asc/desc)

        Returns:
            List of matching articles
        """
        async with sse_client(self.sse_url, headers=self.headers) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "search_article",
                    arguments={
                        "text": text,
                        "page": page,
                        "page_size": page_size,
                        "sort_by": sort_by,
                        "order": order,
                    },
                )
                if result.content and len(result.content) > 0:
                    aggregated: List[Dict[str, Any]] = []
                    for item in result.content:
                        parsed = self._parse_text_payload(getattr(item, "text", None))
                        if isinstance(parsed, list):
                            aggregated.extend(x for x in parsed if isinstance(x, dict))
                        elif isinstance(parsed, dict):
                            aggregated.append(parsed)
                    return aggregated
                return []
