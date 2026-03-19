#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
内容检索器
支持多种检索源：本地文档、Web搜索、向量数据库等
"""

import logging
import importlib.util
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """检索结果"""
    title: str
    snippet: str
    source: str
    score: float = 0.0
    full_text: Optional[str] = None
    metadata: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "title": self.title,
            "snippet": self.snippet,
            "source": self.source,
            "score": self.score,
            "full_text": self.full_text,
            "metadata": self.metadata or {}
        }


class ContentRetriever:
    """
    内容检索器
    
    支持的检索源：
    1. 本地文档库（向量检索）
    2. Web搜索（Bing Search MCP）
    3. 历史案例库
    4. 知识图谱
    
    特点：
    - 多源融合
    - 智能排序
    - 去重和过滤
    - 可扩展的检索源
    """
    
    def __init__(
        self,
        enable_local: bool = True,
        enable_web: bool = False,
        enable_case_db: bool = False
    ):
        """
        初始化内容检索器
        
        Args:
            enable_local: 启用本地文档检索
            enable_web: 启用Web搜索
            enable_case_db: 启用案例库检索
        """
        self.enable_local = enable_local
        self.enable_web = enable_web
        self.enable_case_db = enable_case_db
        
        # 初始化各检索源
        self._init_retrievers()
        
        logger.info(f"ContentRetriever initialized - "
                   f"local={enable_local}, web={enable_web}, case_db={enable_case_db}")
    
    def _init_retrievers(self):
        """初始化各个检索源"""
        # 本地文档检索器
        if self.enable_local:
            if importlib.util.find_spec("app.deep_research.retrievers.local_retriever") is None:
                logger.info("Local retriever backend not installed, local retrieval disabled")
                self.local_retriever = None
                self.enable_local = False
            else:
                try:
                    from app.deep_research.retrievers.local_retriever import LocalRetriever
                    self.local_retriever = LocalRetriever([])  # 默认空列表
                    logger.info("Local retriever initialized")
                except Exception as e:
                    logger.warning(f"Failed to initialize local retriever: {e}")
                    self.local_retriever = None
                    self.enable_local = False
        else:
            self.local_retriever = None
        
        # Web搜索
        if self.enable_web:
            try:
                from app.integrations.bing_search_client import BingSearchMCPClient
                self.web_searcher = BingSearchMCPClient()
                logger.info("Web searcher initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize web searcher: {e}")
                self.web_searcher = None
                self.enable_web = False
        else:
            self.web_searcher = None
        
        # 案例库检索器（预留）
        if self.enable_case_db:
            # TODO: 实现案例库检索
            self.case_db_retriever = None
            logger.info("Case DB retriever (not implemented)")
        else:
            self.case_db_retriever = None
    
    async def retrieve(
        self,
        query: str,
        max_results: int = 5,
        sources: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        执行检索
        
        Args:
            query: 检索查询
            max_results: 最大返回结果数
            sources: 指定检索源列表，如 ["local", "web"]，None表示使用所有启用的源
            
        Returns:
            检索结果列表
        """
        logger.info(f"检索: {query} (max_results={max_results})")
        
        all_results = []
        
        # 决定使用哪些检索源
        use_local = (sources is None or "local" in sources) and self.enable_local
        use_web = (sources is None or "web" in sources) and self.enable_web
        use_case_db = (sources is None or "case_db" in sources) and self.enable_case_db
        
        # 1. 本地文档检索
        if use_local and self.local_retriever:
            try:
                local_results = await self._retrieve_local(query)
                all_results.extend(local_results)
                logger.info(f"本地检索返回 {len(local_results)} 条结果")
            except Exception as e:
                logger.error(f"本地检索失败: {e}")
        
        # 2. Web搜索
        if use_web and self.web_searcher:
            try:
                web_results = await self._retrieve_web(query)
                all_results.extend(web_results)
                logger.info(f"Web检索返回 {len(web_results)} 条结果")
            except Exception as e:
                logger.error(f"Web检索失败: {e}")
        
        # 3. 案例库检索
        if use_case_db and self.case_db_retriever:
            try:
                case_results = await self._retrieve_case_db(query)
                all_results.extend(case_results)
                logger.info(f"案例库检索返回 {len(case_results)} 条结果")
            except Exception as e:
                logger.error(f"案例库检索失败: {e}")
        
        # 4. 合并、去重、排序
        final_results = self._merge_and_rank(all_results, max_results)
        
        logger.info(f"最终返回 {len(final_results)} 条结果")
        return final_results
    
    async def _retrieve_local(self, query: str) -> List[Dict[str, Any]]:
        """本地文档检索"""
        if not self.local_retriever:
            return []
        
        try:
            # 调用本地检索器
            chunks = self.local_retriever.search(query, max_hits=5)
            
            results = []
            for chunk in chunks:
                results.append({
                    "title": chunk.metadata.get("source", "本地文档"),
                    "snippet": chunk.text[:200],
                    "source": "local",
                    "score": getattr(chunk, "score", 0.5),
                    "full_text": chunk.text,
                    "metadata": chunk.metadata
                })
            
            return results
            
        except Exception as e:
            logger.error(f"本地检索执行失败: {e}")
            return []
    
    async def _retrieve_web(self, query: str) -> List[Dict[str, Any]]:
        """Web搜索"""
        if not self.web_searcher:
            return []
        
        try:
            # 调用Web搜索
            search_results = await self.web_searcher.search(query, count=5)
            
            results = []
            for item in search_results:
                results.append({
                    "title": item.get("name", ""),
                    "snippet": item.get("snippet", ""),
                    "source": "web",
                    "score": 0.6,  # Web结果给予中等分数
                    "full_text": None,
                    "metadata": {
                        "url": item.get("url", ""),
                        "display_url": item.get("displayUrl", "")
                    }
                })
            
            return results
            
        except Exception as e:
            logger.error(f"Web搜索执行失败: {e}")
            return []
    
    async def _retrieve_case_db(self, query: str) -> List[Dict[str, Any]]:
        """案例库检索（预留）"""
        # TODO: 实现案例库检索逻辑
        return []
    
    def _merge_and_rank(
        self,
        results: List[Dict[str, Any]],
        max_results: int
    ) -> List[Dict[str, Any]]:
        """
        合并和排序结果
        
        Args:
            results: 原始结果列表
            max_results: 最大返回数量
            
        Returns:
            排序后的结果列表
        """
        # 1. 去重（基于标题相似度）
        unique_results = self._deduplicate(results)
        
        # 2. 按分数排序
        sorted_results = sorted(
            unique_results,
            key=lambda x: x.get("score", 0),
            reverse=True
        )
        
        # 3. 截断
        return sorted_results[:max_results]
    
    def _deduplicate(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        去重
        
        简单实现：基于标题完全匹配
        TODO: 可以改进为基于语义相似度的去重
        """
        seen_titles = set()
        unique_results = []
        
        for result in results:
            title = result.get("title", "").strip().lower()
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_results.append(result)
        
        return unique_results
    
    def add_local_source(self, source_path: str):
        """
        添加本地检索源
        
        Args:
            source_path: 本地文档路径
        """
        if not self.enable_local or not self.local_retriever:
            logger.warning("本地检索未启用")
            return
        
        try:
            # TODO: 实现添加本地源的逻辑
            logger.info(f"添加本地检索源: {source_path}")
        except Exception as e:
            logger.error(f"添加本地源失败: {e}")


# ================================
# 便捷函数
# ================================

async def simple_retrieve(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    便捷检索函数
    
    Args:
        query: 检索查询
        max_results: 最大结果数
        
    Returns:
        检索结果列表
    
    示例:
        >>> results = await simple_retrieve("盗窃罪量刑标准")
        >>> for r in results:
        ...     print(r["title"], r["snippet"])
    """
    retriever = ContentRetriever()
    return await retriever.retrieve(query, max_results=max_results)


# ================================
# 测试代码
# ================================
if __name__ == "__main__":
    import asyncio
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    async def test_retriever():
        """测试检索器"""
        
        # 创建检索器
        retriever = ContentRetriever(
            enable_local=True,
            enable_web=False,  # Web搜索需要配置
            enable_case_db=False
        )
        
        # 执行检索
        query = "盗窃罪量刑标准"
        results = await retriever.retrieve(query, max_results=3)
        
        # 输出结果
        print("=" * 60)
        print(f"检索查询: {query}")
        print("=" * 60)
        
        for i, result in enumerate(results, 1):
            print(f"\n{i}. {result['title']}")
            print(f"   来源: {result['source']}")
            print(f"   摘要: {result['snippet'][:100]}...")
            print(f"   分数: {result['score']}")
        
        if not results:
            print("（未找到结果）")
    
    # 运行测试
    asyncio.run(test_retriever())
