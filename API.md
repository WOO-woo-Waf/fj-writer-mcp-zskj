# API 文档

本文档仅面向接口调用方，说明：
- 调哪个接口
- 传什么参数
- 会返回什么

默认地址（docker-compose）：
- MCP 服务：`http://localhost:11452`
- 写作服务：`http://localhost:11453`

---

## 1. 写作服务（HTTP）

### 1.1 健康检查

- 方法：`GET`
- 路径：`/health`
- 完整地址：`http://localhost:11453/health`

返回示例：

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "services": {
    "writing_service": "ready",
    "react_engine": "ready",
    "llm_client": "configured"
  }
}
```

---

### 1.2 同步写作

- 方法：`POST`
- 路径：`/api/write`
- 完整地址：`http://localhost:11453/api/write`
- Content-Type：`application/json`

请求参数：
- 必填：
  - `case_material` (string)：案件材料全文
  - `prompt_instruction` (string)：写作指令
- 常用可选：
  - `enable_legal_search` (bool，默认 `true`)：
    是否启用法条检索（通过 MCP 获取法条后参与写作）。当前生效。
  - `enable_content_retrieval` (bool，默认 `false`)：
    是否启用内容检索增强。参数在流程中已接入，但当前默认部署通常没有完整检索后端，开启后可能无额外检索结果；属于历史设计保留能力。
  - `section_mode` (bool，默认 `false`)：
    是否按章节生成。当前版本为兼容保留参数，服务统一走“直接生成完整报告”流程，传 `true` 不改变主流程。
  - `max_react_steps` (int，默认 `10`，范围 `1-30`)：
    最大推理轮次。数值越大，通常推理更充分但耗时更高。当前生效。
  - `temperature` (float，默认 `0.2`，范围 `0-2`)：
    模型采样温度，越低越稳定，越高越发散。当前生效。
  - `repetition_strategy` (`smart|strict|none`，默认 `smart`)：
    去重/防重复策略。当前生效，三种模式代码里有实际分支：
    - `smart`：在初始提示中注入强规范要求，平衡约束与自然性。
    - `strict`：在 `smart` 基础上，在写作阶段再次强化强规范要求，约束更强。
    - `none`：不做上述重复强化。
    说明：如果未传 `strong_requirements`，`smart` 和 `strict` 的差异会明显变小，看起来可能接近“无效果”。
  - `strong_requirements` (string[])：
    强约束要求列表（例如格式、引用、语气等），会注入生成约束。当前生效。
  - `context_window_limit` (int，默认 `128000`)：
    上下文窗口上限，用于控制提示与上下文拼接长度。当前生效。
  - `multi_turn_enabled` (bool，默认 `true`)：
    多轮对话开关。当前属于兼容保留参数，现有主流程中暂未形成明显行为差异。
  - `proactive_tool_call` (bool，默认 `true`)：
    是否允许模型在推理中主动触发工具调用（主要是法条检索）。当前生效。
  - `min_output_length` (int，默认 `0`，最小值 `0`)：
    最小输出长度（按字符数计）。`0` 表示不启用最小长度约束，完全由调用方控制。
    当设置为大于 `0` 时，服务会尽量确保最终输出不少于该值。

请求示例：

```json
{
  "case_material": "案件材料全文...",
  "prompt_instruction": "请生成审查报告...",
  "enable_legal_search": true,
  "max_react_steps": 10,
  "temperature": 0.2,
  "min_output_length": 0
}
```

成功返回示例：

```json
{
  "success": true,
  "content": "最终报告字符串",
  "sections": [],
  "metadata": {
    "request_id": "20260303xxxxxx-xxxx",
    "elapsed_seconds": 23.512,
    "content_length": 2560
  },
  "error": null,
  "debug_info": null
}
```

返回字段说明：
- `success`：是否成功
- `content`：最终报告正文。若命中法条检索，正文会使用 `[法条ID:123]` 形式角标引用法条；不附法条原文。
- `sections`：章节结果（当前可能为空数组）
- `metadata`：执行元信息（请求 ID、耗时、长度等）
- `error`：失败时错误信息
- `debug_info`：仅在 `include_debug=true` 时返回

---

### 1.3 流式写作（SSE）

- 方法：`POST`
- 路径：`/api/write/stream`
- 完整地址：`http://localhost:11453/api/write/stream`
- Content-Type：`application/json`
- 响应类型：`text/event-stream`

