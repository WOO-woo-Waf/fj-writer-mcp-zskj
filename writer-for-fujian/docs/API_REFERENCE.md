# 独立写作服务接口

## 概述

独立写作服务是从原系统中抽离出来的专门用于法律文书智能写作的模块。它采用 **React (Reasoning + Acting)** 框架进行多轮对话，集成了法条搜索、内容检索等功能，能够生成高质量的法律文书。

### 核心特点

- ✅ **React多轮对话**：智能推理和工具调用相结合
- ✅ **法条精准搜索**：集成MCP法律数据库
- ✅ **章节式生成**：支持按章节逐步生成，不依赖固定模板
- ✅ **重复性原则**：强规范要求可配置重复出现
- ✅ **完全可配置**：所有参数、提示词、规范要求均可配置
- ✅ **便于扩展**：模块化设计，易于集成和扩展

## 系统架构

```
writing_service.py          # 主接口：WritingService 和 WritingRequest
    ↓
react_writing_engine.py     # React引擎：多轮对话推理
    ↓ (调用工具)
    ├── mcp_client.py       # MCP法条搜索
    ├── content_retriever.py # 内容检索
    └── llm_client.py       # LLM调用
    ↓ (读取配置)
writing_config_manager.py   # 配置管理：模板、规范、参数
```

## 快速开始

### 1. 基础使用

最简单的使用方式是调用便捷函数 `write_report()`：

```python
import asyncio
from app.services.writing_service import write_report

async def main():
    # 案件材料
    case_material = """
    申诉人：张三，男，1985年出生...
    案情简介：2021年5月10日晚...
    一审判决：判处有期徒刑三年...
    申诉理由：1. 证据不足 2. 量刑过重...
    """
    
    # 提示词
    prompt_instruction = """
    请生成刑事申诉审查报告，包括：
    一、申诉人基本情况
    二、案件来源及申诉理由
    三、原审判决认定的事实和法律适用
    四、审查认定的事实
    五、审查意见
    """
    
    # 生成报告
    response = await write_report(
        case_material=case_material,
        prompt_instruction=prompt_instruction,
        enable_legal_search=True,    # 启用法条搜索
        section_mode=True,            # 按章节生成
        max_react_steps=10            # 最大React步数
    )
    
    # 输出结果
    if response.success:
        print(response.content)
        print(f"共生成 {len(response.sections)} 个章节")
    else:
        print(f"生成失败: {response.error}")

asyncio.run(main())
```

### 2. 高级配置

使用 `WritingService` 类和 `WritingConfig` 进行精细化配置：

```python
from app.services.writing_service import WritingService, WritingRequest
from app.services.react_writing_engine import WritingConfig

# 创建自定义配置
config = WritingConfig(
    max_react_steps=15,           # 最大React循环步数
    temperature=0.15,             # LLM温度（越低越确定）
    enable_legal_search=True,     # 启用法条搜索
    enable_content_retrieval=True, # 启用内容检索
    repetition_strategy="strict",  # 重复策略：strict/smart/none
    context_window_limit=10000,   # 上下文窗口限制
    strong_requirements=[         # 强规范要求列表
        "引用法律条文必须准确无误",
        "必须逐一回应所有申诉理由",
        "结论必须有充分证据支持"
    ]
)

# 创建写作请求
request = WritingRequest(
    case_material=case_material,
    prompt_instruction=prompt_instruction,
    config=config,
    section_mode=True
)

# 执行写作
service = WritingService()
response = await service.write(request)
```

### 3. 使用预定义模板

利用配置管理器中的预定义模板：

```python
from app.services.writing_config_manager import get_config_manager

# 获取配置管理器
config_mgr = get_config_manager()

# 使用预定义模板
template = config_mgr.get_prompt_template("criminal_appeal_full")

# 渲染模板
prompt = template.render(
    case_material=case_material,
    special_requirements="必须引用准确法条"
)

# 使用渲染后的提示词进行写作
response = await write_report(case_material, prompt)
```

## 核心模块说明

### WritingService

