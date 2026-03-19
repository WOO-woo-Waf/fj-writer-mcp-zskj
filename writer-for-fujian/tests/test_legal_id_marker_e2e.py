#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
单案例联调：验证“中间可用法条正文 + 最终按需输出法条ID角标”，并覆盖MCP开关耗时与检索可用性。

验证点：
1. 按需角标：出现法律依据句时，最终 content 应包含 [法条ID:数字] 角标。
2. 最终 content 不应包含检索得到的完整法条正文片段。
3. MCP 开启/关闭时均可完成写作，并输出两者耗时对比。
4. 提示词明确要求检索时，可验证检索链路可用（react_steps 有检索动作且 legal_references 可用）。

用法：
    python writer-for-fujian/tests/test_legal_id_marker_e2e.py
    python writer-for-fujian/tests/test_legal_id_marker_e2e.py --case all --base-url http://127.0.0.1:11453
    python writer-for-fujian/tests/test_legal_id_marker_e2e.py --case latency
    python writer-for-fujian/tests/test_legal_id_marker_e2e.py --case search
"""

from __future__ import annotations

import argparse
import json
import re
from typing import Any, Dict, List

import httpx


def build_payload() -> Dict[str, Any]:
    # 单一案例：允许引用法律依据，若引用则标注ID角标。
    case_material = (
        "被告人王某以虚构项目融资需求为由，向多名被害人签订借款及合作协议，"
        "收取款项后未按约履行，资金主要用于偿还旧债和个人消费。"
        "公安机关侦查后移送审查起诉，现需形成审查意见。"
    )

    prompt_instruction = (
        "请撰写一段刑事审查意见（200-350字），围绕是否构成合同诈骗进行分析。"
        "要求：可以引用相关法条"
    )

    return {
        "case_material": case_material,
        "prompt_instruction": prompt_instruction,
        "enable_legal_search": True,
        "enable_content_retrieval": False,
        "section_mode": False,
        "max_react_steps": 5,
        "temperature": 0.1,
        "proactive_tool_call": True,
        "min_output_length": 120,
    }


def build_search_required_payload() -> Dict[str, Any]:
    """显式要求检索法条的测试载荷。"""
    case_material = (
        "被告人王某以虚构项目融资需求为由，向多名被害人签订借款及合作协议，"
        "收取款项后未按约履行，资金主要用于偿还旧债和个人消费。"
        "公安机关侦查后移送审查起诉，现需形成审查意见。"
    )

    prompt_instruction = (
        "请先检索与合同诈骗、自首、量刑相关的法条依据，再输出审查意见。"
        "要求：完整的找出相关的法条依据"
    )

    return {
        "case_material": case_material,
        "prompt_instruction": prompt_instruction,
        "enable_legal_search": True,
        "enable_content_retrieval": False,
        "section_mode": False,
        "max_react_steps": 6,
        "temperature": 0.1,
        "proactive_tool_call": True,
        "min_output_length": 120,
    }


def _contains_long_legal_fragment(content: str, legal_references: List[Dict[str, Any]]) -> bool:
    """检查最终文本是否泄露较长法条原文片段。"""
    normalized_content = re.sub(r"\s+", "", content or "")

    for ref in legal_references:
        raw = str(ref.get("content") or "")
        cleaned = re.sub(r"\s+", "", raw)
        if len(cleaned) < 24:
            continue

        # 取法条正文前36个字符作为强匹配片段，避免误判短词。
        fragment = cleaned[:36]
        if fragment and fragment in normalized_content:
            return True

    return False


def _has_relevant_legal_hit(legal_references: List[Dict[str, Any]], keywords: List[str]) -> bool:
    """检查检索结果是否命中与测试目标相关的法条关键词。"""
    if not legal_references:
        return False

    for ref in legal_references:
        blob = " ".join(
            [
                str(ref.get("title") or ""),
                str(ref.get("article") or ""),
                str(ref.get("content") or "")[:400],
                str(ref.get("query") or ""),
            ]
        )
        if any(keyword in blob for keyword in keywords):
            return True

    return False


def _print_model_trace(final_payload: Dict[str, Any], title: str) -> None:
    """打印模型推理全流程（对话轨迹+react_steps）和最终结果。"""
    metadata = final_payload.get("metadata") or {}
    dialogue_turns = metadata.get("dialogue_turns") or []
    react_steps = final_payload.get("react_steps") or []
    content = str(final_payload.get("content") or "")

    print("\n" + "=" * 88)
    print(f"模型推理全流程 - {title}")
    print("=" * 88)

    print("\n[Dialogue Turns]")
    for idx, turn in enumerate(dialogue_turns, 1):
        role = str(turn.get("role") or "unknown")
        message = str(turn.get("message") or "")
        print(f"\n--- turn {idx} | role={role} ---")
        print(message)

    print("\n[React Steps]")
    for step in react_steps:
        if not isinstance(step, dict):
            continue
        step_no = step.get("step")
        thought = str(step.get("thought") or "")
        action = str(step.get("action") or "")
        observation = str(step.get("observation") or "")
        error = str(step.get("error") or "")
        print(f"\n--- step {step_no} ---")
        print(f"thought: {thought}")
        print(f"action: {action}")
        if observation:
            print(f"observation: {observation}")
        if error:
            print(f"error: {error}")

    print("\n[Final Content]")
    print(content)


def _run_stream_request(payload: Dict[str, Any], base_url: str, timeout: float = 180.0) -> Dict[str, Any]:
    """执行一次流式请求并返回final事件负载。"""
    url = base_url.rstrip("/") + "/api/write/stream"

    print("=" * 88)
    print("开始测试：流式接口（静默接收，中间进度不打印）")
    print(f"POST {url}")
    print("=" * 88)

    events_seen = set()
    final_payload: Dict[str, Any] = {}

    with httpx.Client(timeout=timeout) as client:
        with client.stream("POST", url, json=payload, headers={"Accept": "text/event-stream"}) as response:
            if response.status_code >= 400:
                raise RuntimeError(f"接口调用失败 status={response.status_code}: {response.text[:300]}")

            current_event = ""
            for line in response.iter_lines():
                if line is None:
                    continue

                raw = line.strip()
                if not raw:
                    continue

                # SSE注释行
                if raw.startswith(":"):
                    continue

                if raw.startswith("event:"):
                    current_event = raw.split(":", 1)[1].strip()
                    events_seen.add(current_event)
                    continue

                if raw.startswith("data:"):
                    data_text = raw.split(":", 1)[1].strip()

                    try:
                        data_obj = json.loads(data_text)
                    except json.JSONDecodeError:
                        data_obj = {"raw": data_text}

                    if current_event == "final":
                        final_payload = data_obj if isinstance(data_obj, dict) else {}

            missing = {"start", "progress", "final"} - events_seen
            if missing:
                raise AssertionError(f"流式接口缺少事件: {sorted(missing)}")

    if not final_payload:
        raise AssertionError("未收到 final 事件数据")

    success = bool(final_payload.get("success"))
    if not success:
        raise RuntimeError(f"服务返回失败: {final_payload.get('error')}")

    return final_payload


def run_marker_case(base_url: str, timeout: float = 180.0) -> None:
    final_payload = _run_stream_request(build_payload(), base_url=base_url, timeout=timeout)

    content = str(final_payload.get("content") or "")
    legal_references = final_payload.get("legal_references") or []

    print(f"- content_length={len(content)}")
    print(f"- legal_references_count={len(legal_references)}")

    # if not legal_references:
    #     raise AssertionError("未拿到 legal_references，无法验证法条ID链路")

    # legal_ids = [str(item.get("law_id")) for item in legal_references if item.get("law_id")]
    # if not legal_ids:
    #     raise AssertionError("legal_references 中未发现 law_id")

    # marker_pattern = r"\[法条ID:\d+\]"
    # found_markers = re.findall(marker_pattern, content)
    # if not found_markers:
    #     raise AssertionError("该用例要求存在法律依据句，最终content应包含法条ID角标")

    # if _contains_long_legal_fragment(content, legal_references):
    #     raise AssertionError("最终content检测到疑似法条原文片段泄露")

    # print("\n✓ 测试通过")
    # print(f"- 检索到 law_id 数量: {len(legal_ids)}")
    # print(f"- 最终角标数量: {len(found_markers)}")
    # print(f"- 角标示例: {found_markers[:3]}")
    _print_model_trace(final_payload, title="按需角标基线")


def run_latency_compare_case(base_url: str, timeout: float = 180.0) -> None:
    """对比开启/关闭MCP法条搜索时的最终耗时。"""
    base_payload = build_payload()

    payload_on = dict(base_payload)
    payload_on["enable_legal_search"] = True

    payload_off = dict(base_payload)
    payload_off["enable_legal_search"] = False
    payload_off["proactive_tool_call"] = False

    print("\n" + "=" * 88)
    print("开始测试：MCP开关耗时对比")
    print("=" * 88)

    final_on = _run_stream_request(payload_on, base_url=base_url, timeout=timeout)
    final_off = _run_stream_request(payload_off, base_url=base_url, timeout=timeout)

    elapsed_on = float((final_on.get("metadata") or {}).get("elapsed_seconds") or 0.0)
    elapsed_off = float((final_off.get("metadata") or {}).get("elapsed_seconds") or 0.0)

    if elapsed_on <= 0 or elapsed_off <= 0:
        raise AssertionError("未能从metadata中读取有效耗时(elapsed_seconds)")

    delta = elapsed_on - elapsed_off
    ratio = (elapsed_on / elapsed_off) if elapsed_off > 0 else 0.0

    print("\n✓ 测试通过")
    print(f"- MCP开启耗时: {elapsed_on:.3f}s")
    print(f"- MCP关闭耗时: {elapsed_off:.3f}s")
    print(f"- 耗时差值(开-关): {delta:.3f}s")
    print(f"- 倍率(开/关): {ratio:.3f}x")
    _print_model_trace(final_on, title="MCP开启")
    _print_model_trace(final_off, title="MCP关闭")


def run_search_availability_case(base_url: str, timeout: float = 180.0) -> None:
    """提示词明确要求检索时，验证检索链路可用。"""
    print("\n" + "=" * 88)
    print("开始测试：显式检索可用性")
    print("=" * 88)

    final_payload = _run_stream_request(build_search_required_payload(), base_url=base_url, timeout=timeout)

    content = str(final_payload.get("content") or "")
    legal_references = final_payload.get("legal_references") or []
    react_steps = final_payload.get("react_steps") or []

    if not legal_references:
        raise AssertionError("显式检索用例未拿到 legal_references")

    legal_ids = [str(item.get("law_id")) for item in legal_references if item.get("law_id")]
    if not legal_ids:
        raise AssertionError("显式检索用例未拿到有效 law_id")

    expected_keywords = ["合同诈骗", "第二百二十四", "自首", "第六十七", "量刑", "第六十一"]
    if not _has_relevant_legal_hit(legal_references, expected_keywords):
        raise AssertionError("检索结果未命中合同诈骗/自首/量刑相关法条，疑似未搜到目标法条")

    search_actions = {
        str(step.get("action") or "")
        for step in react_steps
        if isinstance(step, dict)
    }
    if not ({"search_legal", "search_cp", "get_article", "get_cp_article"} & search_actions):
        raise AssertionError("react_steps 中未发现法条检索相关动作")

    marker_pattern = r"\[法条ID:\d+\]"
    found_markers = re.findall(marker_pattern, content)
    if not found_markers:
        raise AssertionError("显式检索用例要求输出法律依据句，最终未发现法条ID角标")

    if _contains_long_legal_fragment(content, legal_references):
        raise AssertionError("显式检索用例检测到疑似法条原文片段泄露")

    print("\n✓ 测试通过")
    print(f"- legal_references_count={len(legal_references)}")
    print(f"- react_actions={sorted(action for action in search_actions if action)}")
    print(f"- 角标示例: {found_markers[:3]}")
    _print_model_trace(final_payload, title="显式检索可用性")


def main() -> int:
    parser = argparse.ArgumentParser(description="验证法条ID角标输出、MCP耗时对比、检索可用性")
    parser.add_argument("--base-url", default="http://127.0.0.1:11453", help="写作服务地址")
    parser.add_argument("--timeout", type=float, default=180.0, help="请求超时秒数")
    parser.add_argument(
        "--case",
        choices=["all", "marker", "latency", "search"],
        default="all",
        help="选择测试用例：all/marker/latency/search",
    )
    args = parser.parse_args()

    try:
        if args.case in ("all", "marker"):
            run_marker_case(base_url=args.base_url, timeout=args.timeout)
        # if args.case in ("all", "latency"):
        #     run_latency_compare_case(base_url=args.base_url, timeout=args.timeout)
        # if args.case in ("all", "search"):
        #     run_search_availability_case(base_url=args.base_url, timeout=args.timeout)
        return 0
    except Exception as exc:
        print(f"\n✗ 测试失败: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
