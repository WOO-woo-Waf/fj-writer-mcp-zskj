#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

NETWORK_NAME="fujian-services-net"

MCP_IMAGE="mcp-service-img"
WRITER_IMAGE="writer-service-img"

MCP_CONTAINER="mcp-service"
WRITER_CONTAINER="writer-service"

MCP_PORT="11452:8000"
WRITER_PORT="11453:8000"

MCP_CONFIG_PATH="$ROOT_DIR/mcp-with-law-article/config.ini"
WRITER_ENV_FILE="$ROOT_DIR/writer-for-fujian/.env"

usage() {
  cat <<EOF
用法: ./docker-no-compose.sh <命令>

命令:
  build     构建两个镜像
  start     启动两个容器（若镜像不存在会先构建）
  stop      停止并删除两个容器
  restart   重启（stop + start）
  status    查看容器状态
  logs      查看两个容器日志（持续输出）
  up        等价于 build + start
  down      等价于 stop

示例:
  ./docker-no-compose.sh up
  ./docker-no-compose.sh start
  ./docker-no-compose.sh stop
EOF
}

check_prerequisites() {
  command -v docker >/dev/null 2>&1 || {
    echo "错误: 未找到 docker 命令，请先安装 Docker。"
    exit 1
  }

  if [[ ! -f "$MCP_CONFIG_PATH" ]]; then
    echo "错误: 找不到配置文件: $MCP_CONFIG_PATH"
    exit 1
  fi

  if [[ ! -f "$WRITER_ENV_FILE" ]]; then
    echo "错误: 找不到环境变量文件: $WRITER_ENV_FILE"
    exit 1
  fi
}

ensure_network() {
  docker network inspect "$NETWORK_NAME" >/dev/null 2>&1 || docker network create "$NETWORK_NAME" >/dev/null
}

remove_existing_containers() {
  docker rm -f "$MCP_CONTAINER" "$WRITER_CONTAINER" >/dev/null 2>&1 || true
}

image_exists() {
  local image_name="$1"
  docker image inspect "$image_name" >/dev/null 2>&1
}

build_images() {
  echo "[1/2] 构建 MCP 镜像..."
  docker build -t "$MCP_IMAGE" "$ROOT_DIR/mcp-with-law-article"

  echo "[2/2] 构建 Writer 镜像..."
  docker build -t "$WRITER_IMAGE" "$ROOT_DIR/writer-for-fujian"
}

start_containers() {
  ensure_network
  remove_existing_containers

  if ! image_exists "$MCP_IMAGE" || ! image_exists "$WRITER_IMAGE"; then
    echo "检测到镜像不存在，先执行构建..."
    build_images
  fi

  echo "启动 MCP 容器..."
  docker run -d \
    --name "$MCP_CONTAINER" \
    --restart unless-stopped \
    --network "$NETWORK_NAME" \
    -p "$MCP_PORT" \
    -v "$MCP_CONFIG_PATH:/app/config.ini:ro" \
    -e PYTHONUNBUFFERED=1 \
    --cpus=1 \
    --memory=1024m \
    "$MCP_IMAGE" >/dev/null

  echo "启动 Writer 容器..."
  docker run -d \
    --name "$WRITER_CONTAINER" \
    --restart unless-stopped \
    --network "$NETWORK_NAME" \
    -p "$WRITER_PORT" \
    --env-file "$WRITER_ENV_FILE" \
    -e PYTHONUNBUFFERED=1 \
    -e MCP_SSE_URL="http://$MCP_CONTAINER:8000/sse" \
    --cpus=2 \
    --memory=2048m \
    "$WRITER_IMAGE" >/dev/null

  echo "启动完成。"
  show_status
}

stop_containers() {
  echo "停止并删除容器..."
  docker rm -f "$WRITER_CONTAINER" "$MCP_CONTAINER" >/dev/null 2>&1 || true
  echo "已停止。"
}

show_status() {
  docker ps -a \
    --filter "name=$MCP_CONTAINER" \
    --filter "name=$WRITER_CONTAINER" \
    --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
}

show_logs() {
  docker logs -f "$MCP_CONTAINER" &
  local log_pid_1=$!
  docker logs -f "$WRITER_CONTAINER" &
  local log_pid_2=$!

  trap 'kill "$log_pid_1" "$log_pid_2" 2>/dev/null || true' INT TERM EXIT
  wait
}

main() {
  local cmd="${1:-}"
  if [[ -z "$cmd" ]]; then
    usage
    exit 1
  fi

  check_prerequisites

  case "$cmd" in
    build)
      build_images
      ;;
    start)
      start_containers
      ;;
    stop|down)
      stop_containers
      ;;
    restart)
      stop_containers
      start_containers
      ;;
    status)
      show_status
      ;;
    logs)
      show_logs
      ;;
    up)
      build_images
      start_containers
      ;;
    -h|--help|help)
      usage
      ;;
    *)
      echo "未知命令: $cmd"
      usage
      exit 1
      ;;
  esac
}

main "$@"