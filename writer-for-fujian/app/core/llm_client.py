#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
大模型API客户端模块
提供统一的LLM接口调用封装，支持流式和非流式输出
"""
import time
import json
import logging
from typing import Optional, Dict, Any, List, Iterator, Union
from dataclasses import dataclass
import httpx

try:
    from app.config.settings import LLMConfig
except ImportError:
    # 如果无法导入，使用默认配置
    class LLMConfig:
        BASE_URL = "https://api.openai.com/v1"
        API_KEY = ""
        MODEL = "gpt-4"
        TIMEOUT = 120
        MAX_RETRIES = 3

logger = logging.getLogger(__name__)


# ================================
# 数据模型
# ================================
@dataclass
class Message:
    """聊天消息数据类"""
    role: str  # system, user, assistant
    content: str
    
    def to_dict(self) -> Dict[str, str]:
        """转换为字典格式"""
        return {"role": self.role, "content": self.content}


@dataclass
class ChatResponse:
    """聊天响应数据类"""
    content: str  # 生成的文本内容
    model: str  # 使用的模型名称
    usage: Dict[str, int]  # token使用统计
    finish_reason: str  # 结束原因：stop, length, content_filter等
    raw_response: Dict[str, Any]  # 原始响应数据
    
    @property
    def prompt_tokens(self) -> int:
        """提示词token数"""
        return self.usage.get("prompt_tokens", 0)
    
    @property
    def completion_tokens(self) -> int:
        """生成内容token数"""
        return self.usage.get("completion_tokens", 0)
    
    @property
    def total_tokens(self) -> int:
        """总token数"""
        return self.usage.get("total_tokens", 0)


# ================================
# 异常类定义
# ================================
class LLMError(Exception):
    """LLM调用基础异常"""
    pass


class LLMAPIError(LLMError):
    """API调用错误"""
    def __init__(self, status_code: int, message: str, response: Optional[Dict] = None):
        self.status_code = status_code
        self.message = message
        self.response = response
        super().__init__(f"API Error {status_code}: {message}")


class LLMTimeoutError(LLMError):
    """请求超时错误"""
    pass


class LLMRateLimitError(LLMError):
    """速率限制错误"""
    pass


# ================================
# LLM客户端
# ================================
class LLMClient:
    """
    大模型API客户端
    
    功能：
    - 支持OpenAI兼容的API接口
    - 自动重试和错误处理
    - 流式和非流式输出
    - 请求日志和性能监控
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
    ):
        """
        初始化LLM客户端
        
        Args:
            api_key: API密钥，默认从配置读取
            base_url: API基础URL，默认从配置读取
            model: 模型名称，默认从配置读取
            timeout: 请求超时时间（秒），默认从配置读取
            max_retries: 最大重试次数，默认从配置读取
        """
        self.api_key = api_key or LLMConfig.API_KEY
        self.base_url = (base_url or LLMConfig.BASE_URL).rstrip("/")
        self.model = model or LLMConfig.MODEL
        self.timeout = timeout or LLMConfig.TIMEOUT
        self.max_retries = max_retries or LLMConfig.MAX_RETRIES
        
        # 验证配置
        if not self.api_key:
            logger.warning("LLM_API_KEY未配置，请设置环境变量或传入api_key参数")
        
        # 创建HTTP客户端
        self.client = httpx.Client(
            timeout=self.timeout,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        )
    
    def chat_completion(
        self,
        messages: List[Union[Dict, Message]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> ChatResponse:
        """
        非流式聊天补全
        
        Args:
            messages: 消息列表
            temperature: 温度参数（0.0-2.0）
            max_tokens: 最大生成token数
            **kwargs: 其他API参数
        
        Returns:
            ChatResponse对象
        """
        # 转换消息格式
        formatted_messages = []
        for msg in messages:
            if isinstance(msg, Message):
                formatted_messages.append(msg.to_dict())
            elif isinstance(msg, dict):
                formatted_messages.append(msg)
            else:
                raise ValueError(f"不支持的消息类型: {type(msg)}")
        
        # 构建请求体
        payload = {
            "model": self.model,
            "messages": formatted_messages,
            "stream": False,
        }
        
        if temperature is not None:
            payload["temperature"] = temperature
        
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        
        payload.update(kwargs)
        
        # 发送请求
        url = f"{self.base_url}/chat/completions"
        
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.post(url, json=payload, timeout=self.timeout)
                response.raise_for_status()
                response_data = response.json()
                
                # 解析响应
                choice = response_data["choices"][0]
                return ChatResponse(
                    content=choice["message"]["content"],
                    model=response_data["model"],
                    usage=response_data.get("usage", {}),
                    finish_reason=choice.get("finish_reason", "unknown"),
                    raw_response=response_data
                )
            
            except httpx.TimeoutException as e:
                if attempt == self.max_retries:
                    raise LLMTimeoutError(f"请求超时（{self.timeout}秒）") from e
                time.sleep(2 ** attempt)
            
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                
                if status_code == 429:
                    if attempt == self.max_retries:
                        raise LLMRateLimitError("API速率限制") from e
                    time.sleep(2 ** attempt)
                    continue
                
                if status_code == 504:
                    if attempt == self.max_retries:
                        raise LLMTimeoutError(f"网关超时（504）") from e
                    time.sleep(2 ** attempt)
                    continue
                
                error_msg = str(e)
                try:
                    if e.response.text:
                        error_response = e.response.json()
                        error_msg = error_response.get("error", {}).get("message", str(e))
                except:
                    pass
                
                raise LLMAPIError(status_code=status_code, message=error_msg) from e
            
            except Exception as e:
                if attempt == self.max_retries:
                    raise LLMError(f"请求失败: {str(e)}") from e
                time.sleep(2 ** attempt)

    def chat_completion_stream(
        self,
        messages: List[Union[Dict, Message]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Iterator[str]:
        """
        流式聊天补全

        Args:
            messages: 消息列表
            temperature: 温度参数（0.0-2.0）
            max_tokens: 最大生成token数
            **kwargs: 其他API参数

        Yields:
            模型生成的增量文本分片
        """
        formatted_messages = []
        for msg in messages:
            if isinstance(msg, Message):
                formatted_messages.append(msg.to_dict())
            elif isinstance(msg, dict):
                formatted_messages.append(msg)
            else:
                raise ValueError(f"不支持的消息类型: {type(msg)}")

        payload = {
            "model": self.model,
            "messages": formatted_messages,
            "stream": True,
        }

        if temperature is not None:
            payload["temperature"] = temperature

        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        payload.update(kwargs)
        url = f"{self.base_url}/chat/completions"

        for attempt in range(self.max_retries + 1):
            try:
                with self.client.stream("POST", url, json=payload, timeout=self.timeout) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line:
                            continue

                        data_line = line.decode("utf-8") if isinstance(line, bytes) else str(line)
                        if not data_line.startswith("data:"):
                            continue

                        data = data_line[5:].strip()
                        if not data:
                            continue
                        if data == "[DONE]":
                            return

                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue

                        choices = chunk.get("choices") or []
                        if not choices:
                            continue

                        delta = choices[0].get("delta", {})
                        content_piece = delta.get("content")
                        if content_piece:
                            yield content_piece
                return

            except httpx.TimeoutException as e:
                if attempt == self.max_retries:
                    raise LLMTimeoutError(f"流式请求超时（{self.timeout}秒）") from e
                time.sleep(2 ** attempt)

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                if status_code == 429:
                    if attempt == self.max_retries:
                        raise LLMRateLimitError("API速率限制") from e
                    time.sleep(2 ** attempt)
                    continue

                if status_code == 504:
                    if attempt == self.max_retries:
                        raise LLMTimeoutError("流式请求网关超时（504）") from e
                    time.sleep(2 ** attempt)
                    continue

                error_msg = str(e)
                try:
                    if e.response.text:
                        error_response = e.response.json()
                        error_msg = error_response.get("error", {}).get("message", str(e))
                except Exception:
                    pass

                raise LLMAPIError(status_code=status_code, message=error_msg) from e

            except Exception as e:
                if attempt == self.max_retries:
                    raise LLMError(f"流式请求失败: {str(e)}") from e
                time.sleep(2 ** attempt)
    
    def close(self):
        """关闭HTTP客户端"""
        self.client.close()
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()
