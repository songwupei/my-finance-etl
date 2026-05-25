#!/bin/bash
# kill_shiny — 按端口杀掉 Shiny 进程
lsof -i :8000 -t | xargs kill 2>/dev/null && echo "Shiny killed (port 8000)" || echo "No Shiny on port 8000"
