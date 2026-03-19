#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
独立写作服务接口
提供基于React框架的多轮对话写作功能
支持法条搜索、内容检索和智能写作
"""

import logging
import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

from app.core.llm_client import LLMClient
from app.integrations.mcp_client import LegalMCPClient
from app.services.react_writing_engine import ReactWritingEngine, WritingConfig
from app.services.content_retriever import ContentRetriever

logger = logging.getLogger(__name__)


@dataclass
class WritingRequest:
    """写作请求"""
    case_material: str  # 案件材料
    prompt_instruction: str  # 提示词指令
    
    # 可选配置
    config: Optional[WritingConfig] = None
    enable_legal_search: bool = True  # 是否启用法条搜索
    enable_content_retrieval: bool = True  
    max_react_steps: int = 10  # 最大React循环步数
    temperature: float = 0  # LLM温度参数
    
    # 高级选项
    section_mode: bool = False  # 兼容参数：默认关闭章节模式，统一直接生成完整报告
    repetition_strategy: str = "smart"  # 重复策略: smart, strict, none
    context_window_limit: int = 128000  # 上下文窗口限制（模型支持128K）
    multi_turn_enabled: bool = True
    proactive_tool_call: bool = True
    min_output_length: int = 0


@dataclass
class WritingResponse:
    """写作响应"""
    success: bool
    content: str  # 生成的报告内容
    sections: List[Dict[str, Any]] = field(default_factory=list)  # 章节内容（如果使用章节模式）
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据
    error: Optional[str] = None  # 错误信息
    
    # 调试信息
    react_steps: List[Dict[str, Any]] = field(default_factory=list)  # React执行步骤
    legal_references: List[Dict[str, Any]] = field(default_factory=list)  # 法条引用
    retrieved_contents: List[Dict[str, Any]] = field(default_factory=list)  # 检索内容


class WritingService:
    """
    独立写作服务
    
    核心功能：
    1. 接收两类输入：案件材料 + 提示词指令
    2. 使用React框架进行多轮推理
    3. 调用MCP完成法条检索
    4. 汇总案件材料、法条内容与提示词指令
    5. 生成完整报告
    
    特点：
    - 所有参数可配置
    - 默认非章节化直出模式
    - 支持法条检索能力增强
    - 上下文窗口默认128K
    - 完整的调试和追踪信息
    """
    
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        mcp_client: Optional[LegalMCPClient] = None,
        content_retriever: Optional[ContentRetriever] = None
    ):
        """
        初始化写作服务
        
        Args:
            llm_client: LLM客户端（可选，默认自动创建）
            mcp_client: MCP法条搜索客户端（可选）
            content_retriever: 内容检索器（可选）
        """
        self.llm_client = llm_client or LLMClient()
        self.mcp_client = mcp_client

        if self.mcp_client is None:
            default_sse_url = os.getenv("MCP_SSE_URL", "http://127.0.0.1:8000/sse")
            try:
                self.mcp_client = LegalMCPClient(sse_url=default_sse_url)
                logger.info(f"MCP client auto-initialized with {default_sse_url}")
            except Exception as exc:
                logger.warning(f"MCP client not initialized: {exc}")

        self.content_retriever = content_retriever
        
        logger.info("WritingService initialized")
    
    async def write(self, request: WritingRequest) -> WritingResponse:
        """
        执行写作任务
        
        Args:
            request: 写作请求
            
        Returns:
            WritingResponse: 写作响应
        """
        logger.info(f"开始写作任务 - 案件材料长度: {len(request.case_material)}, "
                   f"提示词长度: {len(request.prompt_instruction)}")
        
        try:
            # 1. 准备配置
            config = request.config or WritingConfig()
            config.max_react_steps = request.max_react_steps
            config.temperature = request.temperature
            config.enable_legal_search = request.enable_legal_search
            config.enable_content_retrieval = request.enable_content_retrieval
            config.repetition_strategy = request.repetition_strategy
            config.context_window_limit = request.context_window_limit
            config.multi_turn_enabled = request.multi_turn_enabled
            config.proactive_tool_call = request.proactive_tool_call
            config.min_output_length = request.min_output_length

            if request.enable_content_retrieval and self.content_retriever is None:
                self.content_retriever = ContentRetriever()
            
            # 2. 创建React写作引擎
            engine = ReactWritingEngine(
                llm_client=self.llm_client,
                mcp_client=self.mcp_client if request.enable_legal_search else None,
                content_retriever=self.content_retriever if request.enable_content_retrieval else None,
                config=config
            )
            
            # 3. 默认并统一采用直接模式：一次性生成完整内容
            if request.section_mode:
                logger.info("section_mode=True 已收到，但当前流程统一使用直接模式生成完整报告")

            result = await self._generate_direct(
                engine=engine,
                case_material=request.case_material,
                prompt_instruction=request.prompt_instruction
            )
            
            # 4. 构建响应
            response = WritingResponse(
                success=True,
                content=result["content"],
                sections=result.get("sections", []),
                metadata=result.get("metadata", {}),
                react_steps=result.get("react_steps", []),
                legal_references=result.get("legal_references", []),
                retrieved_contents=result.get("retrieved_contents", [])
            )
            
            logger.info(f"写作任务完成 - 内容长度: {len(response.content)}")
            return response
            
        except Exception as e:
            logger.error(f"写作任务失败: {str(e)}", exc_info=True)
            return WritingResponse(
                success=False,
                content="",
                error=str(e)
            )
    
    async def _generate_by_sections(
        self,
        engine: ReactWritingEngine,
        case_material: str,
        prompt_instruction: str
    ) -> Dict[str, Any]:
        """
        按章节生成内容
        
        Args:
            engine: React写作引擎
            case_material: 案件材料
            prompt_instruction: 提示词
            
        Returns:
            结果字典
        """
        logger.info("使用章节模式生成")
        
        # 1. 解析章节结构（从提示词中提取或使用默认结构）
        sections = self._parse_sections_from_prompt(prompt_instruction)
        
        # 2. 为每个章节生成内容
        section_results = []
        all_react_steps = []
        all_legal_refs = []
        all_retrieved = []
        all_dialogue_turns = []
        
        for section in sections:
            logger.info(f"生成章节: {section['title']}")
            
            # 构建章节特定的提示词
            section_prompt = self._build_section_prompt(
                case_material=case_material,
                global_instruction=prompt_instruction,
                section_info=section
            )
            
            # 使用React引擎生成
            section_result = await engine.generate(
                task_description=section_prompt,
                context=case_material
            )
            
            section_results.append({
                "id": section["id"],
                "title": section["title"],
                "content": section_result["content"],
                "metadata": section_result.get("metadata", {})
            })
            
            # 收集调试信息
            all_react_steps.extend(section_result.get("react_steps", []))
            all_legal_refs.extend(section_result.get("legal_references", []))
            all_retrieved.extend(section_result.get("retrieved_contents", []))
            all_dialogue_turns.extend(section_result.get("metadata", {}).get("dialogue_turns", []))
        
        # 3. 汇总所有章节
        full_content = self._assemble_sections(section_results)
        
        return {
            "content": full_content,
            "sections": section_results,
            "metadata": {
                "total_sections": len(section_results),
                "generation_mode": "section_by_section",
                "dialogue_turns": all_dialogue_turns,
            },
            "react_steps": all_react_steps,
            "legal_references": all_legal_refs,
            "retrieved_contents": all_retrieved
        }
    
    async def _generate_direct(
        self,
        engine: ReactWritingEngine,
        case_material: str,
        prompt_instruction: str
    ) -> Dict[str, Any]:
        """
        直接生成完整内容
        
        Args:
            engine: React写作引擎
            case_material: 案件材料
            prompt_instruction: 提示词
            
        Returns:
            结果字典
        """
        logger.info("使用直接模式生成")
        
        # 使用React引擎生成
        result = await engine.generate(
            task_description=prompt_instruction,
            context=case_material
        )
        
        return {
            "content": result["content"],
            "sections": [],
            "metadata": {
                "generation_mode": "direct",
                "dialogue_turns": result.get("metadata", {}).get("dialogue_turns", []),
            },
            "react_steps": result.get("react_steps", []),
            "legal_references": result.get("legal_references", []),
            "retrieved_contents": result.get("retrieved_contents", [])
        }
    
    def _parse_sections_from_prompt(self, prompt: str) -> List[Dict[str, str]]:
        """
        从提示词中解析章节结构
        
        如果提示词中包含章节标记（如"一、"、"二、"等），则提取；
        否则返回默认的单章节结构
        
        Args:
            prompt: 提示词
            
        Returns:
            章节列表
        """
        import re
        
        # 尝试匹配中文章节标记
        pattern = r'([一二三四五六七八九十]+、.+?)(?=\n|$)'
        matches = re.findall(pattern, prompt)
        
        if matches:
            sections = []
            for i, match in enumerate(matches, 1):
                title = match.strip()
                sections.append({
                    "id": f"section_{i}",
                    "title": title,
                    "order": i
                })
            return sections
        
        # 默认单章节
        return [{
            "id": "main_section",
            "title": "主要内容",
            "order": 1
        }]
    
    def _build_section_prompt(
        self,
        case_material: str,
        global_instruction: str,
        section_info: Dict[str, str]
    ) -> str:
        """
        构建章节特定的提示词
        
        Args:
            case_material: 案件材料
            global_instruction: 全局指令
            section_info: 章节信息
            
        Returns:
            章节提示词
        """
        section_prompt = f"""
