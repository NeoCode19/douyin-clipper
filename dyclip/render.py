"""渲染 Obsidian 笔记 — 与 Obsidian Web Clipper 官方「默认」模板结构对齐

参照 默认-clipper.json(schemaVersion 0.1.0):
  frontmatter: title / source / author(wikilink数组) / published / created /
               description / tags(clippings)
  文件名:     {{title}}
  正文:       纯净正文,无额外包装(本工具放入文稿段落流,不使用时间戳)
"""
from __future__ import annotations

import re
from datetime import datetime

INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|#^\[\]\r\n\t]')


def split_desc(desc: str) -> tuple[str, str]:
    """抖音 desc 第一行视为标题,整体(压平换行)作为简介"""
    flat = " ".join(desc.split())
    first_line = next((ln.strip() for ln in desc.splitlines() if ln.strip()), "")
    title = flat[:120] if not first_line else " ".join(first_line.split())[:120]
    return title or "抖音视频", flat


def note_stem(title: str, aweme_id: str, max_len: int = 60) -> str:
    """笔记/附件通用的安全文件主干"""
    name = INVALID_FILENAME_CHARS.sub("", title)
    name = re.sub(r"\s+", " ", name).strip()
    if len(name) > max_len:
        name = name[:max_len]
    return name or f"抖音视频 {aweme_id}"


def safe_filename(title: str, aweme_id: str, max_len: int = 60) -> str:
    return f"{note_stem(title, aweme_id, max_len)}.md"


def join_paragraphs(transcript: list[dict], per_paragraph: int = 4) -> str:
    """把逐句转写合并成自然段落流(中文,不加空格)"""
    texts = [seg["text"].strip() for seg in transcript if seg["text"].strip()]
    paragraphs = [
        "".join(texts[i:i + per_paragraph])
        for i in range(0, len(texts), per_paragraph)
    ]
    return "\n\n".join(paragraphs)


def fmt_ts(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h:d}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


def render_note(item: dict, transcript: list[dict],
                video_file: str | None = None) -> str:
    """结构与用户既有 YouTube 视频剪藏笔记对齐:

      frontmatter 七字段(tags 含 视频转录)
      > [!info]- 视频信息(折叠 callout)
      ![[视频.mp4]] 内嵌
      ## 简介 -> ## 转录
    transcript 时间戳仅入参备用,正文为纯段落流。
    """
    author = item.get("author") or "未知作者"
    published = item.get("published") or ""
    description = item.get("description") or ""
    now = datetime.now().astimezone()

    out: list[str] = [
        "---",
        f'title: "{item["title"].replace(chr(34), chr(39))}"',
        f'source: "{item["web_url"]}"',
        "author:",
        f'  - "{author.replace(chr(34), chr(39))}"',
        f'published: {published}' if published else 'published: ""',
        f"created: {now.isoformat(timespec='seconds')}",
        'tags:',
        '  - "clippings"',
        '  - "视频转录"',
        "---",
        "",
        "> [!info]- 视频信息",
        f"> **频道**:{author}",
        f"> **发布**:{published or '未知'}",
        f"> **时长**:{fmt_ts(item.get('duration_sec') or 0)}",
        f"> **链接**:[在抖音打开]({item['web_url']})",
    ]
    if video_file:
        out += ["", f"![[{video_file}]]"]
    if description:
        out += ["", "## 简介", "", description]
    out += ["", "## 转录", "", join_paragraphs(transcript)]
    return "\n".join(out) + "\n"
