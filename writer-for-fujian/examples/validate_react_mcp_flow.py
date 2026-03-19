#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
本地联调验证：React 写作链路 + MCP 法条检索

目标：
1. 模拟“输入案件材料 + 提示词”
2. 通过 React 工具调用 MCP 的 search_article
3. 输出最终文章，并展示中间步骤和法条引用

运行前提：
- MCP 服务已启动（http://127.0.0.1:8000/sse）
- writer-for-fujian 依赖已安装
"""

import asyncio
from types import SimpleNamespace

from app.integrations.mcp_client import LegalMCPClient
from app.services.writing_service import WritingService, WritingRequest


class ScriptedLLMClient:
    """一个可控的伪 LLM，用于稳定复现 React 流程。"""

    def __init__(self):
        self.call_count = 0

    def chat_completion(self, messages, temperature=0.2, **kwargs):
        self.call_count += 1

        if self.call_count == 1:
            return SimpleNamespace(
                content=(
                    "Thought: 先根据案件材料检索相关法条。\n"
                    "Action: search_legal: 盗窃罪"
                )
            )

        if self.call_count == 2:
            observation_text = ""
            for msg in reversed(messages):
                if getattr(msg, "role", "") == "user" and "Observation:" in getattr(msg, "content", ""):
                    observation_text = msg.content.replace("Observation:", "").strip()
                    break

            final_article = (
                "【案件分析】\n"
                "根据案件材料，行为涉及财产性侵害，核心争点在于盗窃构成与量刑。\n\n"
                "【相关法条检索结果】\n"
                f"{observation_text}\n\n"
                "【初步写作结论】\n"
                "应围绕行为方式、数额、主观故意及从轻从重情节展开论证。"
            )
            return SimpleNamespace(
                content=(
                    "Thought: 已获得法条依据，形成最终输出。\n"
                    f"Action: FINISH: {final_article}"
                )
            )

        return SimpleNamespace(content="Thought: 任务完成。\nAction: FINISH: 完成")


async def main():
    case_material = "申诉人张三，涉嫌盗窃他人财物，涉案金额较大。"
    prompt_instruction = "请依据案件材料，生成简要法律分析并给出法条依据。"

    mcp_client = LegalMCPClient(sse_url="http://127.0.0.1:8000/sse")
    llm_client = ScriptedLLMClient()

    service = WritingService(llm_client=llm_client, mcp_client=mcp_client)

    request = WritingRequest(
        case_material=case_material,
        prompt_instruction=prompt_instruction,
        enable_legal_search=True,
        enable_content_retrieval=False,
        section_mode=False,
        max_react_steps=3,
    )

    response = await service.write(request)

    print("\n" + "=" * 80)
    print("React + MCP 本地联调结果")
    print("=" * 80)
    print(f"success: {response.success}")
    print(f"react_steps: {len(response.react_steps)}")
    print(f"legal_references: {len(response.legal_references)}")
    print("\n--- 输出文章 ---")
    print(response.content)

    print("\n--- React 步骤 ---")
    for step in response.react_steps:
        print(f"Step {step.get('step')}: action={step.get('action')} error={step.get('error')}")

    if not response.success:
        raise SystemExit(1)

    if not response.legal_references:
        print("\n⚠ 未记录法条引用，请检查 MCP 服务和 search_legal 调用。")
        raise SystemExit(2)

    print("\n✅ 联调通过：写作流程已成功调用 MCP 法条搜索并生成输出。")


if __name__ == "__main__":
    asyncio.run(main())