请求参数：
- 与 `/api/write` 基本一致
- 可通过 `min_output_length` 控制最小输出长度（默认 `0`，表示不限制）
- 额外可选：`stream_heartbeat_seconds` (int，默认 `3`，范围 `1-30`)：
  控制 `progress` 心跳事件发送间隔（每隔 N 秒推一次进度），主要用于连接保活和前端进度反馈。
  说明：该参数只影响流式心跳频率，不改变模型推理结果与写作质量；若客户端不消费 `progress`，调大调小可能看起来“没有功能变化”。

SSE 事件顺序（正常完成）：
1) `start`
2) `progress`（可多次）
3) `final`
4) `done`

异常时会收到：`error`

各事件返回示例：

`start`
```json
{
  "request_id": "...",
  "message": "写作任务已启动",
  "case_material_length": 12345,
  "prompt_instruction_length": 456,
  "timestamp": "2026-03-03T12:00:00"
}
```

`progress`
```json
{
  "request_id": "...",
  "status": "running",
  "elapsed_seconds": 18.3,
  "message": "模型仍在推理中"
}
```

`final`
```json
{
  "request_id": "...",
  "success": true,
  "content": "最终报告字符串（含 [法条ID:123] 角标）",
  "error": null,
  "metadata": {
    "elapsed_seconds": 42.1,
    "content_length": 3680
  },
  "react_steps": [],
  "legal_references": [],
  "retrieved_contents": []
}
```

`done`
```json
{
  "request_id": "...",
  "status": "completed"
}
```

`error`
```json
{
  "request_id": "...",
  "error": "错误信息"
}
```

---


## 2. MCP 服务（MCP over SSE）

> 仅直接对接 MCP 协议时使用。若你只调用写作服务，可忽略本节。

连接方式：
- SSE 地址：`GET /sse`
- 完整地址：`http://localhost:11452/sse`

Docker 部署注意：
- 写作服务通过 `MCP_SSE_URL=http://mcp-service:8000/sse` 连接 MCP。
- 若 MCP 服务启用了严格 Host 校验，可在写作服务环境变量中设置：
  - `MCP_FORCE_HOST_HEADER=127.0.0.1:8000`
  以避免容器内 `Host: mcp-service:8000` 被拒绝（421）。
- `MCP over SSE` 不是 `REST call_tool` 接口，`/mcp/call_tool` 返回 404 属于预期。

### 2.1 工具：`get_article`

用途：按法规标题 + 条号精确获取法条。

入参：
- `number` (string，必填)，例如 `"第264条"`
- `title` (string，必填)，例如 `"刑法"`

返回：
- 命中：法条对象
- 未命中：`{}`

示例：

```json
{
  "id": 123,
  "title": "中华人民共和国刑法",
  "section_number": "第264条",
  "content": "盗窃公私财物...",
  "url": "https://...",
  "created_at": "2025-01-01T00:00:00",
  "updated_at": "2025-02-24T00:00:00"
}
```

### 2.2 工具：`search_article`

用途：关键词检索法条。

入参：
- `text` (string，必填)
- `page` (int|string，可选，默认 `1`)
- `page_size` (int|string，可选，默认 `10`，范围 `1-100`)
- `sort_by` (string，可选，默认 `relevance`，可选：`relevance|updated_at|created_at|id`)
- `order` (string，可选，默认 `desc`，可选：`asc|desc`)

返回：
- 命中：数组（每项为法条对象，含 `relevance`）
- 未命中：`[]`

示例：

```json
[
  {
    "id": 123,
    "title": "中华人民共和国刑法",
    "section_number": "第264条",
    "content": "盗窃公私财物...",
    "url": "https://...",
    "created_at": "2025-01-01T00:00:00",
    "updated_at": "2025-02-24T00:00:00",
    "relevance": 6
  }
]
```

---

## 3. 最小调用示例（curl）

同步写作：

```bash
curl -X POST "http://localhost:11453/api/write" \
  -H "Content-Type: application/json" \
  -d '{
    "case_material": "案件材料全文...",
    "prompt_instruction": "请生成审查报告...",
    "enable_legal_search": true
  }'
```

流式写作：

```bash
curl -N -X POST "http://localhost:11453/api/write/stream" \
  -H "Content-Type: application/json" \
  -d '{
    "case_material": "案件材料全文...",
    "prompt_instruction": "请生成审查报告...",
    "stream_heartbeat_seconds": 3,
    "min_output_length": 0
  }'
```
