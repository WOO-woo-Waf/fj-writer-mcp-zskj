# MCP 查询与并发性能改进方案（评审稿）

## 1. 目标与范围

本方案用于评审，先对齐设计，不直接落地全部代码。

目标：
- `get_article`：按明确优先级一次 SQL 命中，避免 Python 多轮 `execute`。
- `search_article`：默认“宽召回 + 强排序”，多关键词采用 OR。
- 连接与并发：降低数据库往返次数，提高高并发稳定性。

范围：
- `mcp-with-law-article/db_connector.py`
- `mcp-with-law-article/server.py`
- （可选）`writer-for-fujian` 对 MCP 的调用策略

---

## 2. 查询语义规范

### 2.1 `get_article` 规范（单次 SQL）

推荐优先级：
1. 标题匹配 + `section_number` 命中
2. 标题匹配 + `content` 命中“第XX条”
3. 标题近似 + `section_number` 命中

实现要求：
- 不允许 Python 逐 candidate 循环多次打库。
- 采用一次查询 + 打分排序（`CASE` 或 score expression）。
- number 输入先标准化为候选集。

条号标准化候选建议：
- 原文
- 去空白
- 阿拉伯数字形式：`15`、`第15条`
- 中文数字形式：`十五`、`第十五条`

### 2.2 `search_article` 规范（默认 MCP 行为）

默认行为：
- `WHERE`：多关键词 OR（宽召回）
- `ORDER BY`：默认 `relevance DESC`
- 若 `sort_by != relevance`：切换到指定排序（`updated_at` / `created_at` / `id`）
- 保留分页

分词规则建议：
- 空格/中英文标点切分
- 去重
- 长度 1 默认丢弃
- 单字白名单（如：`税`、`罪`）可保留
- token 上限 8~10，避免 SQL 过长

---

## 3. SQL 设计建议

### 3.1 `get_article` 一次查询模板（示意）

```sql
SELECT id, title, section_number, content, url, created_at, updated_at,
       (
         CASE
           WHEN section_number = ANY($2) THEN 300
           WHEN section_number ILIKE ANY($3) THEN 220
           WHEN content ILIKE ANY($4) THEN 140
           ELSE 0
         END
         +
         CASE
           WHEN title = $1 THEN 80
           WHEN title ILIKE $5 THEN 40
           ELSE 0
         END
       ) AS score
FROM law_article
WHERE (
      section_number = ANY($2)
   OR section_number ILIKE ANY($3)
   OR content ILIKE ANY($4)
)
AND title ILIKE $5
ORDER BY score DESC, id DESC
LIMIT 1;
```

说明：
- 用 score 保证“先条号、再正文、再标题近似”的可解释优先级。
- 只打一轮 SQL，避免网络往返放大延迟。

### 3.2 `search_article` 宽召回 + 强排序模板（示意）

```sql
SELECT id, title, section_number, content, url, created_at, updated_at,
       (
         (CASE WHEN title ILIKE $1 THEN 1 ELSE 0 END) * 4
         + (CASE WHEN section_number ILIKE $2 THEN 1 ELSE 0 END) * 3
         + (CASE WHEN content ILIKE $3 THEN 1 ELSE 0 END) * 2
         -- token 级别加权（多关键词 OR）
       ) AS relevance
FROM law_article
WHERE (
      (title ILIKE $4 OR section_number ILIKE $5 OR content ILIKE $6)
   OR (title ILIKE $7 OR section_number ILIKE $8 OR content ILIKE $9)
   OR ...
)
ORDER BY relevance DESC, updated_at DESC NULLS LAST, id DESC
LIMIT $N OFFSET $M;
```

---

## 4. 并发与连接模型改进

当前情况：
- 应用层接口是 async 调用链。
- DB connector 使用 `psycopg2`（同步驱动）。

### 方案 A（低风险、快速落地）

保留 `psycopg2`，在服务层将 DB 调用放入线程池执行：
- 工具函数改为 async 包装同步查询（`asyncio.to_thread` 或专用线程池）。
- 调整连接池参数（按实例 CPU 与 QPS 估算）：
  - `minconn`: 2~5
  - `maxconn`: 20~50（视 DB 连接上限）
- 增加查询超时（statement timeout）与慢查询日志。

优点：
- 改造小，兼容现有 SQL 与依赖。

风险：
- 高并发下线程池和连接池都可能成为瓶颈，需要监控配合。

### 方案 B（中风险、中长期）

迁移为 `asyncpg`：
- 数据库 IO 全异步，减少线程切换。
- 配合预编译语句、批量参数更容易做优化。

优点：
- 高并发吞吐更高，尾延迟更稳。

风险：
- 改造范围大（连接管理、参数占位符、类型映射、测试需重做）。

建议路线：
- 先 A 后 B。
- A 稳定后压测，如瓶颈仍明显，再做 B。

---

## 5. 查询次数优化（跨服务）

建议在 writer -> MCP 调用链上新增策略：
- 当 MCP 已支持多关键词 OR 时，优先“一次完整 query 调用”。
- 仅在结果为空或质量低时，再触发关键词并发回退。

收益：
- 降低 MCP 调用数与 DB 压力。
- 降低重复结果去重成本。

---

## 6. 索引建议

推荐增加或确认以下索引：
- `title`：`btree`（前缀/等值）
- `section_number`：`btree` 或 `text_pattern_ops`
- `updated_at` / `created_at` / `id`：排序索引
- 若正文 `ILIKE` 占比较高：
  - `pg_trgm` + GIN（`content gin_trgm_ops`）

注意：
- 纯 `%xxx%` 的 `ILIKE` 对 btree 利用有限，正文字段建议 trigram 索引。

---

## 7. 可观测性与压测

上线前后都需要记录：
- P50 / P95 / P99 延迟
- 每秒查询数
- DB 连接池占用率
- 慢查询数量与 SQL 指纹
- 超时与错误率

压测场景：
- 单关键词
- 多关键词（2/5/10）
- 高频 `get_article`（条号多形态输入）

验收门槛（示例）：
- `search_article` P95 < 300ms（中等数据量）
- `get_article` 单次请求往返 = 1 次 SQL
- 错误率 < 0.1%

---

## 8. 分阶段实施计划

Phase 1（本周）：
- 固化 `get_article` 单次 SQL + 打分排序。
- 固化 `search_article` OR + relevance 默认排序。
- 完成基础索引与 explain 检查。

Phase 2（下周）：
- 引入线程池包装同步 DB 调用。
- 接入慢查询日志与基础指标。
- 做首轮压测并调连接池参数。

Phase 3（可选）：
- 评估迁移 `asyncpg`，并进行 A/B 压测。

---

## 9. 评审确认项（请确认）

请确认以下决策再进入下一轮代码改造：
1. `get_article` score 权重是否按本稿（300/220/140 + 80/40）。
2. token 上限固定 10 还是改为配置项（建议配置化）。
3. 是否立即在 writer 侧改为“优先一次完整 query 调 MCP，失败再回退”。
4. 并发路线是否先走方案 A（psycopg2 + 线程池）。
5. 是否同意引入 `pg_trgm` 索引（需要 DB 扩展权限）。
