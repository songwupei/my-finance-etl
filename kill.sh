  # 按端口杀
  lsof -i :5001 -t | xargs kill

  # 或按进程名
  pkill -f flask_app.py
