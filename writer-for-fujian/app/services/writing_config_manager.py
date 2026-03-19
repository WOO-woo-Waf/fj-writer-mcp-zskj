#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
写作配置管理器
管理所有可配置的参数、提示词模板和强规范要求
"""

import logging
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class PromptTemplate:
    """提示词模板"""
    id: str
    name: str
    description: str
    template: str
    variables: List[str]  # 模板中的变量名
    category: str = "general"  # 分类：general, legal, criminal, civil等
    
    def render(self, **kwargs) -> str:
        """渲染模板"""
        try:
            return self.template.format(**kwargs)
        except KeyError as e:
            logger.warning(f"模板渲染缺少变量: {e}")
            return self.template


@dataclass
class StrongRequirement:
    """强规范要求"""
    id: str
    content: str  # 要求内容
    priority: int = 1  # 优先级（1-5，5最高）
    category: str = "general"  # 分类
    repeat_frequency: str = "smart"  # 重复频率：always, smart, once
    
    def __str__(self) -> str:
        return self.content


class WritingConfigManager:
    """
    写作配置管理器
    
    管理内容：
    1. 提示词模板库
    2. 强规范要求库
    3. React模式性提示词
    4. 系统参数配置
    
    特点：
    - 支持从文件加载配置
    - 支持动态添加和修改
    - 支持配置导出和导入
    - 支持配置版本管理
    """
    
    def __init__(self, config_dir: Optional[Path] = None):
        """
        初始化配置管理器
        
        Args:
            config_dir: 配置文件目录，None则使用默认目录
        """
        self.config_dir = config_dir or Path(__file__).parent.parent.parent / "config" / "writing"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # 模板库
        self.prompt_templates: Dict[str, PromptTemplate] = {}
        
        # 强规范要求库
        self.strong_requirements: Dict[str, StrongRequirement] = {}
        
        # React模式性提示词
        self.react_patterns: Dict[str, str] = {}
        
        # 系统参数
        self.system_params: Dict[str, Any] = self._default_system_params()
        
        # 加载配置
        self._load_all_configs()
        
        logger.info(f"WritingConfigManager initialized - config_dir={self.config_dir}")
    
    def _default_system_params(self) -> Dict[str, Any]:
        """默认系统参数"""
        return {
            "max_react_steps": 10,
            "temperature": 0.2,
            "context_window_limit": 8000,
            "enable_legal_search": True,
            "enable_content_retrieval": True,
            "repetition_strategy": "smart",
            "section_mode": True
        }
    
    def _load_all_configs(self):
        """加载所有配置"""
        self._load_prompt_templates()
        self._load_strong_requirements()
        self._load_react_patterns()
        self._load_system_params()
    
    def _load_prompt_templates(self):
        """加载提示词模板"""
        template_file = self.config_dir / "prompt_templates.json"
        
        if not template_file.exists():
            # 创建默认模板
            self._create_default_prompt_templates()
            self._save_prompt_templates()
            return
        
        try:
            with open(template_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            for item in data:
                template = PromptTemplate(**item)
                self.prompt_templates[template.id] = template
            
            logger.info(f"加载了 {len(self.prompt_templates)} 个提示词模板")
        except Exception as e:
            logger.error(f"加载提示词模板失败: {e}")
    
    def _load_strong_requirements(self):
        """加载强规范要求"""
        req_file = self.config_dir / "strong_requirements.json"
        
        if not req_file.exists():
            # 创建默认强规范要求
            self._create_default_strong_requirements()
            self._save_strong_requirements()
            return
        
        try:
            with open(req_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            for item in data:
                req = StrongRequirement(**item)
                self.strong_requirements[req.id] = req
            
            logger.info(f"加载了 {len(self.strong_requirements)} 个强规范要求")
        except Exception as e:
            logger.error(f"加载强规范要求失败: {e}")
    
    def _load_react_patterns(self):
        """加载React模式性提示词"""
        pattern_file = self.config_dir / "react_patterns.json"
        
        if not pattern_file.exists():
            # 创建默认模式
            self._create_default_react_patterns()
            self._save_react_patterns()
            return
        
        try:
            with open(pattern_file, "r", encoding="utf-8") as f:
                self.react_patterns = json.load(f)
            
            logger.info(f"加载了 {len(self.react_patterns)} 个React模式")
        except Exception as e:
            logger.error(f"加载React模式失败: {e}")
    
    def _load_system_params(self):
        """加载系统参数"""
        param_file = self.config_dir / "system_params.json"
        
        if not param_file.exists():
            self._save_system_params()
            return
        
        try:
            with open(param_file, "r", encoding="utf-8") as f:
                loaded_params = json.load(f)
                self.system_params.update(loaded_params)
            
            logger.info(f"加载系统参数: {list(self.system_params.keys())}")
        except Exception as e:
            logger.error(f"加载系统参数失败: {e}")
    
    # ==================== 默认配置创建 ====================
    
    def _create_default_prompt_templates(self):
        """创建默认提示词模板"""
        templates = [
            PromptTemplate(
                id="criminal_appeal_full",
                name="刑事申诉完整报告",
                description="生成完整的刑事申诉审查报告",
                template="""请根据以下案件材料生成刑事申诉审查报告。

