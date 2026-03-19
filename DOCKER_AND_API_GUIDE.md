# Docker 与接口完整说明（MCP + 写作智能体）

本文档解释以下内容：
1. Dockerfile 和 docker-compose 是什么
2. 为什么有两个 Dockerfile
3. 如何构建、启动、停止
4. 容器与网络关系
5. 常用 Docker 指令
6. 写作服务接口文档（含流式）

---
重建并启动容器
docker compose up -d --force-recreate writer-service


cd /data/app/fj-writer-mcp

# 重要：检索链路改动后必须重建两个服务（mcp + writer）
sudo docker compose build mcp-service writer-service
sudo docker compose up -d --force-recreate mcp-service writer-service

# 查看是否为新容器（启动时间会刷新）
sudo docker compose ps

# 观察两端日志，确认检索参数已生效
sudo docker compose logs -f mcp-service
sudo docker compose logs -f writer-service

## 1) Dockerfile 是什么

`Dockerfile` 是“镜像构建说明书”。

你可以把它理解成：
- 从哪个基础环境开始（例如 `python:3.11-slim`）
- 复制哪些文件进去
- 安装哪些依赖
- 容器启动时执行哪个命令

一句话：**Dockerfile 负责“怎么打包一个服务”**。

---

## 2) docker-compose 是什么

`docker-compose.yml` 是“多容器编排文件”。

它负责：
- 一次启动多个容器
- 连接容器网络
- 配置端口映射、环境变量、资源限制、重启策略
- 定义服务之间依赖（如写作服务依赖 MCP 服务）

一句话：**Compose 负责“多个服务如何一起运行”**。

---

## 3) 为什么你看到两个 Dockerfile

你有两个独立服务：
- MCP 服务（法律检索）
- 写作智能体服务（HTTP API）

它们职责不同、依赖不同、启动命令不同，所以一般是：
- 每个服务一个 Dockerfile（分别打包）
- 用同一个 compose 把两者连起来

这是一种标准微服务做法。

### 你问“能不能放一个 Docker 里？”

可以，但不推荐。

单容器双进程会带来：
- 进程管理复杂（一个崩溃可能影响另一个）
- 扩缩容不灵活（无法单独扩容写作服务）
- 观测和排障更难

如果只是本地临时演示，可以这么干；长期运行建议维持现在的两容器方案。

---

## 4) 当前项目的部署结构

你当前配置：
- `mcp-with-law-article/Dockerfile`
- `writer-for-fujian/Dockerfile`
- 根目录 `docker-compose.yml`

网络互通：
- 写作服务容器内通过 `http://mcp-service:8000/sse` 调用 MCP

端口暴露：
- MCP: 主机 `18080` -> 容器 `8000`
- Writer API: 主机 `18081` -> 容器 `8000`

---

## 5) 构建、启动、停止

### 构建并启动

```bash
docker compose up -d --build
```

### 查看运行状态

```bash
docker compose ps
```

### 查看日志

```bash
docker compose logs -f mcp-service
docker compose logs -f writer-service
```

### 仅重启某个服务

```bash
docker compose restart writer-service
```

### 停止并移除容器

```bash
docker compose down
```

### 停止并移除容器+网络+匿名卷

```bash
docker compose down -v
```

---

## 6) 容器是什么

容器是“进程级隔离运行环境”，不是虚拟机。

特点：
- 启动快
- 资源占用小
- 依赖打包一致（本地/测试/生产一致）

在你的场景里：
- `mcp-service` 容器：专门跑法律检索服务
- `writer-service` 容器：专门跑写作 API 服务

两者独立、可单独重启、单独扩展、单独限流限资源。

---

## 7) 常用 Docker 指令（实用版）

### 镜像相关

```bash
docker images
docker rmi <image_id>
```

### 容器相关

```bash
docker ps
docker ps -a
docker stop <container>
docker start <container>
docker rm <container>
```

### 进入容器

```bash
docker exec -it writer-service sh
docker exec -it mcp-service sh
```

### 查看容器资源占用

```bash
docker stats
```

### 清理无用资源

```bash
docker system prune -f
```

---

## 8) 写作服务接口文档

服务地址（默认）：
- `http://localhost:18081`

### 8.1 健康检查

- 方法：`GET`
- 路径：`/health`
- 用途：检查服务是否可用

### 8.2 同步写作接口

- 方法：`POST`
- 路径：`/api/write`
- 描述：等待模型执行完成后，一次返回完整字符串报告

请求体（JSON）：

```json
{
  "case_material": "案件材料文本",
  "prompt_instruction": "提示词",
  "enable_legal_search": true,
  "enable_content_retrieval": false,
  "section_mode": false,
  "max_react_steps": 10,
  "temperature": 0.2,
  "repetition_strategy": "smart",
  "strong_requirements": ["引用法条需准确"],
  "context_window_limit": 128000,
  "multi_turn_enabled": true,
  "proactive_tool_call": true
}
```

响应体（JSON）：

```json
{
  "success": true,
  "content": "最终报告字符串",
  "sections": [],
  "metadata": {
    "request_id": "20260303xxxxxx-xxxx",
    "elapsed_seconds": 23.5,
    "content_length": 2500
  },
  "error": null,
  "debug_info": null
}
```

### 8.3 流式写作接口（SSE）

- 方法：`POST`
- 路径：`/api/write/stream`
- 描述：长任务时推荐，持续返回事件，避免网关超时
- 响应类型：`text/event-stream`

SSE 事件：
- `start`：任务开始
- `progress`：心跳/进度
- `final`：最终结果（含完整 content）
- `done`：结束标记
- `error`：异常

说明：
- `final` 事件里会返回完整字符串结果 `content`
- 调用端需支持 SSE 解析

### 8.4 简化接口

- 方法：`POST`
- 路径：`/api/write/simple`
- 描述：仅传核心参数，内部转调 `/api/write`

---

## 9) 资源限制说明

compose 中已设置：
- `mcp-service`: 1 CPU / 1GB
- `writer-service`: 2 CPU / 2GB

注意：
- `deploy.resources` 在普通 Docker Compose 下不一定生效（主要给 Swarm）
- `cpus` 与 `mem_limit` 在本地 compose 模式可生效

---

## 10) 常见问题

### Q1：为什么我访问不到写作接口？
- 先看 `docker compose ps`
- 再看 `docker compose logs -f writer-service`
- 检查 `LLM_API_KEY` 是否配置

### Q2：写作服务调用不到 MCP？
- 确认 `writer-service` 环境变量 `MCP_SSE_URL=http://mcp-service:8000/sse`
- 确认 `mcp-service` 容器已正常启动

### Q3：输入很大（上万字）会不会有问题？
- 当前接口支持大文本 JSON 请求
- 建议通过流式接口 `/api/write/stream` 接收长耗时任务结果
- 生产环境建议同步调大反向代理超时和 body 大小限制

---

## 11) 一句话总结

- 你现在不是“一个 Docker 容器”，而是“一个 Compose 应用（两个容器）”。
- 这是正确且推荐的做法：服务解耦、稳定、易扩展。
