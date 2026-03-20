#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""手动测试 ReactWritingEngine 关键工具函数。

运行方式：
1) 使用真实 MCP（默认）：
    MCP_SSE_URL=http://localhost:11452/sse python3 writer-for-fujian/tests/manual_test_react_tools.py

2) 使用 fake MCP（离线）：
    python3 writer-for-fujian/tests/manual_test_react_tools.py --fake
"""

import asyncio
import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

# 兼容从仓库根目录或 writer-for-fujian 目录运行脚本。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.integrations.mcp_client import LegalMCPClient
from app.services.react_writing_engine import ReactWritingEngine, WritingConfig, ReactStep


class FakeResponse:
    def __init__(self, content: str):
        self.content = content


class FakeLLMClient:
    def chat_completion_stream(self, messages, temperature=0.2, max_tokens=None):
        yield "Thought: 已完成。\nAction: FINISH: 这是最终报告文本。"

    def chat_completion(self, messages, temperature=0.2, max_tokens=None):
        return FakeResponse("Thought: 已完成。\nAction: FINISH: 这是最终报告文本。")


class FakeMCPClient:
    def __init__(self):
        self.search_calls: List[Dict[str, Any]] = []
        self.get_calls: List[Dict[str, Any]] = []

    async def search_article(
        self,
        text: str,
        page: int | str = 1,
        page_size: int | str = 20,
        sort_by: str = "relevance",
        order: str = "desc",
    ) -> List[Dict[str, Any]]:
        self.search_calls.append(
            {
                "text": text,
                "page": page,
                "page_size": page_size,
                "sort_by": sort_by,
                "order": order,
            }
        )
        return [
            {
                "id": "101",
                "title": "中华人民共和国刑法",
                "section_number": "第264条",
                "content": "盗窃公私财物，数额较大的，处三年以下有期徒刑、拘役或者管制。",
            },
            {
                "id": "102",
                "title": "中华人民共和国刑法",
                "section_number": "第267条",
                "content": "抢夺公私财物，数额较大的，处三年以下有期徒刑、拘役或者管制。",
            },
        ]

    async def get_article(self, number: str, title: str) -> Dict[str, Any]:
        self.get_calls.append({"number": number, "title": title})
        return {
            "id": "103",
            "title": title,
            "section_number": number,
            "content": "以非法占有为目的，采用虚构事实或者隐瞒真相的方法，骗取公私财物。",
        }


def _build_engine(mcp_client: Any) -> ReactWritingEngine:
    llm_client = FakeLLMClient()
    config = WritingConfig(
        enable_legal_search=True,
        proactive_tool_call=True,
        force_final_synthesis=False,
        enforce_task_alignment=False,
        max_legal_results_for_observation=3,
    )
    return ReactWritingEngine(llm_client=llm_client, mcp_client=mcp_client, config=config)


async def run_fake_tests() -> None:
    mcp_client = FakeMCPClient()
    engine = _build_engine(mcp_client)

    print("[1] 测试 _tool_search_legal")
    obs = await engine._tool_search_legal("盗窃罪 量刑", "案件材料", record_reference=True)
    assert "法条ID:101" in obs, "search_legal 未返回法条ID"
    assert len(engine.legal_references) >= 1, "search_legal 未记录 legal_references"
    print("    通过")

    print("[2] 测试 _tool_get_article")
    obs2 = await engine._tool_get_article("刑法|第266条", "案件材料", record_reference=True)
    assert "法条ID:103" in obs2, "get_article 未返回法条ID"
    assert any(ref.get("law_id") == "103" for ref in engine.legal_references), "get_article 未记录 law_id"
    print("    通过")

    print("[3] 测试 _post_process_legal_citations")
    engine.steps.append(
        ReactStep(
            step_number=1,
            thought="测试",
            action="search_legal",
            action_input="盗窃罪",
            observation="ok",
        )
    )
    text = "本案法律依据为《中华人民共和国刑法》第264条。"
    out = engine._post_process_legal_citations(text)
    assert "[法条ID:" in out, "后处理未补充法条ID角标"
    print("    通过")

    print("[4] 测试 generate 启用MCP会先检索")
    result = await engine.generate(
        task_description="请根据案件材料写一份完整法律分析报告",
        context="被告人涉嫌盗窃，争议焦点为金额认定。"
    )
    assert mcp_client.search_calls, "generate 未触发 proactive MCP 检索"
    assert result.get("content"), "generate 未返回 content"
    print("    通过")

    print("\n所有关键工具函数测试通过。")


async def run_real_tests() -> None:
    sse_url = os.getenv("MCP_SSE_URL", "").strip()
    if not sse_url:
        raise RuntimeError("缺少 MCP_SSE_URL，请先设置后再运行真实MCP测试")

    mcp_client = LegalMCPClient(sse_url=sse_url)
    engine = _build_engine(mcp_client)

    print("[1] 测试 MCP 连通性 list_tools")
    tools = await mcp_client.list_tools()
    assert tools is not None, "list_tools 返回为空对象"
    print(f"    通过，可用工具数量: {len(tools)}")

    print("[2] 测试 _tool_search_legal")
    obs = await engine._tool_search_legal("盗窃罪 量刑", "案件材料", record_reference=True)
    if "未找到相关法条" in obs:
        print("    警告：search_article 本次未命中，继续验证 get_article 与后处理链路")
    else:
        assert len(engine.legal_references) >= 1, "search_legal 未记录 legal_references"
        print("    通过")

    print("[3] 测试 _tool_get_article")
    obs2 = await engine._tool_get_article("刑法|第264条", "案件材料", record_reference=True)
    assert "未找到" not in obs2, "get_article 未命中法条"
    assert any(ref.get("title") for ref in engine.legal_references), "get_article 未写入 legal_references"
    print("    通过")

    print("[4] 测试 _post_process_legal_citations")
    engine.steps.append(
        ReactStep(
            step_number=1,
            thought="测试",
            action="search_legal",
            action_input="盗窃罪",
            observation="ok",
        )
    )
    text = "本案法律依据为《中华人民共和国刑法》第264条。"
    out = engine._post_process_legal_citations(text)
    assert "[法条ID:" in out, "后处理未补充法条ID角标"
    print("    通过")

    print("[5] 测试 generate 启用MCP会先检索并输出报告")
    result = await engine.generate(
        task_description="请根据案件材料写一份完整法律分析报告",
        context="被告人涉嫌盗窃，争议焦点为金额认定。"
    )
    assert result.get("content"), "generate 未返回 content"
    print("    通过")

    print("\n真实MCP关键工具函数测试通过。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="手动测试 ReactWritingEngine 关键工具函数")
    parser.add_argument("--fake", action="store_true", help="使用 fake MCP 客户端离线测试")
    args = parser.parse_args()

    if args.fake:
        asyncio.run(run_fake_tests())
    else:
        asyncio.run(run_real_tests())
