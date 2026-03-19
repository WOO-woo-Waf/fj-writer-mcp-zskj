# 写作服务部署和使用指南

## 目录结构说明

```
writer-for-fujian/
├── app/                         # 应用代码
│   ├── config/                  # 配置模块
│   │   └── settings.py          # 配置管理
│   ├── core/                    # 核心模块
│   │   └── llm_client.py        # LLM客户端
│   ├── integrations/            # 外部集成
│   │   ├── mcp_client.py        # MCP法条搜索
│   │   └── bing_search_client.py # Bing搜索
│   └── services/                # 服务层（核心功能）
│       ├── writing_service.py   # 主服务接口
│       ├── react_writing_engine.py # React引擎
│       ├── content_retriever.py # 内容检索
│       └── writing_config_manager.py # 配置管理
├── config/                      # 配置文件目录（运行时生成）
│   └── writing/                 # 写作服务配置
├── docs/                        # 文档
│   ├── QUICKSTART.md           # 快速开始
│   └── API_REFERENCE.md        # API参考
├── examples/                    # 示例代码
│   └── demo.py                 # 完整示例
├── tests/                       # 测试
│   └── test_service.py         # 服务测试
├── api.py                       # API接口层（待实现）
├── requirements.txt             # Python依赖
├── .env.example                # 环境变量示例
└── README.md                   # 说明文档
```

## 部署步骤

### 1. 环境准备

**Python版本要求**: Python 3.8+

**创建虚拟环境**:
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

复制`.env.example`为`.env`并编辑：

```bash
cp .env.example .env
```

编辑`.env`文件：
```ini
# 必填：LLM API配置
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-your-actual-api-key
LLM_MODEL=gpt-4
LLM_TIMEOUT=120

# 可选：MCP法条搜索
MCP_SSE_URL=your-mcp-url
MODELSCOPE_KEY=your-key
```

### 4. 测试服务

运行测试脚本验证安装：

```bash
python tests/test_service.py
```

如果所有测试通过，说明服务运行正常。

### 5. 运行示例

```bash
python examples/demo.py
```

## 使用方式

### 方式1: Python直接调用

```python
import asyncio
from app.services.writing_service import write_report

async def main():
    response = await write_report(
        case_material="案件材料...",
        prompt_instruction="生成要求...",
        enable_legal_search=True,
        section_mode=True
    )
    
    if response.success:
        print(response.content)
    else:
        print(f"错误: {response.error}")

asyncio.run(main())
```

### 方式2: HTTP API接口（需实现）

#### 启动API服务器

```bash
python api.py
```

访问 http://localhost:8000/docs 查看接口文档。

#### 实现API接口

打开`api.py`，按照TODO注释实现：

1. 取消注释导入语句：
```python
from app.services.writing_service import WritingService, WritingRequest
from app.services.react_writing_engine import WritingConfig
```

2. 在`write_report`函数中实现逻辑：
```python
# 构建配置
config = WritingConfig(
    max_react_steps=request.max_react_steps,
    temperature=request.temperature,
    # ... 其他配置
)

# 创建请求
writing_request = WritingRequest(
    case_material=request.case_material,
    prompt_instruction=request.prompt_instruction,
    config=config
)

# 执行写作
service = WritingService()
response = await service.write(writing_request)

# 返回结果
return WriteReportResponse(
    success=response.success,
    content=response.content,
    sections=response.sections,
    error=response.error
)
```

#### 调用API

```bash
curl -X POST "http://localhost:8000/api/write" \
  -H "Content-Type: application/json" \
  -d '{
    "case_material": "案件材料...",
    "prompt_instruction": "生成要求...",
    "enable_legal_search": true
  }'
```

或使用Python requests:

```python
import requests

response = requests.post(
    "http://localhost:8000/api/write",
    json={
        "case_material": "案件材料...",
        "prompt_instruction": "生成要求..."
    }
)

result = response.json()
if result["success"]:
    print(result["content"])
```

## 配置管理

### 提示词模板

配置文件位于 `config/writing/prompt_templates.json`。

首次运行时自动生成，可手动编辑添加自定义模板：

```json
{
  "id": "my_template",
  "name": "我的模板",
  "description": "自定义模板",
  "template": "根据{case_material}生成{output_type}",
  "variables": ["case_material", "output_type"],
  "category": "custom"
}
```

### 强规范要求

配置文件位于 `config/writing/strong_requirements.json`。

添加自定义强规范要求：

```json
{
  "id": "custom_requirement",
  "content": "自定义规范要求内容",
  "priority": 5,
  "category": "general",
  "repeat_frequency": "always"
}
```

### 系统参数

配置文件位于 `config/writing/system_params.json`。

可修改默认参数：

