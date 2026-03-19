#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
独立写作服务 - 完整使用示例
演示如何使用React框架进行多轮对话式法律文书写作
"""

import asyncio
import logging
from pathlib import Path

from app.services.writing_service import WritingService, WritingRequest, write_report
from app.services.writing_config_manager import get_config_manager, StrongRequirement
from app.services.react_writing_engine import WritingConfig

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


# ================================
# 示例1: 基础使用 - 使用便捷函数
# ================================

async def example_basic():
    """基础示例：使用便捷函数生成报告"""
    print("\n" + "=" * 80)
    print("示例1: 基础使用 - 便捷函数")
    print("=" * 80)
    
    # 案件材料
    case_material = """
    申诉人：张三，男，1985年出生，汉族，初中文化，无业。住址：XX市XX区XX路XX号。
    
    案情简介：
    2021年5月10日晚21时许，张三在XX市XX区XX商场停车场内，趁无人注意，
    撬开停放在该处的一辆轿车车门，盗窃车内现金人民币3万元、苹果手机一部（价值8000元）。
    
    2021年5月15日，张三被公安机关抓获。经查，涉案财物已被张三挥霍。
    
    一审判决：
    XX市人民法院于2021年8月认定张三犯盗窃罪，判处有期徒刑三年，并处罚金人民币1万元。
    
    二审裁定：
    XX市中级人民法院于2021年10月裁定驳回上诉，维持原判。
    
    申诉理由：
    1. 一审判决认定被告人盗窃现金3万元证据不足，实际盗窃金额仅为1.5万元
    2. 被告人系初犯，认罪态度好，一审量刑过重
    3. 被告人家庭困难，有年迈父母需要赡养，请求从轻处罚
    """
    
    # 提示词
    prompt_instruction = """
    请根据案件材料生成刑事申诉审查报告，包括以下章节：
    
    一、申诉人基本情况
    二、案件来源及申诉理由
    三、原审判决认定的事实和适用法律
    四、审查认定的事实
    五、审查意见
    
    要求：
    1. 内容详实，逻辑清晰，语言严谨规范
    2. 准确引用相关法律条文（使用法条搜索工具）
    3. 对申诉理由逐一进行回应和分析
    4. 提出明确的审查处理意见
    5. 遵循法律文书格式规范
    """
    
    # 调用写作服务
    response = await write_report(
        case_material=case_material,
        prompt_instruction=prompt_instruction,
        enable_legal_search=True,
        section_mode=True,
        max_react_steps=10
    )
    
    # 输出结果
    if response.success:
        print("\n✅ 生成成功！\n")
        print("=" * 80)
        print(response.content)
        print("=" * 80)
        
        print(f"\n📊 统计信息:")
        print(f"- 章节数: {len(response.sections)}")
        print(f"- React步骤数: {len(response.react_steps)}")
        print(f"- 引用法条数: {len(response.legal_references)}")
        
        # 保存到文件
        output_dir = Path("data/output/writing_service_examples")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "example_basic.md"
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(response.content)
        
        print(f"\n💾 报告已保存到: {output_file}")
    else:
        print(f"\n❌ 生成失败: {response.error}")


# ================================
# 示例2: 高级配置 - 使用WritingService
# ================================

async def example_advanced():
    """高级示例：使用WritingService和自定义配置"""
    print("\n" + "=" * 80)
    print("示例2: 高级配置 - WritingService")
    print("=" * 80)
    
    # 案件材料
    case_material = """
    申诉人：李四，女，1990年出生，汉族，大学文化，某公司职员。
    
    案情：2020年3月，李四涉嫌职务侵占罪被立案侦查。
    指控：利用担任公司财务主管职务便利，侵占公司资金50万元。
    一审：判处有期徒刑五年。
    申诉理由：事实认定不清，证据不足，定性错误。
    """
    
    prompt_instruction = """
    请撰写审查意见章节，重点分析：
    1. 职务侵占罪的构成要件
    2. 本案证据是否充分
    3. 定性是否准确
    """
    
    # 获取配置管理器并添加强规范要求
    config_mgr = get_config_manager()
    
    # 添加自定义强规范要求
    custom_requirement = StrongRequirement(
        id="duty_embezzlement_analysis",
        content="分析职务侵占罪时，必须明确：主体身份、职务便利、侵占行为、非法占有目的、数额标准五个要件",
        priority=5,
        category="criminal",
        repeat_frequency="always"
    )
    config_mgr.add_strong_requirement(custom_requirement)
    
    # 构建自定义配置
    writing_config = WritingConfig(
        max_react_steps=15,
        temperature=0.15,
        enable_legal_search=True,
        enable_content_retrieval=True,
        repetition_strategy="strict",
        context_window_limit=10000,
        strong_requirements=[
            "引用法律条文必须准确无误",
            "分析职务侵占罪时，必须明确主体身份、职务便利、侵占行为、非法占有目的、数额标准五个要件",
            "必须逐一回应申诉理由"
        ]
    )
    
    # 创建写作请求
    request = WritingRequest(
        case_material=case_material,
        prompt_instruction=prompt_instruction,
        config=writing_config,
        enable_legal_search=True,
        enable_content_retrieval=False,
        section_mode=False,  # 直接生成，不分章节
        repetition_strategy="strict"
    )
    
    # 创建服务并执行
    service = WritingService()
    response = await service.write(request)
    
    # 输出结果
    if response.success:
        print("\n✅ 生成成功！\n")
        print("=" * 80)
        print(response.content)
        print("=" * 80)
        
        print(f"\n📊 统计信息:")
        print(f"- React步骤数: {len(response.react_steps)}")
        print(f"- 引用法条数: {len(response.legal_references)}")
        
        # 输出React步骤详情
        print(f"\n🔍 React执行步骤:")
        for step in response.react_steps[:5]:  # 只显示前5步
            print(f"\nStep {step['step']}:")
            print(f"  Thought: {step['thought'][:100]}...")
            if step['action']:
                print(f"  Action: {step['action']}")
            if step['observation']:
                print(f"  Observation: {step['observation'][:100]}...")
        
        # 输出法条引用
        if response.legal_references:
            print(f"\n📚 法条引用:")
            for i, ref in enumerate(response.legal_references[:3], 1):
                print(f"{i}. 《{ref['title']}》{ref['article']}")
    else:
        print(f"\n❌ 生成失败: {response.error}")


# ================================
# 示例3: 配置管理 - 使用模板
# ================================

async def example_with_template():
    """示例：使用预定义模板"""
    print("\n" + "=" * 80)
    print("示例3: 使用预定义模板")
    print("=" * 80)
    
    # 获取配置管理器
    config_mgr = get_config_manager()
    
    # 使用预定义模板
    template = config_mgr.get_prompt_template("criminal_appeal_full")
    
    if not template:
        print("❌ 模板未找到")
        return
    
    print(f"📄 使用模板: {template.name}")
    print(f"   描述: {template.description}")
    
    # 案件材料
    case_material = """
    申诉人：王五，男，1988年生。
    案情：2019年涉嫌诈骗罪，一审判处有期徒刑四年。
    申诉：事实认定错误，请求改判无罪。
    """
    
    # 获取强规范要求
    strong_reqs = config_mgr.get_strong_requirements(category="criminal", min_priority=4)
    special_requirements = "\n".join([f"- {req.content}" for req in strong_reqs])
    
    # 渲染模板
    prompt_instruction = template.render(
        case_material=case_material,
        special_requirements=special_requirements
    )
    
    print(f"\n📝 生成的提示词：")
    print("-" * 80)
    print(prompt_instruction[:500] + "...")
    print("-" * 80)
    
    # 执行写作（简化输出）
    response = await write_report(
        case_material=case_material,
        prompt_instruction=prompt_instruction,
        enable_legal_search=True,
        section_mode=True,
        max_react_steps=8
    )
    
    if response.success:
        print(f"\n✅ 生成成功！内容长度: {len(response.content)} 字符")
        print(f"   章节数: {len(response.sections)}")
    else:
        print(f"\n❌ 生成失败: {response.error}")


# ================================
# 示例4: 不使用法条搜索（纯写作）
# ================================

async def example_without_legal_search():
    """示例：不使用法条搜索的纯写作模式"""
    print("\n" + "=" * 80)
    print("示例4: 纯写作模式（无法条搜索）")
    print("=" * 80)
    
    case_material = """
    案情摘要：某交通事故案件，原告诉称被告驾驶机动车发生碰撞，
    要求赔偿医疗费、误工费等共计10万元。被告辩称事故责任在原告。
    """
    
    prompt_instruction = """
    请根据案情材料，撰写一份事实认定和证据分析报告。
    不需要引用法律条文，重点分析：
    1. 事故责任认定
    2. 证据充分性
    3. 赔偿金额合理性
    """
    
    response = await write_report(
        case_material=case_material,
        prompt_instruction=prompt_instruction,
        enable_legal_search=False,  # 关闭法条搜索
        enable_content_retrieval=False,  # 关闭内容检索
        section_mode=False,
        max_react_steps=6
    )
    
    if response.success:
        print("\n✅ 生成成功！\n")
        print("=" * 80)
        print(response.content)
        print("=" * 80)
    else:
        print(f"\n❌ 生成失败: {response.error}")


# ================================
# 主函数
# ================================

async def main():
    """主函数：运行所有示例"""
    print("\n" + "=" * 80)
    print("独立写作服务 - 完整示例演示")
    print("=" * 80)
    
    try:
        # 运行示例1：基础使用
        await example_basic()
        
        # 运行示例2：高级配置
        # await example_advanced()
        
        # 运行示例3：使用模板
        # await example_with_template()
        
        # 运行示例4：纯写作模式
        # await example_without_legal_search()
        
        print("\n" + "=" * 80)
        print("✅ 所有示例运行完成")
        print("=" * 80)
        
    except Exception as e:
        logger.error(f"运行示例时发生错误: {e}", exc_info=True)
        print(f"\n❌ 错误: {e}")


if __name__ == "__main__":
    # 运行主函数
    asyncio.run(main())
