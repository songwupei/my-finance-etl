#!/bin/bash
# ============================================================
# stop.sh — 停止所有财务数据分析平台服务
# ============================================================
echo "🛑 停止服务..."

SIONTILES_PORT=8765
VIZRO_PORT=5001
SHINY_PORT=8000

for entry in "SionTiles:$SIONTILES_PORT" "Vizro:$VIZRO_PORT" "Shiny:$SHINY_PORT"; do
    name="${entry%%:*}"
    port="${entry##*:}"
    pids=$(lsof -i :"$port" -t 2>/dev/null)
    if [ -n "$pids" ]; then
        echo "$pids" | xargs -r kill 2>/dev/null
        echo "   ✅ $name (port $port) 已停止 (PID: $(echo $pids | tr '\n' ' '))"
    else
        echo "   ⚠️  $name (port $port) 未运行"
    fi
done

echo "完成。"
