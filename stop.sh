#!/bin/bash
# ============================================================
# stop.sh — 停止所有财务数据分析平台服务
# ============================================================
# 端口等配置与 start.sh 同源（deploy/），避免两边不一致。

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=deploy/lib.sh
source "$SCRIPT_DIR/deploy/lib.sh"
deploy_load "$SCRIPT_DIR"

echo "🛑 停止服务..."

echo "   配置主题: $PROFILE_NAME（$PROFILE）"

while IFS=: read -r name port; do
    if ! deploy_kill_port "$port" "$name"; then
        echo "   ⚠️  $name (port $port) 未运行"
    fi
done < <(deploy_services)

echo "完成。"