【案件材料】
{case_material}

【报告要求】
1. 包含以下章节：申诉人基本情况、案件来源及申诉理由、原审判决事实和法律适用、审查认定事实、审查意见
2. 内容详实，逻辑清晰，语言规范
3. 准确引用相关法律条文
4. 对申诉理由逐一分析
5. 提出明确的审查处理意见

【特别注意】
{special_requirements}
""",
                variables=["case_material", "special_requirements"],
                category="criminal"
            ),
            PromptTemplate(
                id="section_opinion",
                name="审查意见章节",
                description="生成审查处理意见章节",
                template="""请根据案件材料和前期调研，撰写审查处理意见章节。

【案件材料】
{case_material}

【申诉理由】
{appeal_reasons}

【法律依据】
{legal_basis}

【撰写要求】
1. 逐条回应申诉理由
2. 结合事实和证据进行分析
3. 准确引用法律条文
4. 提出明确的审查结论
5. 语言严谨，逻辑清晰
""",
                variables=["case_material", "appeal_reasons", "legal_basis"],
                category="criminal"
            ),
            PromptTemplate(
                id="fact_summary",
                name="事实认定汇总",
                description="汇总和认定案件事实",
                template="""请根据以下材料汇总案件事实。

【原始材料】
{materials}

【汇总要求】
1. 提取关键事实要素
2. 时间、地点、人物、行为、结果清晰
3. 客观准确，不加主观评价
4. 突出与争议焦点相关的事实
""",
                variables=["materials"],
                category="general"
            )
        ]
        
        for template in templates:
            self.prompt_templates[template.id] = template
    
    def _create_default_strong_requirements(self):
        """创建默认强规范要求"""
        requirements = [
            StrongRequirement(
                id="accurate_legal_citation",
                content="引用法律条文必须准确无误，不得编造或曲解法律规定",
                priority=5,
                category="legal",
                repeat_frequency="always"
            ),
            StrongRequirement(
                id="objective_language",
                content="使用客观、中立的语言，避免主观臆断和情绪化表达",
                priority=4,
                category="general",
                repeat_frequency="smart"
            ),
            StrongRequirement(
                id="logical_structure",
                content="保持清晰的逻辑结构，论述层次分明，结论有据",
                priority=4,
                category="general",
                repeat_frequency="smart"
            ),
            StrongRequirement(
                id="respond_all_appeals",
                content="必须逐一回应申诉人提出的所有申诉理由，不得遗漏",
                priority=5,
                category="criminal",
                repeat_frequency="always"
            ),
            StrongRequirement(
                id="evidence_based",
                content="所有事实认定必须有充分证据支持，证据来源清晰",
                priority=5,
                category="general",
                repeat_frequency="always"
            ),
            StrongRequirement(
                id="format_compliance",
                content="严格遵守法律文书格式规范，章节完整，标题准确",
                priority=3,
                category="general",
                repeat_frequency="once"
            )
        ]
        
        for req in requirements:
            self.strong_requirements[req.id] = req
    
    def _create_default_react_patterns(self):
        """创建默认React模式性提示词"""
        self.react_patterns = {
            "analysis_step": "首先分析案件的核心争议点和需要解决的关键问题",
            "legal_search_step": "对于涉及法律适用的问题，必须使用法条搜索工具获取准确的法律依据",
            "fact_review_step": "在形成意见前，系统回顾案件事实和相关证据",
            "reasoning_step": "运用法律推理，将事实、证据和法律规定结合起来",
            "conclusion_step": "最后形成明确的审查意见和处理建议",
            "quality_check": "检查内容是否符合所有强规范要求"
        }
    
    # ==================== 保存方法 ====================
    
    def _save_prompt_templates(self):
        """保存提示词模板"""
        template_file = self.config_dir / "prompt_templates.json"
        try:
            data = [asdict(t) for t in self.prompt_templates.values()]
            with open(template_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"保存了 {len(data)} 个提示词模板")
        except Exception as e:
            logger.error(f"保存提示词模板失败: {e}")
    
    def _save_strong_requirements(self):
        """保存强规范要求"""
        req_file = self.config_dir / "strong_requirements.json"
        try:
            data = [asdict(r) for r in self.strong_requirements.values()]
            with open(req_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"保存了 {len(data)} 个强规范要求")
        except Exception as e:
            logger.error(f"保存强规范要求失败: {e}")
    
    def _save_react_patterns(self):
        """保存React模式"""
        pattern_file = self.config_dir / "react_patterns.json"
        try:
            with open(pattern_file, "w", encoding="utf-8") as f:
                json.dump(self.react_patterns, f, ensure_ascii=False, indent=2)
            logger.info(f"保存了 {len(self.react_patterns)} 个React模式")
        except Exception as e:
            logger.error(f"保存React模式失败: {e}")
    
    def _save_system_params(self):
        """保存系统参数"""
        param_file = self.config_dir / "system_params.json"
        try:
            with open(param_file, "w", encoding="utf-8") as f:
                json.dump(self.system_params, f, ensure_ascii=False, indent=2)
            logger.info("保存系统参数成功")
        except Exception as e:
            logger.error(f"保存系统参数失败: {e}")
    
    # ==================== 访问方法 ====================
    
    def get_prompt_template(self, template_id: str) -> Optional[PromptTemplate]:
        """获取提示词模板"""
        return self.prompt_templates.get(template_id)
    
    def get_strong_requirements(
        self,
        category: Optional[str] = None,
        min_priority: int = 1
    ) -> List[StrongRequirement]:
        """
        获取强规范要求
        
        Args:
            category: 分类过滤
            min_priority: 最低优先级
            
        Returns:
            强规范要求列表
        """
        reqs = list(self.strong_requirements.values())
        
        if category:
            reqs = [r for r in reqs if r.category == category]
        
        reqs = [r for r in reqs if r.priority >= min_priority]
        
        # 按优先级排序
        reqs.sort(key=lambda x: x.priority, reverse=True)
        
        return reqs
    
    def get_react_pattern(self, pattern_key: str) -> str:
        """获取React模式性提示词"""
        return self.react_patterns.get(pattern_key, "")
    
    def get_system_param(self, param_name: str, default: Any = None) -> Any:
        """获取系统参数"""
        return self.system_params.get(param_name, default)
    
    # ==================== 修改方法 ====================
    
    def add_prompt_template(self, template: PromptTemplate):
        """添加提示词模板"""
        self.prompt_templates[template.id] = template
        self._save_prompt_templates()
        logger.info(f"添加提示词模板: {template.id}")
    
    def add_strong_requirement(self, requirement: StrongRequirement):
        """添加强规范要求"""
        self.strong_requirements[requirement.id] = requirement
        self._save_strong_requirements()
        logger.info(f"添加强规范要求: {requirement.id}")
    
    def update_system_param(self, param_name: str, value: Any):
        """更新系统参数"""
        self.system_params[param_name] = value
        self._save_system_params()
        logger.info(f"更新系统参数: {param_name} = {value}")
    
    def export_config(self, output_file: Path):
        """导出所有配置到单个文件"""
        config_data = {
            "prompt_templates": [asdict(t) for t in self.prompt_templates.values()],
            "strong_requirements": [asdict(r) for r in self.strong_requirements.values()],
            "react_patterns": self.react_patterns,
            "system_params": self.system_params
        }
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"配置已导出到: {output_file}")
    
    def import_config(self, input_file: Path):
        """从文件导入配置"""
        with open(input_file, "r", encoding="utf-8") as f:
            config_data = json.load(f)
        
        # 导入各类配置
        if "prompt_templates" in config_data:
            for item in config_data["prompt_templates"]:
                template = PromptTemplate(**item)
                self.prompt_templates[template.id] = template
        
        if "strong_requirements" in config_data:
            for item in config_data["strong_requirements"]:
                req = StrongRequirement(**item)
                self.strong_requirements[req.id] = req
        
        if "react_patterns" in config_data:
            self.react_patterns.update(config_data["react_patterns"])
        
        if "system_params" in config_data:
            self.system_params.update(config_data["system_params"])
        
        # 保存
        self._save_prompt_templates()
        self._save_strong_requirements()
        self._save_react_patterns()
        self._save_system_params()
        
        logger.info(f"配置已从 {input_file} 导入")


# ================================
# 全局配置管理器实例
# ================================
_config_manager: Optional[WritingConfigManager] = None


def get_config_manager() -> WritingConfigManager:
    """获取全局配置管理器实例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = WritingConfigManager()
    return _config_manager


# ================================
# 测试代码
# ================================
if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 创建配置管理器
    config_mgr = WritingConfigManager()
    
    print("=" * 60)
    print("配置管理器测试")
    print("=" * 60)
    
    # 1. 测试提示词模板
    print("\n【提示词模板】")
    for tid, template in config_mgr.prompt_templates.items():
        print(f"- {tid}: {template.name}")
    
    # 2. 测试强规范要求
    print("\n【强规范要求】")
    reqs = config_mgr.get_strong_requirements(min_priority=4)
    for req in reqs:
        print(f"- [{req.priority}] {req.content}")
    
    # 3. 测试React模式
    print("\n【React模式性提示词】")
    for key, pattern in config_mgr.react_patterns.items():
        print(f"- {key}: {pattern}")
    
    # 4. 测试系统参数
    print("\n【系统参数】")
    for key, value in config_mgr.system_params.items():
        print(f"- {key}: {value}")
    
    print("\n" + "=" * 60)
    print("配置文件已保存到:", config_mgr.config_dir)