```json
{
  "max_react_steps": 10,
  "temperature": 0.2,
  "context_window_limit": 8000,
  "enable_legal_search": true,
  "enable_content_retrieval": false,
  "repetition_strategy": "smart",
  "section_mode": true
}
```

## 功能扩展

### 添加自定义工具

编辑 `app/services/react_writing_engine.py`：

```python
async def _tool_custom_analysis(self, query: str, context: str) -> str:
    """自定义分析工具"""
    # 实现自定义逻辑
    return "分析结果..."

# 在 _register_tools 中注册
def _register_tools(self):
    self.tools = {
        # ... 现有工具
        "custom_analysis": self._tool_custom_analysis
    }
```

### 添加自定义检索源

继承 `ContentRetriever` 类：

```python
from app.services.content_retriever import ContentRetriever

class CustomRetriever(ContentRetriever):
    async def _retrieve_custom_source(self, query: str):
        """自定义检索源"""
        # 实现检索逻辑
        return results
```

## 常见问题

### Q1: 如何更换LLM模型？

修改`.env`文件中的`LLM_MODEL`参数，或在代码中指定：

```python
from app.core.llm_client import LLMClient

client = LLMClient(model="gpt-3.5-turbo")
```

### Q2: 如何禁用法条搜索？

在调用时设置 `enable_legal_search=False`：

```python
response = await write_report(
    case_material=case_material,
    prompt_instruction=prompt,
    enable_legal_search=False  # 禁用法条搜索
)
```

### Q3: 生成内容不符合要求怎么办？

1. 优化提示词，使其更具体明确
2. 在配置中添加强规范要求
3. 调整 `repetition_strategy` 为 "strict"
4. 增加 `max_react_steps` 允许更多推理步骤

### Q4: 如何查看React执行过程？

在响应中查看 `react_steps`：

```python
response = await write_report(...)
for step in response.react_steps:
    print(f"Step {step['step']}: {step['thought']}")
    print(f"Action: {step['action']}")
    print(f"Observation: {step['observation']}")
```

### Q5: 如何处理长文档？

1. 启用章节模式 `section_mode=True`
2. 调整 `context_window_limit` 控制上下文长度
3. 分段处理，多次调用

## 性能优化

### 1. 并发处理

对于多个章节，可以并发生成（需修改代码）：

```python
import asyncio

tasks = [
    write_report(material, prompt1),
    write_report(material, prompt2),
    write_report(material, prompt3)
]

results = await asyncio.gather(*tasks)
```

### 2. 缓存策略

对于重复的法条查询，可以实现缓存：

```python
from functools import lru_cache

@lru_cache(maxsize=100)
async def cached_legal_search(query: str):
    # 法条搜索逻辑
    pass
```

### 3. 批量处理

处理大量案件时，使用批量接口：

```python
async def batch_write(cases: List[Dict]):
    results = []
    for case in cases:
        result = await write_report(
            case_material=case['material'],
            prompt_instruction=case['prompt']
        )
        results.append(result)
    return results
```

## 监控和日志

### 日志配置

在代码中配置日志级别：

```python
import logging

logging.basicConfig(
    level=logging.INFO,  # DEBUG, INFO, WARNING, ERROR
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('writing_service.log'),
        logging.StreamHandler()
    ]
)
```

### 性能监控

记录每次请求的性能指标：

```python
import time

start_time = time.time()
response = await write_report(...)
elapsed_time = time.time() - start_time

print(f"生成耗时: {elapsed_time:.2f}秒")
print(f"React步骤数: {len(response.react_steps)}")
print(f"内容长度: {len(response.content)}")
```

## 安全建议

1. **API Key保护**: 不要将`.env`文件提交到版本控制系统
2. **访问控制**: 在生产环境中添加身份验证和授权
3. **输入验证**: 对用户输入进行严格验证
4. **速率限制**: 实现API速率限制防止滥用
5. **日志脱敏**: 不要在日志中记录敏感信息

## 生产部署

### 使用Docker部署

创建 `Dockerfile`:

```dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "api.py"]
```

构建和运行：

```bash
docker build -t writing-service .
docker run -p 8000:8000 --env-file .env writing-service
```

### 使用Supervisor管理

创建 `supervisor.conf`:

```ini
[program:writing-service]
command=/path/to/venv/bin/python api.py
directory=/path/to/writer-for-fujian
autostart=true
autorestart=true
stderr_logfile=/var/log/writing-service.err.log
stdout_logfile=/var/log/writing-service.out.log
```

### 使用Nginx反向代理

```nginx
server {
    listen 80;
    server_name your-domain.com;
    docker compose logs -f writer-service    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 技术支持

- 查看文档: `docs/QUICKSTART.md` 和 `docs/API_REFERENCE.md`
- 运行示例: `python examples/demo.py`
- 运行测试: `python tests/test_service.py`
- 查看API文档: 运行 `python api.py` 后访问 http://localhost:8000/docs
