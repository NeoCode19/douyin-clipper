"""模拟扩展端行为:把 payload JSON 提交给本机助手。

用法: python tools/post_clip.py [payload路径]
"""
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent


def main() -> None:
    payload_path = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT / "downloads" / "payload.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))

    # 从 config.toml 取 token
    text = (PROJECT / "config.toml").read_text(encoding="utf-8")
    token = ""
    for ln in text.splitlines():
        if ln.startswith("token"):
            token = ln.split("=", 1)[1].strip().strip('"')

    import requests
    r = requests.post(
        "http://127.0.0.1:7788/clip",
        json=payload,
        headers={"X-Dyclip-Token": token},
        timeout=15,
        proxies={"http": None, "https": None},
    )
    print(r.status_code, json.dumps(r.json(), ensure_ascii=False))


if __name__ == "__main__":
    main()
