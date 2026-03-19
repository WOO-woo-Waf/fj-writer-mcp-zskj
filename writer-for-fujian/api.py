#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
写作服务 API 接口层
提供 HTTP REST API 接口

1. POST /api/write - 主写作接口
2. POST /api/write/stream - 流式写作接口（SSE）
3. GET /api/health - 健康检查
"""

import asyncio
import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import logging
from logging.handlers import RotatingFileHandler

from app.services.writing_service import write_report as service_write_report
from app.services.react_writing_engine import WritingConfig


def _setup_logging() -> logging.Logger:
    log_dir = Path(__file__).resolve().parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "api.log"

    logger_obj = logging.getLogger("writing_api")
    logger_obj.setLevel(logging.INFO)

    if logger_obj.handlers:
        return logger_obj

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    logger_obj.addHandler(file_handler)
    logger_obj.addHandler(console_handler)
    return logger_obj


logger = _setup_logging()

# 创建FastAPI应用
app = FastAPI(
    title="Writing Service API",
    description="基于React框架的法律文书智能写作服务",
    version="1.0.0"
)


# ================================
# 请求/响应模型定义
# ================================

class WriteReportRequest(BaseModel):
    """写作请求模型"""
    case_material: str = Field(..., description="案件材料（字符串）")
    prompt_instruction: str = Field(..., description="提示词指令（字符串）")
    
    # 可选配置
    enable_legal_search: bool = Field(True, description="是否启用法条搜索")
    enable_content_retrieval: bool = Field(False, description="是否启用内容检索")
    section_mode: bool = Field(False, description="是否按章节生成（默认关闭，直接输出完整报告）")
    max_react_steps: int = Field(10, description="最大React循环步数", ge=1, le=30)
    temperature: float = Field(0.2, description="LLM温度参数", ge=0.0, le=2.0)
    repetition_strategy: str = Field("smart", description="重复策略: smart/strict/none")
    
    # 高级配置
    strong_requirements: Optional[List[str]] = Field(None, description="强规范要求列表")
    context_window_limit: int = Field(128000, description="上下文窗口限制（默认128K）")
    multi_turn_enabled: bool = Field(True, description="是否启用多轮对话")
    proactive_tool_call: bool = Field(True, description="是否启用主动工具调用")
    min_output_length: int = Field(0, description="最小输出长度（字符数，默认0表示不做最小长度约束）", ge=0)
    stream_heartbeat_seconds: int = Field(3, description="流式接口心跳间隔秒数", ge=1, le=30)
    
    class Config:
        schema_extra = {
            "example": {
                "case_material": "申诉人：张三，男，1985年出生...",
                "prompt_instruction": "请生成刑事申诉审查报告，包括：一、申诉人基本情况；二、案件来源...",
                "enable_legal_search": True,
                "section_mode": True,
                "max_react_steps": 10,
                "min_output_length": 0
            }
        }


class WriteReportResponse(BaseModel):
    """写作响应模型"""
    success: bool = Field(..., description="是否成功")
    content: str = Field(..., description="生成的报告内容")
    sections: List[Dict[str, Any]] = Field(default_factory=list, description="章节列表")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    error: Optional[str] = Field(None, description="错误信息")
    
    # 调试信息（可选返回）
    debug_info: Optional[Dict[str, Any]] = Field(None, description="调试信息")


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    version: str
    services: Dict[str, str]


def _build_request_id() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]


def _safe_preview(text: str, limit: int = 120) -> str:
    if not text:
        return ""
    clean = text.replace("\n", " ").replace("\r", " ").strip()
    return clean[:limit] + ("..." if len(clean) > limit else "")


def _build_config_from_request(req: WriteReportRequest) -> WritingConfig:
    config = WritingConfig(
        repetition_strategy=req.repetition_strategy,
        context_window_limit=req.context_window_limit,
        strong_requirements=req.strong_requirements or [],
        multi_turn_enabled=req.multi_turn_enabled,
        proactive_tool_call=req.proactive_tool_call,
        min_output_length=req.min_output_length,
    )
    return config


async def _run_write_report(req: WriteReportRequest):
    config = _build_config_from_request(req)
    return await service_write_report(
        case_material=req.case_material,
        prompt_instruction=req.prompt_instruction,
        config=config,
        enable_legal_search=req.enable_legal_search,
        enable_content_retrieval=req.enable_content_retrieval,
        section_mode=req.section_mode,
        max_react_steps=req.max_react_steps,
        temperature=req.temperature,
        context_window_limit=req.context_window_limit,
        multi_turn_enabled=req.multi_turn_enabled,
        proactive_tool_call=req.proactive_tool_call,
        min_output_length=req.min_output_length,
    )


def _run_write_report_sync(req: WriteReportRequest):
    """Run the async write pipeline in an isolated event loop (thread target)."""
    return asyncio.run(_run_write_report(req))


async def _run_write_report_isolated(req: WriteReportRequest):
    """Prevent blocking the main event loop when downstream code uses sync I/O."""
    return await asyncio.to_thread(_run_write_report_sync, req)


def _to_write_response(
    response: Any,
    include_debug: bool,
    request_id: str,
    elapsed_seconds: float,
) -> WriteReportResponse:
    debug_info = None
    if include_debug:
        debug_info = {
            "request_id": request_id,
            "elapsed_seconds": round(elapsed_seconds, 3),
            "react_steps": response.react_steps,
            "legal_references": response.legal_references,
            "retrieved_contents": response.retrieved_contents,
        }

    return WriteReportResponse(
        success=response.success,
        content=response.content,
        sections=response.sections,
        metadata={
            **(response.metadata or {}),
            "request_id": request_id,
            "elapsed_seconds": round(elapsed_seconds, 3),
            "content_length": len(response.content or ""),
        },
        error=response.error,
        debug_info=debug_info,
    )


def _sse_event(event: str, data: Dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


# ================================
# API 端点实现
# ================================

@app.get("/", response_model=Dict[str, str])
async def root():
    """根路径"""
    return {
        "message": "Writing Service API",
        "version": "1.0.0",
        "docs": "/docs",
        "status": "running"
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查"""
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        services={
            "writing_service": "ready",
            "react_engine": "ready",
            "llm_client": "configured"
        }
    )


