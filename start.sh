#!/bin/bash
# ============================================================
# start.sh — 财务数据分析平台 启动器 (whiptail GUI)
# ============================================================
# Usage: bash start.sh [--profile <主题>]
# 两个服务同时启动，仅打开选中的页面。
#
# 机器相关的配置（路径 / 端口 / micromamba 位置 / 是否开浏览器）全部在
# deploy/ 目录下，见 deploy/README.md。本脚本只负责流程。

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ---- 解析 --profile（必须在加载配置之前）----
while [ $# -gt 0 ]; do
    case "$1" in
        --profile)   PROFILE="$2"; shift 2 ;;
        --profile=*) PROFILE="${1#*=}"; shift ;;
        -h|--help)
            echo "用法: bash start.sh [--profile <主题>]"
            echo "可用主题: $(ls "$SCRIPT_DIR/deploy/profiles" 2>/dev/null | sed 's/\.env$//' | tr '\n' ' ')"
            echo "也可用环境变量覆盖: PROFILE=arch bash start.sh"
            exit 0 ;;
        *) echo "未知参数: $1（用 --help 查看用法）" >&2; exit 2 ;;
    esac
done

# ---- 加载部署配置 ----
# shellcheck source=deploy/lib.sh
source "$SCRIPT_DIR/deploy/lib.sh"
deploy_load "$SCRIPT_DIR"

mkdir -p "$LOG_DIR"

SIONTILES_LOG="$LOG_DIR/siontiles.log"
SHINY_LOG="$LOG_DIR/shiny.log"
VIZRO_LOG="$LOG_DIR/vizro.log"

# 标题里的版本号取自 pyproject.toml，避免与包版本漂移
TITLE="${APP_TITLE}${APP_VERSION:+ v$APP_VERSION}"

# ---- 检查 whiptail（仅交互模式需要）----
if [ -t 0 ] && ! command -v whiptail &>/dev/null; then
    echo "❌ 未安装 whiptail，请先安装: $PKG_HINT_WHIPTAIL"
    exit 1
fi

# ---- 检查运行时（micromamba / python）----
if ! deploy_check_runtime; then
    exit 1
fi

echo "ℹ️  配置主题: $PROFILE_NAME（$PROFILE）"

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
    # stdin 处于 EOF（cron / nohup / </dev/null）时 read 返回非 0，
    # 在 set -e 下会静默退出且不启动任何服务，因此显式兜底。
    read CHOICE_NUM || CHOICE_NUM=1
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
deploy_kill_port "$SIONTILES_PORT" "SionTiles" || true
deploy_kill_port "$SHINY_PORT" "Shiny" || true
deploy_kill_port "$VIZRO_PORT" "Vizro" || true
sleep 1

echo "⏳ 启动服务（串行，避免 DuckDB 锁冲突）..."
echo ""

# ---- 先启动 SionTiles 地图服务（无 DB 依赖）----
SIONTILES_PID=""
if [ "$ENABLE_SIONTILES" = "true" ]; then
    if [ ! -d "$SIONTILES_DIR" ]; then
        echo "⚠️  SionTiles 目录不存在，跳过: $SIONTILES_DIR"
        echo "   （可在 deploy/local.env 设置 SIONTILES_DIR，或 ENABLE_SIONTILES=false）"
    else
        echo "🗺️  启动 企业地图服务 (SionTiles)  port $SIONTILES_PORT ..."
        cd "$SIONTILES_DIR"
        "${RUN_CMD[@]}" python "$SIONTILES_ENTRY" \
            > "$SIONTILES_LOG" 2>&1 &
        SIONTILES_PID=$!
        cd "$SCRIPT_DIR"
        echo "   PID: $SIONTILES_PID  → 日志: $SIONTILES_LOG"

        # 等 SionTiles 就绪
        for i in $(seq 1 10); do
            if curl -s "http://localhost:$SIONTILES_PORT" >/dev/null 2>&1; then
                echo "   ✅ SionTiles 就绪 (port $SIONTILES_PORT)"
                break
            fi
            sleep 1
        done
        if ! curl -s "http://localhost:$SIONTILES_PORT" >/dev/null 2>&1; then
            echo "   ⚠️  SionTiles 未就绪 (port $SIONTILES_PORT)，地图 iframe 将不可用；日志: $SIONTILES_LOG"
        fi
    fi
fi

# ---- 先启动 Shiny（需要写 DuckDB，独占锁）----
echo "🚀 启动 个人电脑办公大屏 (Shiny)  port $SHINY_PORT ..."
"${RUN_CMD[@]}" shiny run \
    --host "$BIND_HOST" --port "$SHINY_PORT" \
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
if ! curl -s "http://localhost:$SHINY_PORT" >/dev/null 2>&1; then
    echo "   ❌ Shiny 启动失败 (port $SHINY_PORT)，请查看日志: $SHINY_LOG"
    exit 1
fi

# ---- 再启动 Vizro（只读 DuckDB）----
echo "🚀 启动 领导汇报大屏 (Vizro)  port $VIZRO_PORT ..."
"${RUN_CMD[@]}" python -c "
from src.my_finance_web import create_app
create_app().run(debug=False, host='$BIND_HOST', port=$VIZRO_PORT)
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
if ! curl -s "http://localhost:$VIZRO_PORT" >/dev/null 2>&1; then
    echo "   ❌ Vizro 启动失败 (port $VIZRO_PORT)，请查看日志: $VIZRO_LOG"
    exit 1
fi

# ---- 打开浏览器 ----
echo ""
if [ "$CHOICE" = "vizro" ]; then
    URL="http://$PUBLIC_HOST:$VIZRO_PORT"
    NAME="领导汇报大屏 (Vizro)"
else
    URL="http://$PUBLIC_HOST:$SHINY_PORT"
    NAME="个人电脑办公大屏 (Shiny)"
fi

if [ "$OPEN_BROWSER" = "true" ]; then
    echo "🌐 打开 $NAME → $URL"
    "$BROWSER_CMD" "$URL" 2>/dev/null || true
else
    echo "🌐 请访问 $NAME → $URL"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  配置主题: $PROFILE_NAME（$PROFILE）"
echo "  服务运行中:"
if [ -n "$SIONTILES_PID" ]; then
    echo "    企业地图分析  → http://$PUBLIC_HOST:$SIONTILES_PORT"
else
    echo "    企业地图分析  → 未启动"
fi
echo "    领导汇报大屏  → http://$PUBLIC_HOST:$VIZRO_PORT"
echo "    个人电脑办公  → http://$PUBLIC_HOST:$SHINY_PORT"
echo "  停止服务: bash stop.sh"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
