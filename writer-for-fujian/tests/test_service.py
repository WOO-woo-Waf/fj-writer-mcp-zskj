#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
独立写作服务 - 简单测试脚本
用于快速验证系统是否正常工作
"""

import asyncio
import logging
import sys
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def test_basic_writing():
    """测试基础写作功能"""
    print("\n" + "=" * 80)
    print("测试1: 基础写作功能（不使用法条搜索）")
    print("=" * 80)
    
    try:
        from app.services.writing_service import write_report
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        print("请确保在项目根目录运行此脚本")
        return False
    
    # 简单的案件材料
    case_material = """
    申诉人：张三，男，1985年出生。
    案情：涉嫌盗窃罪，一审判处有期徒刑三年。
    申诉理由：证据不足，量刑过重。
    """
    
    # 简单的提示词
    prompt = """
    请根据案件材料撰写一份简短的分析报告，包括：
    1. 案情概述
    2. 申诉理由分析
    3. 初步意见
    
    注意：内容简洁即可，约200-300字。
    """
    
    try:
        print("开始生成...")
        response = await write_report(
            case_material=case_material,
            prompt_instruction=prompt,
            enable_legal_search=False,  # 不使用法条搜索，避免MCP配置问题
            enable_content_retrieval=False,
            section_mode=False,
            max_react_steps=5  # 减少步数，加快测试
        )
        
        if response.success:
            print("\n✅ 测试通过！")
            print("\n生成的内容：")
            print("-" * 80)
            print(response.content[:500])  # 只显示前500字符
            if len(response.content) > 500:
                print("...(省略)")
            print("-" * 80)
            print(f"\n内容总长度: {len(response.content)} 字符")
            print(f"React步骤数: {len(response.react_steps)}")
            return True
        else:
            print(f"\n❌ 测试失败: {response.error}")
            return False
            
    except Exception as e:
        print(f"\n❌ 测试出错: {str(e)}")
        logger.error("测试失败", exc_info=True)
        return False


async def test_section_mode():
    """测试章节模式"""
    print("\n" + "=" * 80)
    print("测试2: 章节模式")
    print("=" * 80)
    
    try:
        from app.services.writing_service import write_report
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return False
    
    case_material = "申诉人：李四，女，涉嫌职务侵占罪。"
    
    prompt = """
    请撰写报告，包括：
    一、基本情况
    二、案情分析
    """
    
    try:
        print("开始生成...")
        response = await write_report(
            case_material=case_material,
            prompt_instruction=prompt,
            enable_legal_search=False,
            section_mode=True,  # 使用章节模式
            max_react_steps=6
        )
        
        if response.success:
            print("\n✅ 测试通过！")
            print(f"生成了 {len(response.sections)} 个章节")
            for i, section in enumerate(response.sections, 1):
                print(f"\n章节 {i}: {section['title']}")
                print(f"内容长度: {len(section['content'])} 字符")
            return True
        else:
            print(f"\n❌ 测试失败: {response.error}")
            return False
            
    except Exception as e:
        print(f"\n❌ 测试出错: {str(e)}")
        logger.error("测试失败", exc_info=True)
        return False


async def test_config_manager():
    """测试配置管理器"""
    print("\n" + "=" * 80)
    print("测试3: 配置管理器")
    print("=" * 80)
    
    try:
        from app.services.writing_config_manager import get_config_manager
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return False
    
    try:
        config_mgr = get_config_manager()
        
        print(f"✅ 配置管理器初始化成功")
        print(f"   提示词模板数: {len(config_mgr.prompt_templates)}")
        print(f"   强规范要求数: {len(config_mgr.strong_requirements)}")
        print(f"   React模式数: {len(config_mgr.react_patterns)}")
        
        # 列出模板
        print("\n可用模板:")
        for tid, template in list(config_mgr.prompt_templates.items())[:3]:
            print(f"  - {tid}: {template.name}")
        
        # 列出强规范要求
        requirements = config_mgr.get_strong_requirements(min_priority=4)
        print(f"\n高优先级强规范要求 (共{len(requirements)}个):")
        for req in requirements[:3]:
            print(f"  - [{req.priority}] {req.content[:50]}...")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试出错: {str(e)}")
        logger.error("测试失败", exc_info=True)
        return False


async def test_react_engine():
    """测试React引擎"""
    print("\n" + "=" * 80)
    print("测试4: React引擎")
    print("=" * 80)
    
    try:
        from app.services.react_writing_engine import ReactWritingEngine, WritingConfig
        from app.core.llm_client import LLMClient
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return False
    
    try:
        llm_client = LLMClient()
        config = WritingConfig(
            max_react_steps=3,
            enable_legal_search=False,
            enable_content_retrieval=False
        )
        
        engine = ReactWritingEngine(
            llm_client=llm_client,
            mcp_client=None,
            content_retriever=None,
            config=config
        )
        
        print("✅ React引擎初始化成功")
        print(f"   注册工具数: {len(engine.tools)}")
        print(f"   可用工具: {', '.join(engine.tools.keys())}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试出错: {str(e)}")
        logger.error("测试失败", exc_info=True)
        return False


async def main():
    """主测试函数"""
    print("\n" + "=" * 80)
    print("独立写作服务 - 系统测试")
    print("=" * 80)
    print("\n开始运行测试套件...")
    
    results = []
    
    # 测试1: 基础写作
    result1 = await test_basic_writing()
    results.append(("基础写作功能", result1))
    
    # 测试2: 章节模式
    result2 = await test_section_mode()
    results.append(("章节模式", result2))
    
    # 测试3: 配置管理器
    result3 = await test_config_manager()
    results.append(("配置管理器", result3))
    
    # 测试4: React引擎
    result4 = await test_react_engine()
    results.append(("React引擎", result4))
    
    # 汇总结果
    print("\n" + "=" * 80)
    print("测试结果汇总")
    print("=" * 80)
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status}  {test_name}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print("\n" + "=" * 80)
    print(f"总计: {len(results)} 个测试")
    print(f"通过: {passed} 个")
    print(f"失败: {failed} 个")
    print("=" * 80)
    
    if failed == 0:
        print("\n🎉 所有测试通过！系统运行正常。")
        print("\n下一步:")
        print("1. 运行完整示例: python examples/writing_service_demo.py")
        print("2. 启动API服务: python api_server.py")
        print("3. 查看文档: docs/services/WRITING_SERVICE.md")
        return 0
    else:
        print(f"\n⚠️  有 {failed} 个测试失败，请检查错误信息。")
        print("\n调试建议:")
        print("1. 检查是否在项目根目录运行")
        print("2. 确认已安装所有依赖: pip install -r requirements.txt")
        print("3. 查看详细日志信息")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