主接口类，负责接收请求、协调各模块、返回结果。

**主要方法**:
- `write(request: WritingRequest) -> WritingResponse`：执行写作任务

**请求参数** (`WritingRequest`):
- `case_material`: 案件材料（字符串）
- `prompt_instruction`: 提示词（字符串）
- `config`: 写作配置（可选）
- `enable_legal_search`: 是否启用法条搜索
- `enable_content_retrieval`: 是否启用内容检索
- `section_mode`: 是否按章节生成
- `repetition_strategy`: 重复策略
- `min_output_length`: 最小输出长度（字符数，默认 `0`，由调用方控制）

**响应结果** (`WritingResponse`):
- `success`: 是否成功
- `content`: 生成的完整内容
- `sections`: 章节列表（如果使用章节模式）
- `react_steps`: React执行步骤（调试信息）
- `legal_references`: 引用的法条
- `error`: 错误信息（如果失败）

### ReactWritingEngine

React多轮对话引擎，实现 Thought → Action → Observation 循环。

**可用工具**:
1. `search_legal`: 搜索法律条文
2. `get_article`: 获取具体法条
3. `retrieve_content`: 检索相关内容
4. `summarize`: 汇总材料
5. `write_section`: 撰写章节
6. `FINISH`: 完成任务

**工作流程**:
```
用户请求
  ↓
Thought: 分析任务，思考下一步
  ↓
Action: 选择工具执行
  ↓
Observation: 获取工具结果
  ↓
(重复上述步骤)
  ↓
Thought: 任务完成
  ↓
Action: FINISH: 最终内容
```

### WritingConfigManager

配置管理器，管理所有可配置内容。

**管理内容**:
- **提示词模板库**: 预定义的提示词模板
- **强规范要求库**: 必须遵守的规范要求
- **React模式性提示词**: 指导React循环的提示
- **系统参数**: 各种系统级参数

**主要方法**:
```python
config_mgr = get_config_manager()

# 获取提示词模板
template = config_mgr.get_prompt_template("criminal_appeal_full")

# 获取强规范要求
requirements = config_mgr.get_strong_requirements(category="criminal", min_priority=4)

# 获取系统参数
max_steps = config_mgr.get_system_param("max_react_steps", default=10)

# 添加自定义要求
config_mgr.add_strong_requirement(StrongRequirement(
    id="custom_req_1",
    content="自定义规范要求",
    priority=5
))
```

## 配置文件

配置文件位于 `config/writing/` 目录：

```
config/writing/
├── prompt_templates.json      # 提示词模板
├── strong_requirements.json   # 强规范要求
├── react_patterns.json        # React模式
└── system_params.json         # 系统参数
```

### 提示词模板示例

```json
{
  "id": "criminal_appeal_full",
  "name": "刑事申诉完整报告",
  "description": "生成完整的刑事申诉审查报告",
  "template": "请根据以下案件材料生成报告...\n{case_material}\n{special_requirements}",
  "variables": ["case_material", "special_requirements"],
  "category": "criminal"
}
```

### 强规范要求示例

```json
{
  "id": "accurate_legal_citation",
  "content": "引用法律条文必须准确无误，不得编造或曲解法律规定",
  "priority": 5,
  "category": "legal",
  "repeat_frequency": "always"
}
```

## 重复性原则

系统支持三种重复策略，用于处理强规范要求的重复：

1. **`strict`（严格）**: 强规范要求在每个关键环节都重复出现
2. **`smart`（智能）**: 根据优先级和上下文智能决定是否重复
3. **`none`（无）**: 只在初始提示中出现一次

配置示例：
```python
config = WritingConfig(
    repetition_strategy="smart",
    strong_requirements=[
        "引用法律条文必须准确",
        "必须逐一回应申诉理由"
    ]
)
```

## 章节生成模式

### 章节模式 (`section_mode=True`)

系统会：
1. 解析提示词中的章节结构（如"一、""二、"等）
2. 为每个章节独立进行React推理和生成
3. 最后汇总所有章节

优点：
- 更细粒度的控制
- 每个章节独立调试
- 避免内容遗漏