【全局要求】
{global_instruction}

【当前章节】
{section_info['title']}

【章节任务】
根据全局要求和案件材料，生成"{section_info['title']}"的内容。

注意：
1. 遵循全局要求中的所有规范
2. 重要的强规范要求需要在本章节中体现
3. 内容应详细、准确、符合法律文书规范
4. 如需引用法条，使用法条搜索工具获取准确内容
"""
        return section_prompt.strip()
    
    def _assemble_sections(self, sections: List[Dict[str, Any]]) -> str:
        """
        汇总所有章节为完整文档
        
        Args:
            sections: 章节列表
            
        Returns:
            完整文档内容
        """
        content_parts = []
        
        for section in sections:
            # 添加章节标题
            content_parts.append(f"\n\n{section['title']}\n")
            content_parts.append("=" * 50)
            content_parts.append("\n\n")
            
            # 添加章节内容
            content_parts.append(section['content'])
        
        return "".join(content_parts).strip()


# ================================
# 便捷函数
# ================================

async def write_report(
    case_material: str,
    prompt_instruction: str,
    **kwargs
) -> WritingResponse:
    """
    便捷函数：生成报告
    
    Args:
        case_material: 案件材料（字符串）
        prompt_instruction: 提示词（字符串）
        **kwargs: 其他配置参数
        
    Returns:
        WritingResponse: 写作响应
    
    示例:
        >>> response = await write_report(
        ...     case_material="张三涉嫌盗窃案，涉案金额5万元...",
        ...     prompt_instruction="请生成刑事申诉审查报告，包括案情分析、法律适用...",
        ...     enable_legal_search=True,
        ...     section_mode=False
        ... )
        >>> print(response.content)
    """
    service = WritingService()
    request = WritingRequest(
        case_material=case_material,
        prompt_instruction=prompt_instruction,
        **kwargs
    )
    return await service.write(request)


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
    
    async def test_writing_service():
        """测试写作服务"""
        
        # 示例：案件材料
        case_material = """
        申诉人：张三，男，1980年出生，汉族，初中文化，无业。
        
        案情简介：
        2020年3月，张三因涉嫌盗窃罪被XX市公安局刑事拘留。
        经查，张三于2020年2月15日晚，在XX市XX路XX号居民楼，
        采用翻窗入室的方式，盗窃现金5万元及金银首饰若干。
        
        一审判决：XX市人民法院以盗窃罪判处张三有期徒刑三年，并处罚金1万元。
        
        申诉理由：
        1. 一审判决认定事实不清，证据不足
        2. 涉案金额计算错误
        3. 量刑过重
        """
        
        # 示例：提示词
        prompt_instruction = """
        请根据案件材料生成刑事申诉审查报告，包括以下章节：
        
        一、申诉人基本情况
        二、案件来源及申诉理由
        三、原审判决认定的事实和适用法律
        四、审查认定的事实
        五、审查意见
        
        要求：
        1. 内容详实，逻辑清晰
        2. 准确引用相关法律条文
        3. 对申诉理由逐一进行分析
        4. 提出明确的审查意见
        """
        
        # 调用写作服务
        response = await write_report(
            case_material=case_material,
            prompt_instruction=prompt_instruction,
            enable_legal_search=True,
            section_mode=False,
            max_react_steps=10
        )
        
        # 输出结果
        if response.success:
            print("=" * 60)
            print("生成成功！")
            print("=" * 60)
            print(response.content)
            print("\n" + "=" * 60)
            print(f"共生成 {len(response.sections)} 个章节")
            print(f"React步骤数: {len(response.react_steps)}")
            print(f"引用法条数: {len(response.legal_references)}")
        else:
            print(f"生成失败: {response.error}")
    
    # 运行测试
    asyncio.run(test_writing_service())
