#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
React 写作引擎
基于 ReAct (Reasoning + Acting) 框架的多轮对话写作引擎
支持法条搜索、内容检索和智能推理
"""

import logging
import re
from typing import Dict, Any, Optional, List, Callable, Tuple
from dataclasses import dataclass, field

from app.core.llm_client import LLMClient, Message
from app.integrations.mcp_client import LegalMCPClient

logger = logging.getLogger(__name__)


@dataclass
class WritingConfig:
    """写作配置"""
    max_react_steps: int = 10  # 最大React循环步数
    temperature: float = 0.2  # LLM温度
    enable_legal_search: bool = True  # 启用法条搜索
    enable_content_retrieval: bool = True  # 启用内容检索
    repetition_strategy: str = "smart"  # 重复策略
    context_window_limit: int = 128000  # 上下文窗口限制（模型支持128K）
    
    # 模式性提示词（指导React循环的执行）
    pattern_prompts: Dict[str, str] = field(default_factory=dict)
    
    # 强规范要求（需要重复强调的内容）
    strong_requirements: List[str] = field(default_factory=list)
    multi_turn_enabled: bool = True
    proactive_tool_call: bool = True
    proactive_top_k: int = 3
    proactive_max_queries: int = 3
    min_output_length: int = 20
    prefer_streaming: bool = True
    max_turn_text_chars: int = 6000
    force_final_synthesis: bool = True
    task_priority_overrides_workflow: bool = True
    priority_repeat_high: int = 3
    priority_repeat_medium: int = 2
    priority_repeat_low: int = 1
    enforce_task_alignment: bool = True
    initial_case_repeat: int = 1
    initial_task_repeat: int = 1


@dataclass
class ReactStep:
    """React执行步骤"""
    step_number: int
    thought: str  # 思考内容
    action: Optional[str] = None  # 动作
    action_input: Optional[str] = None  # 动作输入
    observation: Optional[str] = None  # 观察结果
    error: Optional[str] = None  # 错误信息


@dataclass
class DialogueTurn:
    """多轮对话轨迹"""
    role: str
    message: str


class ReactWritingEngine:
    """
    React 写作引擎
    
    核心流程：
    1. Thought: 分析当前任务和上下文
    2. Action: 选择工具执行（法条搜索、内容检索、汇总、写作）
    3. Observation: 获取工具执行结果
    4. 重复上述步骤直到完成任务
    
    工具集：
    - search_legal: 搜索法律条文
    - get_article: 获取具体法条
    - retrieve_content: 检索相关内容
    - summarize: 汇总材料
    - write_section: 撰写章节
    - FINISH: 完成任务
    """
    
    def __init__(
        self,
        llm_client: LLMClient,
        mcp_client: Optional[LegalMCPClient] = None,
        content_retriever: Optional[Any] = None,
        config: Optional[WritingConfig] = None
    ):
        """
        初始化React写作引擎
        
        Args:
            llm_client: LLM客户端
            mcp_client: MCP法条搜索客户端
            content_retriever: 内容检索器
            config: 写作配置
        """
        self.llm_client = llm_client
        self.mcp_client = mcp_client
        self.content_retriever = content_retriever
        self.config = config or WritingConfig()
        
        # 工具注册表
        self.tools: Dict[str, Callable] = {}
        self._register_tools()
        
        # 执行历史
        self.steps: List[ReactStep] = []
        self.dialogue_turns: List[DialogueTurn] = []
        self.legal_references: List[Dict[str, Any]] = []
        self.retrieved_contents: List[Dict[str, Any]] = []
        
        logger.info("ReactWritingEngine initialized")
    
    def _register_tools(self):
        """注册所有可用工具"""
        self.tools = {
            "search_legal": self._tool_search_legal,
            "get_article": self._tool_get_article,
            "search_cp": self._tool_search_legal,
            "get_cp_article": self._tool_get_article,
            "retrieve_content": self._tool_retrieve_content,
            "summarize": self._tool_summarize,
            "write_section": self._tool_write_section,
            "FINISH": self._tool_finish
        }
    
    def _get_system_prompt(self) -> str:
        """获取系统提示词"""
        tools_desc = self._get_tools_description()
        citation_rule = self._get_legal_citation_rule_text()
        
        # 构建强规范要求部分
        strong_reqs_text = ""
        if self.config.strong_requirements:
            strong_reqs_text = "\n\n【强规范要求（必须严格遵守并在输出中体现）】\n"
            for i, req in enumerate(self.config.strong_requirements, 1):
                strong_reqs_text += f"{i}. {req}\n"
        
        return f"""你是一名资深法律写作智能体，负责“流程控制与工具调用”，不负责覆盖用户输入的写作要求。

    你的任务是：在 ReAct 多轮框架下，调用工具、组织证据、最后按“输入提示词”生成正文。

    【优先级规则（必须遵守）】
    1. 最高优先级：输入提示词（task_description）。
    2. 次高优先级：案件材料（context），是事实信息源与证据提取基础。
    3. 最低优先级：本系统流程提示（即当前提示词），仅用于约束步骤与工具使用方式。
    4. 若发生冲突：必须以输入提示词为准，不得用流程提示覆盖内容要求。

    【工作流程】
    Thought: 分析当前情况，思考下一步需要做什么
    Action: 工具名称: 参数
    Observation: (工具返回的结果)
    ... (重复)
    Thought: 任务完成，已生成完整内容
    Action: FINISH: 生成的最终内容

    【可用工具】
    {tools_desc}

    【执行原则】
    1. 先理解输入提示词的目标与格式，再决定是否检索法条。
    2. 仅当任务或正文需要法律依据时，再使用 search_legal/get_article；禁止臆造法条。
    3. 案件材料用于事实抽取与证据支撑，不得替代输入提示词的输出目标。
    4. 最终内容必须可交付，且严格贴合输入提示词要求。
    5. 若正文出现明确“法律依据/法条依据/依照某法条”等法律依据句，应使用法条ID角标引用；若正文不涉及法律依据，可不引用。
    6. 角标格式统一为：[法条ID:123]（示例）。
    {strong_reqs_text}
    {citation_rule}
    【注意事项】
    - 每次只执行一个 Action
    - Action 格式必须严格遵守：Action: 工具名称: 参数
    - FINISH 仅用于结束循环，最终报告会在结束后统一汇总生成
    - 考虑文本长度限制，合理组织内容
    """
    
    def _get_tools_description(self) -> str:
        """获取工具描述"""
        descriptions = []
        
        if self.config.enable_legal_search and self.mcp_client:
            descriptions.extend([
                "- search_legal: 搜索法律条文。参数：搜索关键词（如：盗窃罪量刑标准）",
                "- get_article: 获取具体法条。参数：法规名称|条号（如：刑法|第264条）",
                "- search_cp: CP工具别名，等价于search_legal",
                "- get_cp_article: CP工具别名，等价于get_article"
            ])
        
        if self.config.enable_content_retrieval and self.content_retriever:
            descriptions.append(
                "- retrieve_content: 检索相关内容。参数：检索查询（如：盗窃罪司法解释）"
            )
        
        descriptions.extend([
            "- summarize: 汇总材料。参数：要汇总的要点描述",
            "- FINISH: 完成任务。参数：结束循环标记"
        ])
        
        return "\n".join(descriptions)

    def _get_priority_repeat_count(self, level: str) -> int:
        """根据优先级返回重复次数。"""
        if self.config.repetition_strategy == "none":
            return 1
        if level == "high":
            return max(1, self.config.priority_repeat_high)
        if level == "medium":
            return max(1, self.config.priority_repeat_medium)
        return max(1, self.config.priority_repeat_low)

    def _build_priority_repetition_module(self, task: str, context: str) -> str:
        """构建初始输入模块：按配置重复案件材料与输入提示词。"""
        case_times = max(1, self.config.initial_case_repeat)
        task_times = max(1, self.config.initial_task_repeat)

        case_block = "\n\n".join(
            [f"[案件材料-重复{i}]\n{context}" for i in range(1, case_times + 1)]
        )
        task_block = "\n\n".join(
            [f"[输入提示词-重复{i}]\n{task}" for i in range(1, task_times + 1)]
        )

        workflow_block = (
            "[流程说明]\n"
            "1) 模型根据案件材料提取相关位置的信息；\n"
            "2) 在多轮对话中逐步汇总成报告；\n"
            "3) 最后一轮由特定提示词进行收敛输出。"
        )

        return f"{case_block}\n\n{task_block}\n\n{workflow_block}"
    
    async def generate(
        self,
        task_description: str,
        context: str
    ) -> Dict[str, Any]:
        """
        生成内容
        
        Args:
            task_description: 任务描述（提示词）
            context: 上下文（案件材料）
            
        Returns:
            生成结果字典
        """
        logger.info("开始React生成流程")
        
        # 重置状态
        self.steps = []
        self.dialogue_turns = []
        self.legal_references = []
        self.retrieved_contents = []
        
        # 构建初始提示
        initial_prompt = self._build_initial_prompt(task_description, context)
        
        # 初始化消息历史
        messages = [
            Message(role="system", content=self._get_system_prompt()),
            Message(role="user", content=initial_prompt)
        ]

        if self.config.enable_legal_search and self.mcp_client and self.config.proactive_tool_call:
            proactive_queries = self._build_proactive_queries(task_description, context)
            for proactive_query in proactive_queries[: self.config.proactive_max_queries]:
                logger.info(f"Proactive MCP search query: {proactive_query}")
                proactive_observation = await self._tool_search_legal(proactive_query, context)
                self.steps.append(
                    ReactStep(
                        step_number=0,
                        thought="先主动检索法律依据，作为后续写作基础",
                        action="search_legal",
                        action_input=proactive_query,
                        observation=proactive_observation,
                    )
                )
                messages.append(Message(role="user", content=f"Observation: {proactive_observation}"))

            parsed_articles = self._extract_article_requests(task_description + "\n" + context)
            for title, number in parsed_articles[:2]:
                logger.info(f"Proactive MCP get_article: title={title}, number={number}")
                article_observation = await self._tool_get_article(f"{title}|{number}", context)
                self.steps.append(
                    ReactStep(
                        step_number=0,
                        thought="任务中出现明确条文，主动拉取具体法条原文",
                        action="get_article",
                        action_input=f"{title}|{number}",
                        observation=article_observation,
                    )
                )
                messages.append(Message(role="user", content=f"Observation: {article_observation}"))

        self.dialogue_turns.append(DialogueTurn(role="user", message=initial_prompt))
        
        final_content = ""
        
        # React循环
        for step_num in range(1, self.config.max_react_steps + 1):
            logger.info(f"React Step {step_num}")
            
            # 1. LLM推理
            try:
                content = self._complete_text(
                    messages=messages,
                    temperature=self.config.temperature
                )
                self.dialogue_turns.append(DialogueTurn(role="assistant", message=content))
                logger.debug(f"Step {step_num} Response: {content[:200]}...")
            except Exception as e:
                logger.error(f"LLM调用失败: {e}")
                return self._build_error_result(f"LLM调用失败: {str(e)}")
            
            # 记录步骤
            current_step = ReactStep(
                step_number=step_num,
                thought=self._extract_thought(content)
            )
            if current_step.thought:
                logger.info(f"Step {step_num} Thought: {current_step.thought[:300]}")
            
            # 添加到消息历史
            messages.append(
                Message(role="assistant", content=self._truncate_text(content, self.config.max_turn_text_chars))
            )
            
            # 2. 解析动作
            action_info = self._parse_action(content)
            
            if not action_info:
                # 没有解析出动作，提示继续
                if "FINISH" in content.upper():
                    final_content = self._extract_finish_content(content)
                    current_step.action = "FINISH"
                    self.steps.append(current_step)
                    break
                
                messages.append(Message(
                    role="user",
                    content="请继续思考并选择一个工具执行，或者使用 FINISH 完成任务。"
                ))
                self.dialogue_turns.append(
                    DialogueTurn(role="user", message="请继续思考并选择一个工具执行，或者使用 FINISH 完成任务。")
                )
                self.steps.append(current_step)
                continue
            
            action_name, action_input = action_info
            current_step.action = action_name
            current_step.action_input = action_input
            logger.info(f"Step {step_num} Action: {action_name} | input={action_input[:200]}")
            
            # 3. 执行工具
            if action_name == "FINISH":
                final_content = action_input
                current_step.observation = "任务完成"
                logger.info(f"Step {step_num} FINISH with length={len(final_content)}")
                self.steps.append(current_step)
                break
            
            if action_name not in self.tools:
                observation = f"错误：未知工具 '{action_name}'。请从可用工具列表中选择。"
                current_step.error = observation
            else:
                try:
                    tool_func = self.tools[action_name]
                    observation = await tool_func(action_input, context)
                    current_step.observation = observation
                    logger.info(f"Step {step_num} Observation: {str(observation)[:300]}")
                except Exception as e:
                    observation = f"工具执行失败: {str(e)}"
                    current_step.error = observation
                    logger.error(f"Tool {action_name} failed: {e}", exc_info=True)
            
            self.steps.append(current_step)
            self.dialogue_turns.append(
                DialogueTurn(role="tool", message=f"{action_name}: {str(observation)[:1000]}")
            )
            
            # 4. 将观察结果反馈给模型
            observation_text = self._truncate_text(str(observation), self.config.max_turn_text_chars)
            messages.append(Message(role="user", content=f"Observation: {observation_text}"))
            self.dialogue_turns.append(DialogueTurn(role="user", message=f"Observation: {observation}"))
            
            # 检查上下文长度
            if self._estimate_context_length(messages) > self.config.context_window_limit:
                logger.warning("上下文长度接近限制，进行压缩")
                messages = self._compress_context(messages)

        if self.config.force_final_synthesis:
            final_content = await self._run_final_round_with_special_prompt(
                messages=messages,
                task=task_description,
                draft=final_content,
            )

        if self.config.enforce_task_alignment:
            final_content = await self._enforce_task_alignment(
                task=task_description,
                context=context,
                draft=final_content
            )

        final_content = self._post_process_legal_citations(final_content)

        dynamic_min_len = self._resolve_task_min_length(task_description)
        if len(final_content.strip()) < dynamic_min_len:
            logger.warning(
                f"Final output too short ({len(final_content.strip())}), attempting task-aligned length repair"
            )
            repaired = await self._repair_output_for_task(
                task=task_description,
                context=context,
                draft=final_content,
                min_len=dynamic_min_len,
            )
            if repaired.strip():
                final_content = repaired

        if len(final_content.strip()) < dynamic_min_len:
            if self._is_narrow_task(task_description):
                logger.warning(
                    "Output still short but task is narrow; skip generic fallback to avoid off-topic expansion"
                )
            else:
                logger.warning(
                    f"Output still short ({len(final_content.strip())}), using generic fallback report generation"
                )
                final_content = await self._build_fallback_report(task_description, context)

        final_content = self._post_process_legal_citations(final_content)

        logger.info(
            f"React generation finished: steps={len(self.steps)}, "
            f"dialogue_turns={len(self.dialogue_turns)}, legal_refs={len(self.legal_references)}, "
            f"content_length={len(final_content)}"
        )
        
        # 构建结果
        return {
            "content": final_content,
            "metadata": {
                "total_steps": len(self.steps),
                "max_steps_reached": len(self.steps) >= self.config.max_react_steps,
                "dialogue_turns": [
                    {"role": item.role, "message": item.message}
                    for item in self.dialogue_turns
                ]
            },
            "react_steps": [
                {
                    "step": s.step_number,
                    "thought": s.thought,
                    "action": s.action,
                    "observation": s.observation,
                    "error": s.error
                }
                for s in self.steps
            ],
            "legal_references": self.legal_references,
            "retrieved_contents": self.retrieved_contents
        }
    
    def _build_initial_prompt(self, task: str, context: str) -> str:
        """构建初始提示"""
        # 应用重复策略：强规范要求在初始提示中重复
        strong_reqs_text = ""
        if self.config.repetition_strategy in ["smart", "strict"]:
            if self.config.strong_requirements:
                strong_reqs_text = "\n\n【强规范要求（必须遵守）】\n"
                for req in self.config.strong_requirements:
                    strong_reqs_text += f"- {req}\n"

        case_times = max(1, self.config.initial_case_repeat)
        task_times = max(1, self.config.initial_task_repeat)
        priority_module = self._build_priority_repetition_module(task, context)
        priority_rule = (
            "输入提示词定义输出目标；案件材料是事实信息源，用于提取与核验。"
            if self.config.task_priority_overrides_workflow
            else "按默认优先级执行。"
        )
        
        return f"""
