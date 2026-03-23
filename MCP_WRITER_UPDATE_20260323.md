# MCP + Writer 功能更新说明（2026-03-23）

---

## 2. 本次功能更新

### 2.1 MCP（mcp-with-law-article）

1. `get_article`：
- 改为单次 SQL 打分排序，不再 Python 循环多次 `execute`。
- 条号标准化增强（原文/去空白/阿拉伯/中文）。
- 优先级：`section_number` 命中 > `content` 命中 > 标题近似加权。

2. `search_article`：
- 多关键词改为 OR 召回。
- 默认 `relevance desc`。
- `sort_by != relevance` 时切换字段排序。

3. 配置化：
- 连接池与超时：
  - `pool_minconn` / `pool_maxconn` / `statement_timeout_ms`
- 分词与权重：
  - `token_limit` / `token_min_length` / `single_char_whitelist`
  - `phrase_*_weight` / `token_*_weight`
- `get_article` 权重：
  - `get_article_*_weight`

4. 并发模型（方案 A）：
- MCP tool 改为 async。
- 同步 psycopg2 查询放入线程池执行，避免阻塞事件循环。

### 2.2 Writer（writer-for-fujian）

1. 法条检索策略更新：
- 先整句查询（primary query）。
- 主查询命中不足时才触发分词回退。
- 回退阶段并发检索并做并集去重。

2. 新增请求级可配置参数：
- `legal_search_page_size`
- `legal_search_fallback_enabled`
- `legal_search_fallback_min_results`
- `legal_search_candidate_limit`
- `legal_search_token_min_length`
- `legal_search_single_char_whitelist`

---

## 3. 受影响文件

- `mcp-with-law-article/config.ini`
- `mcp-with-law-article/db_connector.py`
- `mcp-with-law-article/server.py`
- `writer-for-fujian/app/services/react_writing_engine.py`
- `writer-for-fujian/api.py`
- `API.md`

---

## 4. 验证建议（避免再被 Dummy 误导）

### 4.1 验证真实 MCP 返回（不要用 DummyMCP）

```bash
docker compose exec -T writer-service python - <<'PY'
import asyncio
from app.integrations.mcp_client import LegalMCPClient

async def main():
    client = LegalMCPClient()
    rows = await client.search_article('盗窃 诈骗', page=1, page_size=5)
    print('count', len(rows))
    for i, r in enumerate(rows[:3], 1):
        print(i, r.get('id'), r.get('title'), r.get('section_number'))
        print('   content_head=', (r.get('content') or '')[:40])

asyncio.run(main())
PY
```

### 4.2 验证 mcp-service 直连 DB

```bash
docker compose exec -T mcp-service python - <<'PY'
from db_connector import LegalDatabaseConnector

db = LegalDatabaseConnector('config.ini')
db.connect()
rows = db.search_articles('盗窃 诈骗', page=1, page_size=5)
print('count', len(rows))
for i, r in enumerate(rows[:3], 1):
    print(i, r.get('id'), r.get('title'), r.get('section_number'))
    print('   content_head=', (r.get('content') or '')[:40])
PY
```

若两边前三条 `id/title/section_number` 一致，说明 writer->MCP->DB 链路正确。

---

## 5. MCP 工具是否要给模型介绍和提示词

结论：要，而且建议明确到“调用策略 + 参数格式 + 何时调用”。

建议放在系统提示词中包含：

1. 工具能力介绍：
- `search_legal`：关键词检索法条（支持多关键词）
- `get_article`：按法规标题+条号拉取具体条文

2. 调用策略：
- 先 `search_legal` 做召回
- 再按需要用 `get_article` 拉精确条文
- 无法律依据需求时可不调用，避免噪声

3. 参数规范：
- `search_legal`：自然语言关键词（可多关键词）
- `get_article`：`法规名称|条号`（如 `刑法|第264条`）

4. 输出规范：
- 正文引用使用 `[法条ID:xxx]`
- 禁止编造法条内容

当前项目里这部分已存在基础版本，但可继续加强“何时调用/何时不调用”的约束文本。

---

## 6. 注意事项

- 用 `DummyMCP` 只能验证流程分支，不能验证数据正确性。
- 若要验证“数据库内容是否正确”，必须用真实 `LegalMCPClient` 或 `mcp-service` 直连查询。
- 目前未启用 `pg_trgm` 索引（按你的决策先不做）。
