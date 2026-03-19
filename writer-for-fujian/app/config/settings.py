#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
配置文件 - 写作服务配置
"""
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# 项目根目录（writer-for-fujian）
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 加载环境变量文件
env_file_override = os.getenv("WRITER_ENV_FILE")
if env_file_override:
    env_file = Path(env_file_override).expanduser().resolve()
else:
    env_file = PROJECT_ROOT / ".env"

if env_file.exists():
    load_dotenv(env_file)


def get_env(key: str, default: Optional[str] = None) -> str:
    """读取环境变量"""
    return os.getenv(key, default)


def get_env_int(key: str, default: int = 0) -> int:
    """读取整型环境变量"""
    try:
        return int(os.getenv(key, default))
    except ValueError:
        return default


def get_env_float(key: str, default: float = 0.0) -> float:
    """读取浮点型环境变量"""
    try:
        return float(os.getenv(key, default))
    except ValueError:
        return default


# ================================
# 大模型API配置
# ================================
class LLMConfig:
    """大模型API配置类"""
    BASE_URL = get_env("LLM_BASE_URL", "https://api.openai.com/v1")
    API_KEY = get_env("LLM_API_KEY", "")
    MODEL = get_env("LLM_MODEL", "gpt-4")
    TIMEOUT = get_env_int("LLM_TIMEOUT", 120)
    MAX_RETRIES = get_env_int("LLM_MAX_RETRIES", 3)


# ================================
# MCP配置
# ================================
class MCPConfig:
    """MCP服务配置"""
    SSE_URL = get_env("MCP_SSE_URL", "")
    API_KEY = get_env("MODELSCOPE_KEY", "")


# ================================
# 路径配置
# ================================
CONFIG_DIR = PROJECT_ROOT / "config"
CONFIG_WRITING_DIR = CONFIG_DIR / "writing"

# 确保目录存在
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_WRITING_DIR.mkdir(parents=True, exist_ok=True)