@app.post("/api/write", response_model=WriteReportResponse)
async def write_report_api(request: WriteReportRequest, include_debug: bool = False):
    """
    写作接口 - 主接口
    
    接收案件材料和提示词，返回生成的报告。
    
    Args:
        request: 写作请求
        include_debug: 是否包含调试信息
        
    Returns:
        WriteReportResponse: 写作响应
        
    标准POST接口：等待任务完成后返回完整结果。
    适合对接常规HTTP调用。
    """
    request_id = _build_request_id()
    start_time = time.perf_counter()

    logger.info(
        f"[{request_id}] 收到写作请求 | case_len={len(request.case_material)} | "
        f"prompt_len={len(request.prompt_instruction)} | max_steps={request.max_react_steps} | "
        f"legal_search={request.enable_legal_search} | content_retrieval={request.enable_content_retrieval}"
    )
    logger.info(
        f"[{request_id}] prompt_preview={_safe_preview(request.prompt_instruction)}"
    )

    try:
        response = await _run_write_report_isolated(request)
        elapsed = time.perf_counter() - start_time
        logger.info(
            f"[{request_id}] 写作完成 | success={response.success} | "
            f"content_len={len(response.content or '')} | elapsed={elapsed:.2f}s"
        )
        return _to_write_response(response, include_debug, request_id, elapsed)
    except Exception as exc:
        elapsed = time.perf_counter() - start_time
        logger.exception(f"[{request_id}] 写作失败 | elapsed={elapsed:.2f}s | error={exc}")
        raise HTTPException(status_code=500, detail=f"写作任务失败: {str(exc)}")


