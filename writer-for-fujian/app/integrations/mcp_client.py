import os
import asyncio
import traceback
from typing import List, Dict, Optional, Any
import logging
from mcp import ClientSession
from mcp.client.sse import sse_client

logger = logging.getLogger(__name__)

class LegalMCPClient:
    """北大法宝法律智能检索 MCP 客户端"""
    
    def __init__(self, sse_url: str = None, api_key: str = None):
        """
        初始化客户端
        
        Args:
            sse_url: ModelScope MCP 服务的 SSE URL
            api_key: ModelScope API Key (如果需要鉴权)
        """
        self.sse_url = sse_url or os.getenv("MCP_SSE_URL")
        self.api_key = api_key or os.getenv("MODELSCOPE_KEY")
        self.force_host_header = (os.getenv("MCP_FORCE_HOST_HEADER") or "").strip()
        
        if not self.sse_url:
            raise ValueError("MCP_SSE_URL is not set")
            
        self.headers = {}
        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"
        if self.force_host_header:
            # Some FastMCP deployments validate Host strictly; in Docker this may require override.
            self.headers["Host"] = self.force_host_header

        logger.info(
            "LegalMCPClient initialized, endpoint=%s, force_host_header=%s",
            self.sse_url,
            self.force_host_header or "<none>",
        )

    @staticmethod
    def _parse_text_payload(text: Any) -> Any:
        if not isinstance(text, str):
            return text
        try:
            import json
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return text

    @staticmethod
    def _format_exception_detail(exc: Exception) -> str:
        """Render nested exception groups for actionable logs."""
        details: List[str] = []

        def walk(e: BaseException, depth: int = 0) -> None:
            prefix = "  " * depth
            details.append(f"{prefix}{type(e).__name__}: {e}")
            nested = getattr(e, "exceptions", None)
            if nested:
                for sub in nested:
                    walk(sub, depth + 1)

        walk(exc)
        return "\n".join(details)
    
    async def list_tools(self) -> List[Any]:
        """列出可用工具"""
        try:
            logger.info("MCP list_tools start")
            async with sse_client(self.sse_url, headers=self.headers) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    logger.info(f"MCP list_tools success, count={len(result.tools)}")
                    return result.tools
        except asyncio.CancelledError as e:
            logger.warning(f"MCP list_tools cancelled: {e}")
            return []
        except Exception as e:
            logger.error("MCP list_tools failed: %s\n%s", self._format_exception_detail(e), traceback.format_exc())
            return []

    async def get_article(self, number: str, title: str) -> Dict[str, Any]:
        """
        通过包含法规名称和法条条号的文本，获取法条内容
        
        Args:
            number: 法条条号，如"第264条"
            title: 法规名称，如"刑法"
            
        Returns:
            Dict: 包含法条内容的字典
        """
        try:
            logger.info(f"MCP get_article start: title={title}, number={number}")
            async with sse_client(self.sse_url, headers=self.headers) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "get_article",
                        arguments={
                            "number": number,
                            "title": title
                        }
                    )
                    if result.content and len(result.content) > 0:
                        for item in result.content:
                            parsed = self._parse_text_payload(getattr(item, "text", None))
                            if isinstance(parsed, dict):
                                logger.info("MCP get_article success: dict payload")
                                return parsed
                            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                                logger.info("MCP get_article success: list payload")
                                return parsed[0]
            logger.info("MCP get_article finished: empty result")
            return {}
        except asyncio.CancelledError as e:
            logger.warning(f"MCP get_article cancelled: {e}")
            return {}
        except Exception as e:
            logger.error("MCP get_article failed: %s\n%s", self._format_exception_detail(e), traceback.format_exc())
            return {}

    async def search_article(
        self,
        text: str,
        page: int | str = 1,
        page_size: int | str = 20,
        sort_by: str = "relevance",
        order: str = "desc",
    ) -> List[Dict[str, Any]]:
        """
        通过语义检索查找相关法条
        
        Args:
            text: 搜索关键词，如"盗窃罪数额标准"
            
        Returns:
            List[Dict]: 相关法条列表
        """
        try:
            logger.info(
                "MCP search_article start: text=%s, page=%s, page_size=%s, sort_by=%s, order=%s",
                text,
                page,
                page_size,
                sort_by,
                order,
            )
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
                        }
                    )
                    if result.content and len(result.content) > 0:
                        aggregated: List[Dict[str, Any]] = []
                        for item in result.content:
                            parsed = self._parse_text_payload(getattr(item, "text", None))
                            if isinstance(parsed, list):
                                aggregated.extend(x for x in parsed if isinstance(x, dict))
                            elif isinstance(parsed, dict):
                                aggregated.append(parsed)
                        logger.info(f"MCP search_article success: count={len(aggregated)}")
                        return aggregated
            logger.info("MCP search_article finished: empty result")
            return []
        except asyncio.CancelledError as e:
            logger.warning(f"MCP search_article cancelled: {e}")
            return []
        except Exception as e:
            logger.error("MCP search_article failed: %s\n%s", self._format_exception_detail(e), traceback.format_exc())
            return []
