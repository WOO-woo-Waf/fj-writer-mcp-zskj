# 独立写作服务 - 快速入门

## 5分钟快速开始

### 步骤1：确认环境

确保已安装必要的依赖：
```bash
pip install -r requirements.txt
```

### 步骤2：配置环境变量（可选）

如果需要使用法条搜索功能，配置MCP服务：
```bash
export MCP_SSE_URL="your_mcp_service_url"
export MODELSCOPE_KEY="your_api_key"
```

### 步骤3：运行第一个示例

```python
# test_writing.py
import asyncio
from app.services.writing_service import write_report

async def main():
    # 案件材料
    case_material = """
    申诉人：张三，男，1985年出生，涉嫌盗窃罪。
    一审判决：有期徒刑三年。
    申诉理由：证据不足，量刑过重。
    """
    
    # 提示词
    prompt = """
    请生成审查报告，包括：
    一、基本情况
    二、申诉理由
    三、审查意见
    """
    
    # 生成报告
    response = await write_report(
        case_material=case_material,
        prompt_instruction=prompt,
        enable_legal_search=True,
        section_mode=True
    )
    
    if response.success:
        print("生成成功！")
        print(response.content)
    else:
        print(f"失败: {response.error}")

asyncio.run(main())
```

运行：
```bash
python test_writing.py
```

## 使用场景

### 场景1：生成完整刑事申诉报告

```python
response = await write_report(
    case_material="案件材料...",
    prompt_instruction="生成刑事申诉审查报告，包括五个章节...",
    enable_legal_search=True,    # 启用法条搜索
    section_mode=True,            # 按章节生成
    max_react_steps=10
)
```

### 场景2：生成单一分析意见

```python
response = await write_report(
    case_material="案件材料...",
    prompt_instruction="针对申诉理由进行分析，提出审查意见",
    enable_legal_search=True,
    section_mode=False,           # 直接生成，不分章节
    max_react_steps=5
)
```

### 场景3：不使用法条搜索的纯写作

```python
response = await write_report(
    case_material="事故案情...",
    prompt_instruction="撰写事实认定报告",
    enable_legal_search=False,    # 关闭法条搜索
    section_mode=False
)
```

## 通过HTTP API调用

### 启动API服务器

```bash
python api_server.py
```

访问 http://localhost:8000/docs 查看交互式API文档。

### 调用示例

```bash
curl -X POST "http://localhost:8000/api/v1/write" \
  -H "Content-Type: application/json" \
  -d '{
    "case_material": "申诉人：张三...",
    "prompt_instruction": "请生成审查报告...",
    "enable_legal_search": true,
    "section_mode": true
  }'
```

或使用Python requests：

```python
import requests

response = requests.post(
    "http://localhost:8000/api/v1/write",
    json={
        "case_material": "案件材料...",
        "prompt_instruction": "生成要求...",
        "enable_legal_search": True,
        "section_mode": True
    }
)

result = response.json()
if result["success"]:
    print(result["content"])
```

## 核心参数说明

| 参数 | 类型 | 默认值 | 说明 |
|-----|------|--------|------|
| `case_material` | str | 必填 | 案件材料 |
| `prompt_instruction` | str | 必填 | 提示词指令 |
| `enable_legal_search` | bool | True | 是否启用法条搜索 |
| `enable_content_retrieval` | bool | False | 是否启用内容检索 |
| `section_mode` | bool | True | 是否按章节生成 |
| `max_react_steps` | int | 10 | 最大React步数 |
| `temperature` | float | 0.2 | LLM温度参数 |
| `repetition_strategy` | str | "smart" | 重复策略 |

## 高级配置

### 使用自定义配置

```python
from app.services.writing_service import WritingService, WritingRequest
from app.services.react_writing_engine import WritingConfig

# 创建配置
config = WritingConfig(
    max_react_steps=15,
    temperature=0.15,
    strong_requirements=[
        "引用法律条文必须准确",
        "必须逐一回应所有申诉理由"
    ]
)

# 创建请求
request = WritingRequest(
    case_material=case_material,
    prompt_instruction=prompt,
    config=config
)

# 执行
service = WritingService()
response = await service.write(request)
```

### 使用预定义模板

```python
from app.services.writing_config_manager import get_config_manager

config_mgr = get_config_manager()
template = config_mgr.get_prompt_template("criminal_appeal_full")

prompt = template.render(
    case_material=case_material,
    special_requirements="强规范要求..."
)

response = await write_report(case_material, prompt)
```

## 运行完整示例

项目包含多个示例：

```bash
# 运行所有示例
python examples/writing_service_demo.py

# 测试配置管理器
python app/services/writing_config_manager.py

# 测试内容检索器
python app/services/content_retriever.py
```

## 常见问题

**Q: 如何修改强规范要求？**

A: 编辑配置文件 `config/writing/strong_requirements.json` 或使用代码：
```python
from app.services.writing_config_manager import get_config_manager, StrongRequirement

config_mgr = get_config_manager()
config_mgr.add_strong_requirement(StrongRequirement(
    id="my_requirement",
    content="自定义要求",
    priority=5
))
```

**Q: 如何调试React执行过程？**

A: 在响应中查看 `react_steps` 字段：
```python
response = await write_report(...)
for step in response.react_steps:
    print(f"Step {step['step']}: {step['thought']}")
    print(f"Action: {step['action']}")
```

**Q: 生成的内容不符合预期怎么办？**

A: 
1. 调整提示词，使其更具体明确
2. 增加强规范要求
3. 调整 `repetition_strategy` 为 "strict"
4. 增加 `max_react_steps`

**Q: 如何禁用法条搜索？**

A: 设置 `enable_legal_search=False`：
```python
response = await write_report(
    case_material=case_material,
    prompt_instruction=prompt,
    enable_legal_search=False
)
```

## 下一步

- 📖 阅读完整文档：[docs/services/WRITING_SERVICE.md](../docs/services/WRITING_SERVICE.md)
- 🔧 查看API接口文档：运行 `python api_server.py` 后访问 http://localhost:8000/docs
- 💡 查看更多示例：[examples/writing_service_demo.py](../examples/writing_service_demo.py)

## 技术支持

如有问题，请查看：
- 完整文档：`docs/services/WRITING_SERVICE.md`
- 示例代码：`examples/writing_service_demo.py`
- 配置说明：配置文件位于 `config/writing/`
