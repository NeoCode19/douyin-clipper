"""dyclip:// 协议唤起的启动垫片(pythonw 无窗口执行)

工作目录无关;若助手已在运行则自动退出。
pythonw 没有 stdout/stderr(None),全部重定向到日志文件,
否则任何 print 都会掐断请求线程。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(ROOT, "downloads", "server.log")
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
sys.stdout = open(LOG_PATH, "a", buffering=1, encoding="utf-8", errors="replace")
sys.stderr = sys.stdout

sys.path.insert(0, ROOT)

from dyclip.serve import main

try:
    main()
except Exception:
    # 兜底留痕
    with open(LOG_PATH, "a", encoding="utf-8", errors="replace") as f:
        import traceback
        f.write(traceback.format_exc())