@app.post("/api/write/stream")
async def write_report_stream(request: WriteReportRequest, raw_request: Request):
    """
    流式POST接口（SSE）：
    - 立即返回连接，避免长任务超时
    - 持续输出progress心跳
    - 完成后输出final事件（含完整content字符串）
    """
    request_id = _build_request_id()
    start_time = time.perf_counter()

    logger.info(
        f"[{request_id}] 收到流式写作请求 | case_len={len(request.case_material)} | "
        f"prompt_len={len(request.prompt_instruction)} | heartbeat={request.stream_heartbeat_seconds}s"
    )

    async def event_generator():
        task = asyncio.create_task(_run_write_report_isolated(request))

        yield _sse_event("start", {
            "request_id": request_id,
            "message": "写作任务已启动",
            "case_material_length": len(request.case_material),
            "prompt_instruction_length": len(request.prompt_instruction),
            "timestamp": datetime.now().isoformat(),
        })

        try:
            while not task.done():
                if await raw_request.is_disconnected():
                    task.cancel()
                    logger.warning(f"[{request_id}] 客户端断开，取消流式任务")
                    return

                elapsed = time.perf_counter() - start_time
                yield _sse_event("progress", {
                    "request_id": request_id,
                    "status": "running",
                    "elapsed_seconds": round(elapsed, 2),
                    "message": "模型仍在推理中",
                })
                await asyncio.sleep(request.stream_heartbeat_seconds)

            response = await task
            elapsed = time.perf_counter() - start_time

            logger.info(
                f"[{request_id}] 流式写作完成 | success={response.success} | "
                f"content_len={len(response.content or '')} | elapsed={elapsed:.2f}s"
            )

            yield _sse_event("final", {
                "request_id": request_id,
                "success": response.success,
                "content": response.content,
                "error": response.error,
                "metadata": {
                    **(response.metadata or {}),
                    "elapsed_seconds": round(elapsed, 3),
                    "content_length": len(response.content or ""),
                },
                "react_steps": response.react_steps,
                "legal_references": response.legal_references,
                "retrieved_contents": response.retrieved_contents,
            })

            yield _sse_event("done", {
                "request_id": request_id,
                "status": "completed",
            })

        except asyncio.CancelledError:
            logger.warning(f"[{request_id}] 流式任务取消")
            yield _sse_event("error", {
                "request_id": request_id,
                "error": "任务已取消",
            })
        except Exception as exc:
            logger.exception(f"[{request_id}] 流式任务异常: {exc}")
            yield _sse_event("error", {
                "request_id": request_id,
                "error": str(exc),
            })

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)


@app.post("/api/write/simple")
async def write_report_simple(
    case_material: str,
    prompt_instruction: str,
    enable_legal_search: bool = True,
    section_mode: bool = False
):
    """
    简化写作接口
    
    更简单的接口，只需提供核心参数。
    
    简化写作接口（非流式）。
    """
    request = WriteReportRequest(
        case_material=case_material,
        prompt_instruction=prompt_instruction,
        enable_legal_search=enable_legal_search,
        section_mode=section_mode
    )
    
    return await write_report_api(request, include_debug=False)


@app.get("/api/config/templates")
async def list_templates():
    """
    列出所有可用的提示词模板
    
    当前版本未实现。
    """
    raise HTTPException(status_code=501, detail="接口未实现（按当前需求不处理）")


@app.get("/api/config/templates/{template_id}")
async def get_template(template_id: str):
    """
    获取特定模板的详细信息
    
    当前版本未实现。
    """
    raise HTTPException(status_code=501, detail="接口未实现（按当前需求不处理）")


@app.get("/api/config/requirements")
async def list_requirements(category: Optional[str] = None, min_priority: int = 1):
    """
    列出强规范要求
    
    当前版本未实现。
    """
    raise HTTPException(status_code=501, detail="接口未实现（按当前需求不处理）")


# ================================
# 启动说明
# ================================

if __name__ == "__main__":
    import uvicorn
    
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║          Writing Service API Server                          ║
    ║                                                              ║
    ║  基于 React 框架的法律文书智能写作服务                        ║
    ║                                                              ║
    ║  注意: 当前为接口框架，核心功能待实现                         ║
    ╚══════════════════════════════════════════════════════════════╝
    
    启动中...
    
    接口文档: http://localhost:8000/docs
    健康检查: http://localhost:8000/health
    
    主要接口:
    - POST /api/write               # 完整写作接口（同步返回）
    - POST /api/write/stream        # 完整写作接口（SSE流式）
    - POST /api/write/simple        # 简化写作接口
    - GET  /api/config/templates    # 未实现（501）
    - GET  /api/config/requirements # 未实现（501）
    
    实现步骤:
    1. 调用 /api/write 或 /api/write/stream
    2. 查看 logs/api.log 追踪请求
    3. 按需在调用端处理SSE事件
    
    按 Ctrl+C 停止服务器
    """)
    
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
