#!/bin/bash
# ============================================================
# kill.sh — 停止 Vizro (port 5001)；start.sh 已改为直接按端口清理，
#           此脚本仅供手动调用。
# ============================================================
lsof -i :5001 -t 2>/dev/null | xargs -r kill 2>/dev/null && echo "Vizro killed (port 5001)" || echo "No Vizro on port 5001"