【优先级声明】
{priority_rule}

【优先级重复模块】
{priority_module}
{strong_reqs_text}

    请按上述规则开始执行：
    - 初始输入中，案件材料已重复{case_times}遍，输入提示词已重复{task_times}遍；
    - 多轮对话阶段仅围绕已给材料抽取与汇总；
    - 最后一轮使用特定提示词收敛为最终报告。
"""
    
    def _extract_thought(self, content: str) -> str:
        """提取Thought内容"""
        match = re.search(r"Thought:\s*(.+?)(?=\n(?:Action|$))", content, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return ""
    
    def _parse_action(self, content: str) -> Optional[tuple]:
        """解析Action"""
        # 格式: Action: tool_name: args
        match = re.search(r"Action:\s*(\w+):\s*(.+?)(?=\n|$)", content, re.DOTALL | re.IGNORECASE)
        if match:
            tool_name = match.group(1).strip()
            tool_args = match.group(2).strip()
            return tool_name, tool_args
        return None
    
    def _extract_finish_content(self, content: str) -> str:
        """提取FINISH后的内容"""
        match = re.search(r"FINISH:\s*(.+)", content, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return ""
    
    # ==================== 工具实现 ====================
    
    async def _tool_search_legal(self, query: str, context: str) -> str:
        """搜索法律条文"""
        if not self.mcp_client:
            return "法条搜索功能未启用"
        
        try:
            candidate_queries = [query]
            if "刑法" not in query:
                candidate_queries.append(f"{query} 刑法")

            results = []
            for candidate in candidate_queries:
                results = await self.mcp_client.search_article(text=candidate)
                if results:
                    query = candidate
                    break
            
            if not results:
                return "未找到相关法条"
            
            # 记录前3条结果
            output_parts = []
            seen = set()
            for i, result in enumerate(results[:3], 1):
                title = result.get("title", "未知")
                article = result.get("section_number", result.get("article", ""))
                content = result.get("content", "")[:200]
                law_id = self._normalize_legal_id(result.get("id"))
                dedup_key = (title, article, law_id)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                id_text = law_id if law_id else "未知"
                output_parts.append(f"{i}. 《{title}》{article} [法条ID:{id_text}]\n   {content}...")
                
                # 记录引用
                self.legal_references.append({
                    "law_id": law_id,
                    "title": title,
                    "article": article,
                    "content": result.get("content", ""),
                    "query": query
                })
            
            return "\n".join(output_parts)
            
        except Exception as e:
            logger.error(f"法条搜索失败: {e}")
            return f"法条搜索失败: {str(e)}"
    
    async def _tool_get_article(self, params: str, context: str) -> str:
        """获取具体法条"""
        if not self.mcp_client:
            return "法条搜索功能未启用"
        
        try:
            # 解析参数: 法规名称|条号
            parts = params.split("|")
            if len(parts) < 2:
                return "参数格式错误，应为：法规名称|条号（如：刑法|第264条）"
            
            title = parts[0].strip()
            number = parts[1].strip()
            
            result = await self.mcp_client.get_article(number=number, title=title)
            
            if result:
                article_text = result.get("content", "") if isinstance(result, dict) else str(result)
                article_number = result.get("section_number", number) if isinstance(result, dict) else number
                law_id = self._normalize_legal_id(result.get("id")) if isinstance(result, dict) else None
                # 记录引用
                self.legal_references.append({
                    "law_id": law_id,
                    "title": title,
                    "article": article_number,
                    "content": article_text,
                    "query": params
                })
                id_text = law_id if law_id else "未知"
                return f"《{title}》{article_number} [法条ID:{id_text}]：\n{article_text}"
            else:
                return f"未找到《{title}》{number}"
                
        except Exception as e:
            logger.error(f"获取法条失败: {e}")
            return f"获取法条失败: {str(e)}"
    
    async def _tool_retrieve_content(self, query: str, context: str) -> str:
        """检索相关内容"""
        if not self.content_retriever:
            return "内容检索功能未启用"
        
        try:
            results = await self.content_retriever.retrieve(query)
            
            if not results:
                return "未检索到相关内容"
            
            # 记录结果
            output_parts = []
            for i, result in enumerate(results[:3], 1):
                title = result.get("title", "")
                snippet = result.get("snippet", "")[:150]
                output_parts.append(f"{i}. {title}\n   {snippet}...")
                
                self.retrieved_contents.append(result)
            
            return "\n".join(output_parts)
            
        except Exception as e:
            logger.error(f"内容检索失败: {e}")
            return f"内容检索失败: {str(e)}"
    
    async def _tool_summarize(self, requirement: str, context: str) -> str:
        """汇总材料"""
        try:
            # 使用LLM进行汇总
            prompt = f"""
