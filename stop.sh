#!/bin/bash
# ============================================================
# stop.sh — 停止所有财务数据分析平台服务
# ============================================================
echo "🛑 停止服务..."

lsof -i :8765 -t 2>/dev/null | xargs kill 2>/dev/null && echo "   ✅ SionTiles (port 8765) 已停止" || echo "   ⚠️  SionTiles (port 8765) 未运行"
lsof -i :5001 -t 2>/dev/null | xargs kill 2>/dev/null && echo "   ✅ Vizro  (port 5001) 已停止" || echo "   ⚠️  Vizro  (port 5001) 未运行"
lsof -i :8000 -t 2>/dev/null | xargs kill 2>/dev/null && echo "   ✅ Shiny  (port 8000) 已停止" || echo "   ⚠️  Shiny  (port 8000) 未运行"

echo "完成。"
