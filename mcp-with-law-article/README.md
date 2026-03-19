# MCP Legal Article Service

## 目录结构

```
mcp/
├── __init__.py           # 包初始化
├── db_connector.py       # 数据库连接与查询
├── server.py             # FastMCP 服务入口
├── client.py             # 异步客户端（用于调用服务）
├── run_server.py         # 服务启动脚本
├── test_client.py        # 完整测试套件
└── README.md             # 本文件
```

## 快速开始

### 1. 安装依赖

```bash
pip install mcp psycopg2-binary httpx
```

### 2. 配置数据库

编辑 `config.ini`，确保以下配置存在：

```ini
[database]
host = 39.103.56.106
port = 15432
user = root
password = Bzfurniture@2025
database = fj_report_test

[tables]
law_article = law_article
```

### 3. 启动服务

```bash
python mcp/run_server.py
```

或直接运行（从项目根目录）：

```bash
python -m mcp.server
```

默认服务地址：`http://127.0.0.1:8000/sse`

### 4. 运行测试

在新终端窗口中：

```bash
python mcp/test_client.py
```

## 使用文档

### 服务端（server.py）

提供两个主要工具：

#### `get_article(number, title)` - 精确查询

- **参数**
  - `number`: 法条条号，如 `"第264条"`
  - `title`: 法规名称，如 `"刑法"`

- **返回**：包含以下字段的字典
  ```python
  {
      "id": 123,
      "title": "刑法",
      "section_number": "第264条",
      "content": "盗窃罪的定义...",
      "url": "https://...",
      "created_at": "2025-01-01T00:00:00",
      "updated_at": "2025-02-24T00:00:00"
  }
  ```

#### `search_article(text, page, page_size, sort_by, order)` - 模糊搜索

- **参数**
  - `text` (必填): 搜索关键词，如 `"盗窃罪数额标准"`
  - `page` (可选): 页码，从 1 开始，默认 1；支持 `int` 或数字字符串（如 `1` / `"1"`）
  - `page_size` (可选): 每页条数，1-100，默认 10；支持 `int` 或数字字符串（如 `10` / `"10"`）
  - `sort_by` (可选): 排序字段
    - `"relevance"` (默认): 按相关度排序
    - `"updated_at"`: 按更新时间排序
    - `"created_at"`: 按创建时间排序
    - `"id"`: 按 ID 排序
  - `order` (可选): 排序顺序，`"asc"` 或 `"desc"`（默认 `"desc"`）

- **返回**：文章列表，每个包含同上字段 + `relevance`（相关度分数）

> 说明：`search_article` 的检索与排序由数据库 SQL 直接执行（`ILIKE` + `ORDER BY` + `LIMIT/OFFSET`），MCP 层只做参数透传与基础归一化。

## MCP 使用提示词（可直接复制）

你是法律检索助手，请按以下要求调用 MCP 工具并输出结果。

1. 使用方式：
- 明确指定操作目标（`get_article` 或 `search_article`）
- 包含具体参数要求（关键词、页码、每页条数、排序字段、顺序）
- 说明预期输出格式（JSON 列表/字典，需包含 `title`、`section_number`、`content` 摘要、`url`）

2. 搜索方法：
- 使用关键词组合（主题词 + 行为词 + 约束词）
- 限定搜索范围（法规名称、条号区间、时间相关字段）
- 添加筛选条件（分页、排序、是否仅返回前 N 条）

输出要求：
- 先给出调用参数
- 再返回结构化结果
- 最后给出 1-2 句结论摘要

### 客户端（client.py）

异步图客户端，支持 SSE 连接：

```python
import asyncio
from mcp.client import LegalMCPClient

async def main():
    client = LegalMCPClient(
        sse_url="http://127.0.0.1:8000/sse",  # 可选，默认此地址
        api_key=None  # 如果需要鉴权
    )
    
    # 获取单个法条
    article = await client.get_article("第264条", "刑法")
    print(article)
    
    # 搜索法条
    results = await client.search_article(
        "盗窃罪",
        page=1,
        page_size=20,
        sort_by="updated_at",
        order="desc"
    )
    print(results)

asyncio.run(main())
```