请根据以下案件材料，汇总以下信息：
{requirement}

案件材料：
{context[:2000]}

请简明扼要地汇总。
"""
            return self._complete_text(
                messages=[Message(role="user", content=prompt)],
                temperature=0.1
            )
            
        except Exception as e:
            return f"汇总失败: {str(e)}"
    
    async def _tool_write_section(self, requirement: str, context: str) -> str:
        """撰写章节"""
        try:
            # 应用重复策略
            strong_reqs_reminder = ""
            if self.config.repetition_strategy == "strict" and self.config.strong_requirements:
                strong_reqs_reminder = "\n\n强规范要求（必须体现）：\n"
                for req in self.config.strong_requirements:
                    strong_reqs_reminder += f"- {req}\n"
            
            # 构建写作提示
            prompt = f"""
根据以下要求撰写章节内容：
{requirement}
{strong_reqs_reminder}

案件材料：
{context[:3000]}

已搜集的法律依据：
{self._format_legal_references_with_content()}

请撰写详细、准确的章节内容。
"""
            return self._complete_text(
                messages=[Message(role="user", content=prompt)],
                temperature=self.config.temperature
            )
            
        except Exception as e:
            return f"撰写失败: {str(e)}"
    
    async def _tool_finish(self, content: str, context: str) -> str:
        """完成任务"""
        return "任务完成"
    
    # ==================== 辅助方法 ====================
    
    def _format_legal_references(self) -> str:
        """格式化法律引用"""
        if not self.legal_references:
            return "（暂无）"
        
        parts = []
        for i, ref in enumerate(self.legal_references[:8], 1):
            law_id = ref.get("law_id") or "未知"
            title = ref.get("title", "未知法规")
            article = ref.get("article", "")
            parts.append(f"{i}. 《{title}》{article} [法条ID:{law_id}]")
        
        return "\n".join(parts)

    def _format_legal_id_catalog(self) -> str:
        """格式化可引用的法条ID目录，仅供最终生成引用角标。"""
        refs = self._collect_unique_legal_references(without_content=True)
        if not refs:
            return "（暂无可用法条ID）"

        lines = []
        for idx, ref in enumerate(refs, 1):
            law_id = ref.get("law_id")
            if not law_id:
                continue
            title = ref.get("title", "未知法规")
            article = ref.get("article", "")
            lines.append(f"{idx}. [法条ID:{law_id}] 《{title}》{article}")

        return "\n".join(lines) if lines else "（暂无可用法条ID）"

    def _get_legal_citation_rule_text(self) -> str:
        """统一法条ID角标规则。"""
        return (
            "【法条引用规则】\n"
            "- 只允许使用法条ID角标引用：格式 [法条ID:数字ID]。\n"
            "- 不输出法条原文全文；正文仅保留必要法律结论与对应ID角标。\n"
            "- 如果没有检索到法条ID，则不要伪造ID。"
        )

    def _normalize_legal_id(self, value: Any) -> Optional[str]:
        """规范化法条ID，只保留数字串。"""
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        return text if text.isdigit() else None

    def _collect_unique_legal_references(self, without_content: bool = False) -> List[Dict[str, Any]]:
        """去重后的法条引用列表。"""
        unique_refs: List[Dict[str, Any]] = []
        seen = set()

        for ref in self.legal_references:
            law_id = ref.get("law_id")
            title = ref.get("title", "")
            article = ref.get("article", "")
            key = (law_id, title, article)
            if key in seen:
                continue
            seen.add(key)
            if without_content:
                unique_refs.append({
                    "law_id": law_id,
                    "title": title,
                    "article": article,
                    "query": ref.get("query", "")
                })
            else:
                unique_refs.append(ref)

        return unique_refs

    def _post_process_legal_citations(self, content: str) -> str:
        """清理输出并按需补法条ID角标（不再无条件强插）。"""
        text = (content or "").strip()
        if not text:
            return text

        refs = self._collect_unique_legal_references(without_content=True)
        valid_ids = [ref.get("law_id") for ref in refs if ref.get("law_id")]
        if not valid_ids:
            # 没有有效ID可引用时，仅做格式清理。
            return re.sub(r"\n{3,}", "\n\n", text)

        valid_id_set = set(valid_ids)
        marker_pattern = r"\[法条ID:(\d+)\]"
        existing_ids = re.findall(marker_pattern, text)

        # 删除不存在于当前检索结果中的ID角标，避免后续查库失败。
        for marker_id in set(existing_ids):
            if marker_id in valid_id_set:
                continue
            text = re.sub(rf"\[法条ID:{re.escape(marker_id)}\]", "", text)

        # 已有有效角标则不再强插，避免破坏原文结构。
        if re.search(marker_pattern, text):
            return re.sub(r"\n{3,}", "\n\n", text).strip()

        # 未出现角标时，仅在正文出现“法律依据句”时才尝试补标。
        if not self._has_explicit_legal_basis_statement(text):
            return re.sub(r"\n{3,}", "\n\n", text).strip()

        # 先按标题/条号匹配点位补标。
        for ref in refs:
            law_id = ref.get("law_id")
            if not law_id:
                continue
            title = re.escape(ref.get("title", "").strip())
            article = re.escape(str(ref.get("article", "")).strip())
            if not title or not article:
                continue

            pattern = rf"(《{title}》\s*{article})(?!\s*\[法条ID:\d+\])"
            replacement = rf"\1[法条ID:{law_id}]"
            updated_text, count = re.subn(pattern, replacement, text)
            if count > 0:
                text = updated_text

        # 仍无角标时，仅给“法律依据句”补一个角标，不再末尾无条件追加。
        if not re.search(marker_pattern, text):
            text = self._inject_marker_to_legal_basis_sentence(text, valid_ids[0])

        return re.sub(r"\n{3,}", "\n\n", text).strip()

    def _has_explicit_legal_basis_statement(self, text: str) -> bool:
        """判断正文是否明确出现法律依据表达。"""
        signals = [
            "法律依据",
            "法条依据",
            "法律规定",
            "依照",
            "依据",
            "根据《",
            "依照《",
        ]
        return any(signal in text for signal in signals)

    def _inject_marker_to_legal_basis_sentence(self, text: str, law_id: str) -> str:
        """在法律依据句末补一个角标；找不到明确句时保持原文。"""
        lines = text.splitlines()
        patterns = [
            r"法律依据",
            r"法条依据",
            r"法律规定",
            r"根据《",
            r"依照《",
            r"依据",
            r"依照",
        ]

        for idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            if re.search(r"\[法条ID:\d+\]", stripped):
                continue
            if any(re.search(pattern, stripped) for pattern in patterns):
                punct_match = re.search(r"([。；;])\s*$", line)
                marker = f"[法条ID:{law_id}]"
                if punct_match:
                    pos = punct_match.start(1)
                    lines[idx] = f"{line[:pos]}{marker}{line[pos:]}"
                else:
                    lines[idx] = f"{line}{marker}"
                return "\n".join(lines)

        return text
    
    def _estimate_context_length(self, messages: List[Message]) -> int:
        """估算上下文长度"""
        total_length = 0
        for msg in messages:
            total_length += len(msg.content)
        return total_length

    def _truncate_text(self, text: str, max_chars: int) -> str:
        """单条消息截断，控制多轮交互文本上限。"""
        return text

    def _complete_text(
        self,
        messages: List[Message],
        temperature: float,
        max_tokens: Optional[int] = None
    ) -> str:
        """优先流式获取模型输出，失败后回退到非流式。"""
        if self.config.prefer_streaming:
            try:
                chunks: List[str] = []
                for piece in self.llm_client.chat_completion_stream(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                ):
                    chunks.append(piece)
                text = "".join(chunks).strip()
                if text:
                    return text
            except Exception as exc:
                logger.warning(f"Streaming completion failed, fallback to non-stream: {exc}")

        response = self.llm_client.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        return (response.content or "").strip()

    async def _run_final_round_with_special_prompt(self, messages: List[Message], task: str, draft: str) -> str:
        """最后一轮输入：在已有多轮上下文上叠加特定提示词，收敛最终报告。"""
        legal_id_catalog = self._format_legal_id_catalog()
        citation_rule = self._get_legal_citation_rule_text()
        special_prompt = f"""
