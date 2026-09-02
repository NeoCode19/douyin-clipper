"""本机助手:常驻 HTTP 服务,接收 Chrome 扩展提交的剪藏任务

用法: python -m dyclip.serve
端口 127.0.0.1:7788,仅本机可见。
扩展需携带 X-Dyclip-Token(config.toml 中的 token)。
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config, render

PORT = 7788


def build_item(payload: dict) -> dict:
    """把扩展发来的 payload 组装成 pipeline 的 item dict"""
    from urllib.parse import quote
    urls = []
    for pa in payload.get("play_addr") or []:
        if isinstance(pa, str):
            urls.append(pa)
        elif isinstance(pa, dict):
            for u in pa.get("url_list") or []:
                urls.append(u)
    if payload.get("play_api"):
        urls.append(payload["play_api"])
    if not urls:
        raise ValueError("payload 中没有任何可用的视频地址")

    create_time = payload.get("create_time")
    published = ""
    if create_time:
        dt = datetime.fromtimestamp(int(create_time), tz=timezone(timedelta(hours=8)))
        published = dt.strftime("%Y-%m-%d")

    title, description = render.split_desc(payload.get("desc") or "")
    web_url = f"https://www.douyin.com/video/{quote(str(payload['aweme_id']))}"
    return {
        "aweme_id": str(payload["aweme_id"]),
        "title": title,
        "description": description,
        "author": payload.get("author") or "未知作者",
        "published": published,
        "web_url": web_url,
        "play_url": urls[0],
        "url_candidates": urls[:4],
        "duration_sec": round(int(payload.get("duration_ms") or 0) / 1000),
    }


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        origin = self.headers.get("Origin", "")
        if origin.startswith("chrome-extension://"):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Dyclip-Token")

    def _reply(self, code: int, obj: dict):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self._reply(204, {})

    def do_GET(self):
        if self.path == "/ping":
            self._reply(200, {"ok": True, "service": "douyin-clipper", "version": "0.2.0"})
        else:
            self._reply(404, {"ok": False})

    def do_POST(self):
        if self.path != "/clip":
            return self._reply(404, {"ok": False})
        cfg = config.load()
        token = self.headers.get("X-Dyclip-Token", "")
        if token != cfg.get("token", ""):
            return self._reply(401, {"ok": False, "error": "token 不匹配"})

        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            item = build_item(payload)
        except Exception as e:
            return self._reply(400, {"ok": False, "error": f"payload 无效: {e}"})

        thread = threading.Thread(target=self._work, args=(cfg, item), daemon=True)
        thread.start()
        self._reply(202, {"ok": True, "accepted": True,
                          "title": item["title"], "aweme_id": item["aweme_id"],
                          "message": "任务已受理,转写完成后笔记将自动写入仓库"})

    def _work(self, cfg, item):
        log = config.PROJECT_ROOT / "downloads" / "server.log"

        def say(msg: str):
            line = f"{datetime.now():%H:%M:%S} {msg}"
            print(line, flush=True)
            with open(log, "a", encoding="utf-8") as f:
                f.write(line + "\n")

        try:
            say(f"开始处理 {item['aweme_id']} - {item['title'][:30]}")
            from .pipeline import _run
            _run(cfg, item)
            say(f"完成 {item['aweme_id']}")
        except SystemExit as e:
            say(f"失败: {e}")
        except Exception as e:
            import traceback
            say(f"异常: {e}\n{traceback.format_exc()}")


def main() -> None:
    cfg = config.load()
    if not cfg.get("token"):
        raise SystemExit("config.toml 缺少 token 字段(随意一串字符,用于本地鉴权)")
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError as e:
        # 已有实例在跑(常见于协议被重复唤起):静默退出即可
        print(f"端口 {PORT} 已被占用({e}),应已有助手实例在运行,本进程退出。")
        return
    print(f"douyin-clipper 助手已启动:http://127.0.0.1:{PORT}")
    print("等待 Chrome 扩展提交剪藏任务…(Ctrl+C 退出)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n再见")


if __name__ == "__main__":
    main()
