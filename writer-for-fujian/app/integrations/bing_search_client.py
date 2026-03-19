#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Bing 搜索 MCP 客户端
通过 SSE (Server-Sent Events) 协议连接到 Bing 搜索 MCP 服务器
"""
import os
import json
from typing import List, Dict, Optional, Any
from mcp import ClientSession
from mcp.client.sse import sse_client


class BingSearchMCPClient:
    """Bing 搜索 MCP 客户端（SSE 传输）"""
    
    def __init__(self, sse_url: str = None):
        """
        初始化客户端
        
        Args:
            sse_url: SSE 服务器 URL，默认从环境变量 BING_MCP_SSE_URL 读取
        """
        self.sse_url = sse_url or os.getenv(
            "BING_MCP_SSE_URL", 
            "https://mcp.api-inference.modelscope.net/3d20be0e9a434b/sse"
        )
        
        if not self.sse_url:
            raise ValueError("Bing MCP SSE URL not provided")
    
    async def list_tools(self) -> List[Any]:
        """列出可用工具"""
        try:
            async with sse_client(self.sse_url) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    return result.tools
        except Exception as e:
            print(f"Error in list_tools: {e}")
            raise e

    async def search(
        self,
        query: str,
        count: int = 10,
        market: str = "zh-CN"
    ) -> Dict[str, Any]:
        """
        执行 Bing 搜索
        
        Args:
            query: 搜索关键词
            count: 返回结果数量（默认 10）
            market: 市场/语言代码（默认 zh-CN 中文）
            
        Returns:
            Dict: 搜索结果，包含：
                - status: "success" 或 "error"
                - results: 搜索结果列表
                - total: 结果总数
        """
        async with sse_client(self.sse_url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                # 获取工具列表，找到搜索工具
                tools = await session.list_tools()
                search_tool = None
                for tool in tools.tools:
                    if "search" in tool.name.lower() or "bing" in tool.name.lower():
                        search_tool = tool.name
                        break
                
                if not search_tool:
                    raise ValueError("Search tool not found in MCP server")
                
                # 调用搜索工具
                arguments = {
                    "query": query,
                    "count": count,
                    "market": market
                }
                
                result = await session.call_tool(search_tool, arguments=arguments)
                
                # 打印原始结果以便调试
                # if result.content:
                    # print(f"DEBUG: Bing MCP Raw Result: {result.content[0].text[:500]}...")
                
                if result.content and len(result.content) > 0:
                    content = result.content[0]
                    if hasattr(content, 'text'):
                        try:
                            return json.loads(content.text)
                        except json.JSONDecodeError:
                            return {"status": "success", "raw": content.text}
                    return {"status": "success", "content": str(content)}
                
                return {"status": "error", "message": "No content returned"}


# 便捷函数
async def bing_search(query: str, count: int = 10, market: str = "zh-CN") -> Dict[str, Any]:
    """
    便捷的 Bing 搜索函数
    
    Args:
        query: 搜索关键词
        count: 返回结果数量
        market: 市场/语言代码
        
    Returns:
        搜索结果字典
    """
    client = BingSearchMCPClient()
    return await client.search(query, count, market)