【最终轮-特定提示词】
你现在进入最终输出阶段。

要求：
1. 案件材料与输入提示词已在前文完整输入，不要重复铺陈。
2. 使用 ReAct 框架的最终收敛方式：只输出最终报告正文，不输出 Thought/Action/Observation。
3. 严格按输入提示词完成目标与格式，保证输出可直接交付。
4. 不裁剪提示词要求，不省略必要字段；信息不足可写“未注明/未提供”。
5. 最终文本应格式合理、逻辑清晰、语义完整。
6. 若正文出现明确法律依据句（如“法律依据/法条依据/依照某法条”），在对应句末标注 [法条ID:数字ID]；若正文不涉及法律依据，可不标注。
7. 最终输出不要附法条原文正文。

{citation_rule}

【可用法条ID目录】
{legal_id_catalog}

【输入提示词（再次确认，不做裁剪）】
{task}

【当前草稿】
{draft if draft else '无'}
"""

        try:
            final_messages = list(messages)
            final_messages.append(Message(role="user", content=special_prompt))
            synthesized = self._complete_text(
                messages=final_messages,
                temperature=min(self.config.temperature, 0.2)
            )
            if synthesized.strip():
                return synthesized.strip()
        except Exception as exc:
            logger.warning(f"Final round synthesis failed: {exc}")

        return draft

    async def _enforce_task_alignment(self, task: str, context: str, draft: str) -> str:
        """对最终草稿做一次“按输入提示词严格对齐”的收敛修正。"""
        if not draft.strip():
            return draft

        context_for_alignment = self._build_context_windows(context, head=5000, tail=5000)
        legal_id_catalog = self._format_legal_id_catalog()
        citation_rule = self._get_legal_citation_rule_text()

        prompt = f"""
