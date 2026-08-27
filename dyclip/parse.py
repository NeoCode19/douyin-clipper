"""抖音链接解析:短链/完整链接 -> aweme_id -> 元数据 + 视频直链

数据来源是 iesdouyin 移动端分享页,不需要登录和签名。
页面结构若被平台改版,fetch_item 会 fail fast 并打印调试信息。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

UA_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

_HEADERS = {
    "User-Agent": UA_MOBILE,
    "Referer": "https://www.douyin.com/",
}

_AWEME_RE = re.compile(r"/(?:video|note|slides)/(\d+)")


class ParseError(Exception):
    pass


def resolve_aweme_id(url: str, proxies: dict | None = None) -> str:
    """支持 https://www.douyin.com/video/{id} 或 https://v.douyin.com/xxxx/ 短链"""
    m = _AWEME_RE.search(url)
    if m:
        return m.group(1)

    resp = requests.get(
        url,
        headers=_HEADERS,
        allow_redirects=True,
        timeout=20,
        proxies=proxies,
    )
    m = _AWEME_RE.search(resp.url)
    if not m:
        m = _AWEME_RE.search(resp.text)
    if not m:
        raise ParseError(f"无法从链接中解析视频 ID,最终跳转到: {resp.url}")
    return m.group(1)


def fetch_item(aweme_id: str, proxies: dict | None = None) -> dict:
    """拉取分享页并提取结构化数据,返回统一格式的 item dict"""
    share_url = f"https://www.iesdouyin.com/share/video/{aweme_id}/"
    resp = requests.get(share_url, headers=_HEADERS, timeout=20, proxies=proxies)
    if resp.status_code != 200:
        raise ParseError(f"分享页请求失败 HTTP {resp.status_code}: {share_url}")

    html = resp.text
    data = _extract_router_data(html)
    if data is None:
        raise ParseError(
            "分享页中未找到 _ROUTER_DATA。可能已改版或触发风控。HTML 预览:\n"
            + html[:600]
        )

    item = _find_item(data)
    if item is None:
        raise ParseError(f"_ROUTER_DATA 中未找到 item_list 数据 (aweme_id={aweme_id})")

    return normalize(item, aweme_id)


def _extract_router_data(html: str) -> dict | None:
    for pat in (r"window\._ROUTER_DATA\s*=\s*(\{.*?\})\s*</script>",
                r"_ROUTER_DATA\s*=\s*(\{.*?\})\s*<"):
        m = re.search(pat, html, re.S)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                continue
    return None


def _find_item(router_data: dict) -> dict | None:
    loader = router_data.get("loaderData", {})
    for key, val in loader.items():
        if isinstance(val, dict) and "videoInfoRes" in val:
            items = val["videoInfoRes"].get("item_list", [])
            if items:
                return items[0]
    # 兜底:全量搜索任何含 item_list 的层级
    def walk(node):
        if isinstance(node, dict):
            if "item_list" in node and node["item_list"]:
                return node["item_list"][0]
            for v in node.values():
                got = walk(v)
                if got:
                    return got
        elif isinstance(node, list):
            for v in node:
                got = walk(v)
                if got:
                    return got
        return None
    return walk(loader)


def normalize(raw: dict, aweme_id: str) -> dict:
    from .render import split_desc

    video = raw.get("video") or {}
    play_addr = video.get("play_addr") or {}
    url_list = play_addr.get("url_list") or []
    desc = (raw.get("desc") or "").strip() or f"抖音视频 {aweme_id}"
    title, description = split_desc(desc)
    author = (raw.get("author") or {}).get("nickname") or "未知作者"

    create_time = raw.get("create_time")
    published = ""
    if create_time:
        from datetime import datetime, timezone, timedelta
        dt = datetime.fromtimestamp(int(create_time), tz=timezone(timedelta(hours=8)))
        published = dt.strftime("%Y-%m-%d")

    is_image_post = bool(raw.get("image_list")) and not url_list
    if not url_list:
        if is_image_post:
            raise ParseError("这是一条图文帖(不含视频),当前版本只支持视频。")
        raise ParseError("未能从数据中取得视频直链(url_list 为空)。")

    duration_ms = int(video.get("duration") or play_addr.get("duration") or 0)

    web_url = f"https://www.douyin.com/video/{aweme_id}"
    return {
        "aweme_id": aweme_id,
        "title": title,
        "description": description,
        "author": author,
        "published": published,
        "web_url": web_url,
        "play_url": url_list[0],
        "url_candidates": url_list,
        "duration_sec": round(duration_ms / 1000),
    }


def download_video(play_url: str, save_to: Path, proxies: dict | None = None) -> Path:
    """把分享页拿到的直链下载为 mp4。直链域名一般是 iesdouyin.com/aweme/v1/play/"""
    resp = requests.get(play_url, headers=_HEADERS, stream=True,
                        timeout=(20, 120), proxies=proxies)
    if resp.status_code != 200:
        raise ParseError(f"视频下载失败 HTTP {resp.status_code}")
    save_to.parent.mkdir(parents=True, exist_ok=True)
    with open(save_to, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 256):
            f.write(chunk)
    size = save_to.stat().st_size
    if size < 10_000:
        raise ParseError(f"下载的文件过小({size} 字节),疑似被风控拦截。内容预览:"
                         + save_to.read_bytes()[:200].decode(errors="replace"))
    return save_to