### 测试脚本（test_client.py）

包含 6 个完整测试用例：

1. **test_list_tools** - 列出可用工具
2. **test_get_article** - 获取单个法条
3. **test_search_basic** - 基础搜索
4. **test_search_with_sort** - 各种排序选项
5. **test_search_pagination** - 分页测试
6. **test_search_multiple_keywords** - 多关键词测试

运行方式：

```bash
# 直接运行
python mcp/test_client.py

# 或使用 pytest
pip install pytest
pytest mcp/test_client.py -v
```

## 完整工作流示例

### 终端 1：启动服务

```bash
cd d:\buff\fujian-bfs-dag-mcp
python mcp/run_server.py
```

输出：

```
╔══════════════════════════════════════════════════════════════════════════════╗
║               Legal Article MCP Server - FastMCP                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

📋 Configuration:
  Config file: config.ini
  Server: 127.0.0.1:8000

🚀 Starting server...

Server running on 127.0.0.1:8000
```

### 终端 2：运行测试

```bash
cd d:\buff\fujian-bfs-dag-mcp
python mcp/test_client.py
```

输出示例：

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                    Legal Article MCP Test Suite                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

================================================================================
TEST: List Available Tools
================================================================================
✓ Found 2 tools:
  - get_article: Get a single article by section number and law title.
  - search_article: Search articles by keyword with pagination and sorting.

================================================================================
TEST: Get Specific Article
================================================================================
Query: section=第264条, law=刑法
✓ Found article:
  ID: 42
  Title: 刑法
  Section: 第264条
  Content (first 100 chars): 盗窃罪。有下列情形之一，拿取他人财产...
  URL: https://...
  Updated: 2025-02-20T10:30:00

...

================================================================================
TEST SUMMARY
================================================================================
✓ Passed: 6/6
  ✓ list_tools
  ✓ get_article
  ✓ search_basic
  ✓ search_sort
  ✓ pagination
  ✓ keywords
================================================================================
```

## 工作原理

### 连接池

- **最小连接数**: 1
- **最大连接数**: 5
- 自动复用，提升吞吐量
- 连接参数变化时自动重建

### 相关度排序

搜索结果按以下权重计算相关度分数：

- `title` 中匹配：权重 3
- `section_number` 中匹配：权重 2
- `content` 中匹配：权重 1

例：一条在 title 和 content 中都匹配的结果，相关度 = 3 + 1 = 4

### 分页机制

- 页码从 1 开始
- 每页 1-100 条
- 公式：`OFFSET = (page - 1) * page_size`

## 常见问题

**Q: 如何修改服务端口？**
A: 修改 `run_server.py` 中的参数或使用启动脚本的 `--port` 选项

**Q: 如何设置最大连接数？**
A: 编辑 `db_connector.py` 中 `SimpleConnectionPool` 的 `maxconn` 参数

**Q: 搜索不到结果怎么办？**
A: 
- 检查数据库连接是否正常：查看日志中的连接提示
- 检查表名是否在 `config.ini` 中正确配置
- 检查搜索关键词是否真的存在于数据库
- 尝试扩大关键词范围

**Q: 如何在生产环境中运行？**
A: 建议使用 systemd/PM2 等进程管理工具启动 `run_server.py`

## 架构设计

```
Client (client.py)
  ↓ (SSE)
FastMCP Server (server.py)
  ↓ (呼叫工具)
连接池 (db_connector.py)
  ↓ (复用连接)
PostgreSQL Database
```

- **解耦**：数据库逻辑与 MCP 工具分离
- **可复用**：连接池实现 0 连接建立开销
- **可测试**：完整测试套件验证端到端功能

## 下一步（可选）

1. 添加全文检索（PostgreSQL tsvector）以提升搜索性能
2. 实现缓存层（Redis）减少数据库查询
3. 添加法律分类/标签聚合功能
4. 支持高级查询（日期范围、字段筛选等）
