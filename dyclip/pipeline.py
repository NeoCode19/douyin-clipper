"""命令行入口:

    python -m dyclip <抖音分享链接或完整链接>

流程:解析链接 -> 拉元数据 -> 下载视频 -> faster-whisper 转写
      -> 渲染 Markdown -> 写入 Obsidian 仓库 -> 归档视频。
"""
from __future__ import annotations

import functools
import sys
import threading

from . import config, parse, render

_model_lock = threading.Lock()


@functools.lru_cache(maxsize=2)
def _load_model(model_size: str):
    from faster_whisper import WhisperModel
    return WhisperModel(model_size, device="cpu", compute_type="int8",
                        cpu_threads=12)


def warm_model(model_size: str) -> None:
    """把模型提前搬进内存(可与视频下载并行)"""
    with _model_lock:
        _load_model(model_size)


def transcribe(audio_path, model_size: str, language: str = "zh"):
    model = _load_model(model_size)

    print("[3/4] 开始听写…")
    segments_iter, info = model.transcribe(
        str(audio_path),
        language=language,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        beam_size=1,                        # 贪心解码:口播场景质量无感、速度提升明显
        condition_on_previous_text=False,   # 避免长稿幻觉连锁,还能提速
    )
    transcript = []
    for seg in segments_iter:
        transcript.append({"start": seg.start, "end": seg.end, "text": seg.text})
    return transcript, info


def load_item_from_json(json_path):
    """旁路入口:从浏览器抓包导出的 JSON 文件构造 item(应对纯爬虫被风控)"""
    import json
    from pathlib import Path as P
    from .render import split_desc

    data = json.loads(P(json_path).read_text(encoding="utf-8"))
    urls = data.get("play_urls") or []
    if not urls:
        raise SystemExit(f"{json_path} 中没有 play_urls")
    title, description = split_desc(data.get("desc") or "抖音视频")
    published = data.get("published", "")
    if not published and data.get("create_time"):
        from datetime import datetime, timezone, timedelta
        published = datetime.fromtimestamp(
            int(data["create_time"]),
            tz=timezone(timedelta(hours=8)),
        ).strftime("%Y-%m-%d")
    return {
        "aweme_id": data.get("aweme_id") or "unknown",
        "title": title,
        "description": description,
        "author": data.get("author") or "未知作者",
        "published": published,
        "web_url": f"https://www.douyin.com/video/{data.get('aweme_id') or ''}",
        "play_url": urls[0],
        "url_candidates": urls,
        "duration_sec": round(int(data.get("duration_ms") or 0) / 1000),
    }


def main(argv: list[str]) -> None:
    if len(argv) == 3 and argv[1] == "--from-json":
        print(f"[0/4] 从抓包 JSON 进料:{argv[2]}")
        cfg = config.load()
        _run(cfg, load_item_from_json(argv[2]))
        return
    if len(argv) != 2:
        print("用法: python -m dyclip <抖音链接>  或  python -m dyclip --from-json <提取.json>")
        sys.exit(1)

    url = argv[1].strip()
    cfg = config.load()

    proxies = None
    import os
    if os.environ.get("DYCLIP_PROXY"):
        proxies = {"http": os.environ["DYCLIP_PROXY"],
                   "https": os.environ["DYCLIP_PROXY"]}

    print(f"[1/4] 解析链接:{url[:60]}{'…' if len(url) > 60 else ''}")
    aweme_id = parse.resolve_aweme_id(url, proxies)
    item = parse.fetch_item(aweme_id, proxies)
    _run(cfg, item)


def _run(cfg, item) -> None:
    import os
    import time
    from pathlib import Path
    t0 = time.monotonic()

    max_sec = int(cfg.get("max_video_sec", 600))
    if item.get("duration_sec") and item["duration_sec"] > max_sec:
        raise SystemExit(
            f"该视频时长 {render.fmt_ts(item['duration_sec'])},"
            f"超过配置上限 {max_sec // 60} 分钟(max_video_sec),已拒收。"
            "确要剪藏长视频请调大 config.toml 中的 max_video_sec。")
    proxies_env = os.environ.get("DYCLIP_PROXY")
    proxies = {"http": proxies_env, "https": proxies_env} if proxies_env else None

    print(f"      标题:{item['title']}")
    print(f"      作者:{item['author']} · 发布:{item['published'] or '未知'}"
          f" · 时长:{render.fmt_ts(item['duration_sec'])}")

    video_path = cfg["downloads_dir"] / f"{item['aweme_id']}.mp4"
    need_download = not (video_path.exists()
                         and video_path.stat().st_size > 10_000)

    # 模型预热与下载并行:两者一个吃网络一个吃 CPU/磁盘,互不抢路
    warmer = None
    if need_download:
        warmer = threading.Thread(target=warm_model, args=(cfg["model_size"],),
                                  daemon=True)
        warmer.start()

    if not need_download:
        print(f"[2/4] 复用已下载的视频:{video_path.name}")
    else:
        print("[2/4] 下载视频…")
        last_err = None
        for cand in [item["play_url"], *item["url_candidates"][1:]]:
            try:
                parse.download_video(cand, video_path, proxies)
                break
            except Exception as e:
                last_err = e
        else:
            raise SystemExit(f"所有直链下载失败,最后错误:{last_err}")
        print(f"      已保存:{video_path} ({video_path.stat().st_size // 1024} KB)")

    if warmer is not None:
        warmer.join()

    try:
        transcript, info = transcribe(video_path, cfg["model_size"])
    except Exception:
        if video_path.exists() and video_path.stat().st_size < 10_000:
            video_path.unlink(missing_ok=True)
        raise

    if not transcript:
        raise SystemExit("转写结果为空:视频可能没有人声(纯音乐/BGM?)。")
    print(f"      转写完成:{len(transcript)} 段,"
          f"检测语言={info.language}(置信度 {info.language_probability:.0%})")

    import json
    cache_path = cfg["downloads_dir"] / f"{item['aweme_id']}.transcript.json"
    cache_path.write_text(json.dumps(transcript, ensure_ascii=False), encoding="utf-8")

    stem = render.note_stem(item["title"], item["aweme_id"])

    import shutil
    assets_dir = cfg["vault_path"] / cfg["assets_dir"]
    assets_dir.mkdir(parents=True, exist_ok=True)
    target = assets_dir / f"{stem}.mp4"
    print(f"[3.5/4] 视频归档进仓库:{cfg['assets_dir']}/{target.name}")
    Path(target).unlink(missing_ok=True)
    shutil.move(str(video_path), str(target))
    size_mb = target.stat().st_size / 1024 / 1024

    md = render.render_note(item, transcript, target.name)
    out_dir = cfg["vault_path"] / cfg["notes_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / render.safe_filename(item["title"], item["aweme_id"])
    out_path.write_text(md, encoding="utf-8")

    print(f"[4/4] 笔记已写入:{out_path}")
    words = sum(len(s["text"]) for s in transcript)
    elapsed = time.monotonic() - t0
    print(f"      文稿约 {words} 字 · 视频已归档 {size_mb:.1f} MB"
          f" · 全程 {elapsed:.0f} 秒。完成 ✓")


if __name__ == "__main__":
    main(sys.argv)
