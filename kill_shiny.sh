#!/bin/bash
# ============================================================
# kill_shiny.sh — 停止 Shiny；start.sh 已统一按端口清理，此脚本仅供手动调用。
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=deploy/lib.sh
source "$SCRIPT_DIR/deploy/lib.sh"
deploy_load "$SCRIPT_DIR"

if ! deploy_kill_port "$SHINY_PORT" "Shiny"; then
    echo "Shiny 未运行 (port $SHINY_PORT)"
fi