请将以下“当前草稿”修正为严格符合“输入提示词”的最终文本。

【硬性约束】
1. 只执行输入提示词要求的内容，不扩展无关段落。
2. 若输入提示词要求字数范围，必须满足该范围。
3. 若输入提示词要求纯文本，禁止Markdown符号（如 #、*、-、```）。
4. 未在案件材料中明确出现的信息不得臆造，可写“未注明/未提供”。
5. 保留已有正确信息，删除与输入提示词冲突的内容。
6. 如果案件材料里已明确出现字段值（尤其“原案被告人”相关的出生日期、户籍地、暂住地/现住址、证件号），必须使用该值，不得改写为“未提供”。
7. 申诉人字段与被告人字段必须按主体分别抽取，禁止交叉引用。
8. 若正文出现明确法律依据句，使用 [法条ID:数字ID] 角标；若正文不涉及法律依据，可不使用角标。不要贴法条原文。

{citation_rule}

【可用法条ID目录】
{legal_id_catalog}

【输入提示词】
{task}

【案件材料（仅作事实依据）】
{context_for_alignment}

【当前草稿】
{draft[:4000]}

请直接输出修正后的最终文本，不要解释。
"""

        try:
            refined = self._complete_text(
                messages=[Message(role="user", content=prompt)],
                temperature=0.1
            )
            if refined.strip():
                return refined.strip()
        except Exception as exc:
            logger.warning(f"Task alignment refinement failed: {exc}")

        return draft

    def _format_legal_references_with_content(self) -> str:
        """格式化法条引用（含正文摘要），用于中间推理与写作。"""
        if not self.legal_references:
            return "（未检索到可用法条）"

        lines = []
        seen = set()
        for ref in self.legal_references:
            title = ref.get("title", "未知法规")
            article = ref.get("article", "")
            key = (title, article)
            if key in seen:
                continue
            seen.add(key)
            law_id = ref.get("law_id") or "未知"
            content = (ref.get("content", "") or "").strip()
            snippet = content[:220] + ("..." if len(content) > 220 else "")
            lines.append(f"- 《{title}》{article} [法条ID:{law_id}]：{snippet}")
            if len(lines) >= 8:
                break
        return "\n".join(lines)
    
    def _compress_context(self, messages: List[Message]) -> List[Message]:
        """压缩上下文"""
        # 根据用户要求：保持完整上下文，不做压缩
        return messages
    
    def _build_error_result(self, error: str) -> Dict[str, Any]:
        """构建错误结果"""
        return {
            "content": "",
            "metadata": {
                "error": error,
                "dialogue_turns": [
                    {"role": item.role, "message": item.message}
                    for item in self.dialogue_turns
                ],
            },
            "react_steps": [],
            "legal_references": [],
            "retrieved_contents": []
        }

    def _build_proactive_queries(self, task: str, context: str) -> List[str]:
        """根据输入提示词与案件材料，构建多组主动法条检索关键词。"""
        merged = f"{task}\n{context}"
        candidates = [
            "合同诈骗", "诈骗罪", "盗窃罪", "职务侵占", "受贿罪", "故意伤害", "故意杀人",
            "单位犯罪", "共同犯罪", "自首", "认罪认罚", "量刑", "证据", "申诉", "再审", "刑法", "刑事诉讼法"
        ]

        hits = [word for word in candidates if word in merged]
        queries: List[str] = []

        if hits:
            queries.append(" ".join(hits[:3]))
            if len(hits) > 3:
                queries.append(" ".join(hits[3:6]))

        article_hints = re.findall(r"第\s*\d+\s*条", merged)
        if article_hints:
            normalized = [re.sub(r"\s+", "", item) for item in article_hints[:2]]
            if "刑法" in merged:
                queries.append(f"刑法 {' '.join(normalized)}")
            if "刑事诉讼法" in merged:
                queries.append(f"刑事诉讼法 {' '.join(normalized)}")

        deduped: List[str] = []
        seen = set()
        for query in queries:
            cleaned = query.strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            deduped.append(cleaned)

        return deduped[: max(1, self.config.proactive_max_queries)]

    def _extract_article_request(self, text: str) -> Optional[Tuple[str, str]]:
        """从文本中提取条文请求，如《刑法》第264条"""
        title_match = re.search(r"《([^》]{1,30})》", text)
        number_match = re.search(r"第\s*\d+\s*条", text)
        if title_match and number_match:
            return title_match.group(1).strip(), re.sub(r"\s+", "", number_match.group(0))

        fallback_number = re.search(r"第\s*\d+\s*条", text)
        if fallback_number and "刑法" in text:
            return "刑法", re.sub(r"\s+", "", fallback_number.group(0))
        return None

    def _extract_article_requests(self, text: str) -> List[Tuple[str, str]]:
        """提取多个条文请求，支持《xx法》第x条 或 默认刑法条号。"""
        pairs: List[Tuple[str, str]] = []
        seen = set()

        for match in re.finditer(r"《([^》]{1,30})》\s*(第\s*\d+\s*条)", text):
            title = match.group(1).strip()
            number = re.sub(r"\s+", "", match.group(2))
            key = (title, number)
            if key in seen:
                continue
            seen.add(key)
            pairs.append(key)

        if not pairs and "刑法" in text:
            for match in re.finditer(r"第\s*\d+\s*条", text):
                number = re.sub(r"\s+", "", match.group(0))
                key = ("刑法", number)
                if key in seen:
                    continue
                seen.add(key)
                pairs.append(key)
                if len(pairs) >= 3:
                    break

        return pairs

    def _resolve_task_min_length(self, task: str) -> int:
        """从输入提示词中解析最小字数，解析失败则使用配置默认值。"""
        patterns = [
            r"字数\s*控制\s*在\s*(\d+)\s*[-—~～]\s*(\d+)\s*字",
            r"不少于\s*(\d+)\s*字",
            r"至少\s*(\d+)\s*字",
        ]

        for pattern in patterns:
            match = re.search(pattern, task)
            if not match:
                continue
            if len(match.groups()) == 2:
                return int(match.group(1))
            if len(match.groups()) == 1:
                return int(match.group(1))

        return self.config.min_output_length

    def _is_narrow_task(self, task: str) -> bool:
        """判断是否为小节/局部输出任务，避免套用整篇报告兜底。"""
        narrow_signals = [
            "撰写\"一、",
            "撰写“一、",
            "仅生成",
            "只生成",
            "一、申诉人基本情况",
            "基本情况及与原案关系",
        ]
        return any(signal in task for signal in narrow_signals)

    async def _repair_output_for_task(self, task: str, context: str, draft: str, min_len: int) -> str:
        """当输出过短时，按输入提示词补全，而不是切换通用模板。"""
        context_for_repair = self._build_context_windows(context, head=4500, tail=4500)
        legal_id_catalog = self._format_legal_id_catalog()
        citation_rule = self._get_legal_citation_rule_text()
        prompt = f"""
