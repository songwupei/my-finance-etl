#!/bin/bash
# ============================================================
# start.sh — 财务数据分析平台 启动器 (whiptail GUI)
# ============================================================
# Usage: bash start.sh
# 两个服务同时启动，仅打开选中的页面。

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

SHINY_LOG="$LOG_DIR/shiny.log"
VIZRO_LOG="$LOG_DIR/vizro.log"

KILL_SHINY="$SCRIPT_DIR/kill_shiny.sh"
KILL_VIZRO="$SCRIPT_DIR/kill.sh"

SHINY_PORT=8000
VIZRO_PORT=5001

TITLE="财务数据分析平台 v1.6.3"
MENU_TEXT="两个服务将同时启动。请选择要打开的页面:"

# ---- 检查 whiptail（仅交互模式需要）----
if [ -t 0 ] && ! command -v whiptail &>/dev/null; then
    echo "❌ 未安装 whiptail，请先安装: sudo apt install whiptail"
    exit 1
fi

# ---- 检查 micromamba ----
if ! command -v micromamba &>/dev/null; then
    echo "❌ 未安装 micromamba"
    exit 1
fi

# ---- 显示菜单 ----
if [ -t 0 ]; then
    # 交互式终端：使用 whiptail GUI
    CHOICE=$(whiptail --title "$TITLE" \
        --radiolist "$MENU_TEXT" \
        20 60 2 \
        "vizro" "领导汇报大屏 (Vizro)  — port $VIZRO_PORT" ON \
        "shiny" "个人电脑办公大屏 (Shiny) — port $SHINY_PORT" OFF \
        3>&1 1>&2 2>&3)
else
    # 非交互式终端：使用纯文本提示
    echo "========================================"
    echo "  $TITLE"
    echo "========================================"
    echo "  1) 领导汇报大屏 (Vizro)  — port $VIZRO_PORT"
    echo "  2) 个人电脑办公大屏 (Shiny) — port $SHINY_PORT"
    echo ""
    echo -n "请选择 [1-2] (默认: 1): "
    read CHOICE_NUM
    case "${CHOICE_NUM:-1}" in
        1) CHOICE="vizro" ;;
        2) CHOICE="shiny" ;;
        *) echo "无效选择，退出。"; exit 0 ;;
    esac
fi

if [ -z "$CHOICE" ]; then
    echo "已取消。"
    exit 0
fi

# ---- 杀掉已有进程 ----
echo "🔧 清理已有进程..."
bash "$KILL_SHINY" 2>/dev/null || true
bash "$KILL_VIZRO" 2>/dev/null || true
sleep 1

echo "⏳ 启动服务（串行，避免 DuckDB 锁冲突）..."
echo ""

# ---- 先启动 Shiny（需要写 DuckDB，独占锁）----
echo "🚀 启动 个人电脑办公大屏 (Shiny)  port $SHINY_PORT ..."
micromamba run shiny run \
    --host 0.0.0.0 --port $SHINY_PORT \
    src.my_finance_shiny.app \
    > "$SHINY_LOG" 2>&1 &
SHINY_PID=$!
echo "   PID: $SHINY_PID  → 日志: $SHINY_LOG"

# 等 Shiny 就绪（完成 DuckDB 写入后再启动 Vizro）
for i in $(seq 1 30); do
    if curl -s "http://localhost:$SHINY_PORT" >/dev/null 2>&1; then
        echo "   ✅ Shiny  就绪 (port $SHINY_PORT)"
        break
    fi
    sleep 1
done

# ---- 再启动 Vizro（只读 DuckDB）----
echo "🚀 启动 领导汇报大屏 (Vizro)  port $VIZRO_PORT ..."
micromamba run python -c "
from src.my_finance_web import create_app
create_app().run(debug=False, host='0.0.0.0', port=$VIZRO_PORT)
" > "$VIZRO_LOG" 2>&1 &
VIZRO_PID=$!
echo "   PID: $VIZRO_PID  → 日志: $VIZRO_LOG"

# 等 Vizro 就绪
for i in $(seq 1 30); do
    if curl -s "http://localhost:$VIZRO_PORT" >/dev/null 2>&1; then
        echo "   ✅ Vizro  就绪 (port $VIZRO_PORT)"
        break
    fi
    sleep 1
done

# ---- 打开浏览器 ----
echo ""
if [ "$CHOICE" = "vizro" ]; then
    URL="http://localhost:$VIZRO_PORT"
    NAME="领导汇报大屏 (Vizro)"
else
    URL="http://localhost:$SHINY_PORT"
    NAME="个人电脑办公大屏 (Shiny)"
fi

echo "🌐 打开 $NAME → $URL"
xdg-open "$URL" 2>/dev/null || open "$URL" 2>/dev/null || true

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  服务运行中:"
echo "    领导汇报大屏  → http://localhost:$VIZRO_PORT"
echo "    个人电脑办公  → http://localhost:$SHINY_PORT"
echo "  停止服务: bash stop.sh"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