### 直接模式 (`section_mode=False`)

系统一次性生成完整内容。

优点：
- 生成速度更快
- 内容更连贯

## API接口示例

如果要将写作服务封装成HTTP接口：

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class ReportRequest(BaseModel):
    case_material: str
    prompt_instruction: str
    enable_legal_search: bool = True
    section_mode: bool = True

@app.post("/api/write")
async def write_report_api(request: ReportRequest):
    """写作接口"""
    response = await write_report(
        case_material=request.case_material,
        prompt_instruction=request.prompt_instruction,
        enable_legal_search=request.enable_legal_search,
        section_mode=request.section_mode
    )
    
    return {
        "success": response.success,
        "content": response.content,
        "sections": response.sections,
        "error": response.error
    }
```

调用示例：
```bash
curl -X POST "http://localhost:8000/api/write" \
  -H "Content-Type: application/json" \
  -d '{
    "case_material": "案件材料...",
    "prompt_instruction": "生成报告要求..."
  }'
```

## 运行示例

项目包含完整的示例代码：

```bash
# 运行完整示例
python examples/writing_service_demo.py

# 运行单个示例
python -c "from examples.writing_service_demo import example_basic; import asyncio; asyncio.run(example_basic())"
```

示例包括：
1. 基础使用示例
2. 高级配置示例
3. 模板使用示例
4. 纯写作模式示例（无法条搜索）

## 扩展和自定义

### 添加自定义工具

在 `ReactWritingEngine` 中添加新工具：

```python
async def _tool_custom_analysis(self, query: str, context: str) -> str:
    """自定义分析工具"""
    # 实现自定义逻辑
    return "分析结果..."

# 在 _register_tools 中注册
self.tools["custom_analysis"] = self._tool_custom_analysis
```

### 添加自定义检索源

继承 `ContentRetriever` 并实现新的检索方法：

```python
class CustomRetriever(ContentRetriever):
    async def _retrieve_custom_source(self, query: str):
        """自定义检索源"""
        # 实现检索逻辑
        return results
```

### 添加自定义提示词模板

```python
from app.services.writing_config_manager import get_config_manager, PromptTemplate

config_mgr = get_config_manager()

custom_template = PromptTemplate(
    id="my_custom_template",
    name="自定义模板",
    description="用于特定场景",
    template="模板内容: {var1} {var2}",
    variables=["var1", "var2"],
    category="custom"
)

config_mgr.add_prompt_template(custom_template)
```

## 注意事项

1. **法条搜索**：需要配置MCP服务的URL和API Key（环境变量 `MCP_SSE_URL` 和 `MODELSCOPE_KEY`）
2. **LLM配置**：确保 `LLMClient` 已正确配置（API Key、模型名称等）
3. **上下文长度**：注意控制 `context_window_limit`，避免超出模型限制
4. **React步数**：`max_react_steps` 不宜过大，通常10-15步足够

## 性能优化建议

1. **并发处理**：多个章节可以并发生成（需修改代码）
2. **缓存法条**：对常用法条进行缓存
3. **提示词优化**：精炼提示词，减少不必要的Token消耗
4. **分级生成**：先生成大纲，再逐步细化

## 故障排查

### 问题1：无法连接MCP服务

检查环境变量配置：
```bash
echo $MCP_SSE_URL
echo $MODELSCOPE_KEY
```

### 问题2：生成内容不符合要求

1. 调整强规范要求和重复策略
2. 增加 `max_react_steps`
3. 优化提示词描述

### 问题3：上下文超长

1. 减小 `context_window_limit`
2. 启用章节模式，减少单次生成的内容量

## 更新日志

### v1.0.0 (2026-03-02)
- ✅ 初始版本发布
- ✅ 实现React多轮对话框架
- ✅ 集成MCP法条搜索
- ✅ 支持章节式生成
- ✅ 完整的配置管理系统
- ✅ 重复性原则支持

## 许可证

[根据项目实际情况填写]

## 联系方式

[根据项目实际情况填写]
