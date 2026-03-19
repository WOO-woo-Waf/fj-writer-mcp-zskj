# 独立写作服务模块

基于 React 框架的法律文书智能写作服务，从主系统中抽离的独立功能模块。

## 目录结构

```
writer-for-fujian/
├── app/
│   ├── core/              # 核心功能模块
│   │   └── llm_client.py  # LLM客户端
│   ├── integrations/      # 外部集成
│   │   ├── mcp_client.py  # MCP法条搜索客户端
│   │   └── bing_search_client.py  # Bing搜索客户端
│   └── services/          # 写作服务模块
│       ├── writing_service.py       # 主服务接口
│       ├── react_writing_engine.py  # React多轮对话引擎
│       ├── content_retriever.py     # 内容检索器
│       └── writing_config_manager.py # 配置管理器
├── config/               # 配置文件目录
│   └── writing/          # 写作服务配置
├── docs/                 # 文档
│   ├── QUICKSTART.md    # 快速开始
│   └── API_REFERENCE.md # API参考
├── examples/             # 示例代码
│   └── demo.py          # 完整示例
├── tests/                # 测试文件
│   └── test_service.py  # 服务测试
├── api.py               # API接口层（待实现）
├── requirements.txt     # 依赖列表
└── README.md           # 本文件
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量（可选）

如果需要使用法条搜索功能：

```bash
export MCP_SSE_URL="your_mcp_service_url"
export MODELSCOPE_KEY="your_api_key"
```

### 3. 运行测试

```bash
python tests/test_service.py
```

### 4. 查看示例

```bash
python examples/demo.py
```

## 核心功能

- ✅ **React多轮对话**：智能推理和工具调用
- ✅ **法条搜索**：集成MCP法律数据库
- ✅ **章节式生成**：按章节逐步生成内容
- ✅ **完全可配置**：所有参数均可配置
- ✅ **可扩展**：易于添加新功能

## API 接口

接口层位于 `api.py`，提供HTTP REST接口（待实现）。

## 使用示例

```python
from app.services.writing_service import write_report

response = await write_report(
    case_material="案件材料...",
    prompt_instruction="生成要求...",
    enable_legal_search=True
)

if response.success:
    print(response.content)
```

## 文档

- [快速开始](docs/QUICKSTART.md)
- [API参考](docs/API_REFERENCE.md)

## 许可证

[根据实际情况填写]