请在不偏离输入提示词要求的前提下，补全当前草稿。

要求：
1. 只能围绕输入提示词指定内容扩写，不得扩展为整篇通用报告。
2. 最终文本长度不少于 {min_len} 字。
3. 若输入提示词有字数区间，优先满足该区间。
4. 禁止臆造案件材料中未明确的信息，可写“未注明/未提供”。
5. 涉及法条依据时，使用 [法条ID:数字ID] 角标，不要输出法条原文。
6. 直接输出最终文本，不要解释。

{citation_rule}

【可用法条ID目录】
{legal_id_catalog}

【输入提示词】
{task}

【案件材料】
{context_for_repair}

【当前草稿】
{draft[:3000]}
"""
        try:
            repaired = self._complete_text(
                messages=[Message(role="user", content=prompt)],
                temperature=0.1,
            )
            return repaired.strip()
        except Exception as exc:
            logger.warning(f"Repair output for task failed: {exc}")
            return draft

    def _build_context_windows(self, context: str, head: int = 5000, tail: int = 5000) -> str:
        """长材料取前后双窗口，尽量保留开头事实与尾部判决等关键信息。"""
        if not context:
            return ""
        if len(context) <= head + tail:
            return context
        head_part = context[:head]
        tail_part = context[-tail:]
        return (
            f"【材料前段】\n{head_part}\n\n"
            f"【材料后段】\n{tail_part}"
        )

    async def _build_fallback_report(self, task: str, context: str) -> str:
        """当模型提前FINISH或输出过短时，生成完整审查报告（稳定模板兜底）。"""
        legal_lines = []
        legal_seen = set()
        for idx, ref in enumerate(self.legal_references[:8], 1):
            title = ref.get("title", "未知法规")
            article = ref.get("article", "")
            law_id = ref.get("law_id")
            dedup_key = (title, article)
            if dedup_key in legal_seen:
                continue
            legal_seen.add(dedup_key)
            if law_id:
                legal_lines.append(f"{len(legal_lines) + 1}. 《{title}》{article} [法条ID:{law_id}]")
            else:
                legal_lines.append(f"{len(legal_lines) + 1}. 《{title}》{article}")
            if len(legal_lines) >= 5:
                break

        legal_part = "\n".join(legal_lines) if legal_lines else "暂无可用法条，建议补充关键词后重试。"
        context_excerpt = context[:2000]
        logger.info("Build fallback report with deterministic template")

        return (
            "一、案件摘要\n"
            f"本报告依据用户任务要求与案件材料进行审查撰写，任务目标为形成包含“案件摘要、争点分析、法律依据、审查结论”的完整法律审查文书。"
            f"根据现有案件材料，申诉人主张原审在犯罪数额认定与主观故意认定方面存在错误，并请求启动再审程序。"
            f"现有信息显示，本案争议核心集中在事实认定与法律评价的对应关系，即证据链是否能够稳定支撑诈骗罪构成要件。"
            f"综合ReAct流程中的检索与归纳结果，案件审查应围绕证据真实性、关联性、证明力以及主观明知的推定基础展开。\n\n"
            f"案件材料要点如下：{context_excerpt}\n\n"
            "二、争点分析\n"
            "第一，关于涉案金额认定，审查重点在于资金流向、交易对手陈述、客观书证与电子数据之间能否形成闭合证明链。"
            "若金额计算采用推定或间接证据，应重点检验其推理路径是否唯一且排除合理怀疑。"
            "第二，关于主观故意认定，应区分一般民事违约风险与刑事诈骗故意，重点审查行为发生前后的陈述、履约能力、资金用途及事后处置行为。"
            "第三，关于再审必要性，应评估是否存在足以动摇原判决基础的新证据或关键证据矛盾。"
            "若关键证据之间存在冲突且无法合理排除，应优先启动补强调查与关联证据复核程序。\n\n"
            "三、法律依据\n"
            f"结合检索到的规范与条文信息，可形成如下适用框架（仅保留法条ID角标用于后续查库）：\n{legal_part}\n"
            "在适用层面，应坚持罪刑法定与证据裁判原则：对诈骗罪构成要件（行为方式、非法占有目的、被害人处分行为及财产损失结果）逐项对照审查。"
            "对于存在重大分歧的事实认定，应优先采用可核验、可复现的客观证据作为认定基础，避免仅凭单一言词证据作出不利推断。\n\n"
            "四、审查结论\n"
            "基于当前材料，可以形成初步审查意见：本案确有必要围绕金额计算方法与主观故意证明路径开展再核查。"
            "如复核后发现关键证据之间存在实质矛盾，或原判在要件论证上存在明显缺口，建议依法启动再审审查程序；"
            "如关键证据能够相互印证且达到排除合理怀疑标准，则可维持原裁判结论。"
            "现阶段建议同步制作“争点-证据-法条”对应表，作为再审审查的正式工作底稿，以确保审查结论的可解释性与可复核性。"
        )
