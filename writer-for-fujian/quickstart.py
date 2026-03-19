#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
快速启动脚本
用于快速验证服务是否正常
"""

import asyncio
import sys
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def quick_test():
    """快速测试"""
    print("\n" + "=" * 60)
    print("写作服务 - 快速测试")
    print("=" * 60)
    
    try:
        from app.services.writing_service import write_report
        
        print("\n✅ 模块导入成功")
        
        # 简单测试  
        print("\n开始测试写作功能...")
        
        response = await write_report(
            case_material="申诉人：张三，男，涉嫌盗窃罪。",
            prompt_instruction="请生成简要分析，约100字。",
            enable_legal_search=False,
            enable_content_retrieval=False,
            section_mode=False,
            max_react_steps=3
        )
        
        if response.success:
            print("\n✅ 测试通过！")
            print(f"\n生成内容（前200字）:")
            print("-" * 60)
            print(response.content[:200])
            if len(response.content) > 200:
                print("...")
            print("-" * 60)
            return 0
        else:
            print(f"\n❌ 测试失败: {response.error}")
            return 1
            
    except ImportError as e:
        print(f"\n❌ 导入失败: {e}")
        print("\n请检查:")
        print("1. 是否安装了所有依赖: pip install -r requirements.txt")
        print("2. 是否在正确的目录运行")
        return 1
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        logger.error("测试失败", exc_info=True)
        return 1


def main():
    """主函数"""
    print("\n写作服务快速测试工具")
    print("=" * 60)
    print("\n这会运行一个简单的测试来验证服务是否正常工作。")
    print("如果测试失败，请查看错误信息或运行完整测试: python tests/test_service.py\n")
    
    exit_code = asyncio.run(quick_test())
    
    if exit_code == 0:
        print("\n" + "=" * 60)
        print("🎉 服务运行正常！")
        print("=" * 60)
        print("\n下一步:")
        print("1. 运行完整示例: python examples/demo.py")
        print("2. 启动API服务: python api.py")
        print("3. 查看文档: docs/QUICKSTART.md")
        print()
    else:
        print("\n" + "=" * 60)
        print("⚠️  测试失败，请检查配置")
        print("=" * 60)
        print("\n故障排查:")
        print("1. 确认已安装依赖: pip install -r requirements.txt")
        print("2. 配置LLM API: 复制.env.example为.env并填写API密钥")
        print("3. 查看详细错误日志")
        print("4. 参考文档: docs/DEPLOYMENT.md")
        print()
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
