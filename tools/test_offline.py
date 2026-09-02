"""离线自测:不联网、不碰真实 Obsidian 仓库,验证转写缓存复用与笔记渲染链路。

    python tools/test_offline.py

覆盖:
  1. 旧格式转写缓存(纯段列表)命中 → 免听写,视频归档,笔记正常渲染
  2. 新格式缓存({"model","segments"})且模型匹配 → 命中
  3. 缓存的 model 与配置不符 → 作废缓存走重新下载(离线下直链必失败,借断言报错)
  4. obsidian:// URI 构造(vault 名与相对路径的百分号编码)
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dyclip import pipeline  # noqa: E402


def make_cfg(tmp: Path, model: str = "small") -> dict:
    return {
        "vault_path": tmp / "vault",
        "notes_dir": "notes",
        "assets_dir": "assets",
        "downloads_dir": tmp / "downloads",
        "model_size": model,
        "max_video_sec": 600,
        "open_note": False,
    }


def make_item(aweme_id: str = "test123") -> dict:
    return {
        "aweme_id": aweme_id,
        "title": "离线自测视频",
        "description": "这是一段用于离线自测的简介。",
        "author": "测试作者",
        "published": "2026-09-02",
        "web_url": f"https://www.douyin.com/video/{aweme_id}",
        "play_url": "http://127.0.0.1:9/none.mp4",
        "url_candidates": ["http://127.0.0.1:9/none.mp4"],
        "duration_sec": 65,
    }


SEGS = [{"start": i * 1.0, "end": i * 1.0 + 0.9, "text": f"第{i}句。"}
        for i in range(6)]


def fresh_tmp() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="dyclip-test-"))
    (tmp / "downloads").mkdir(parents=True)
    (tmp / "downloads" / "test123.mp4").write_bytes(b"0" * 20_000)
    return tmp


def test_uri():
    cfg = {"vault_path": Path("C:/tmp/我的仓库")}
    uri = pipeline.obsidian_open_uri(cfg, Path("C:/tmp/我的仓库/收件箱/笔记.md"))
    assert uri == ("obsidian://open?vault=%E6%88%91%E7%9A%84%E4%BB%93%E5%BA%93"
                   "&file=%E6%94%B6%E4%BB%B6%E7%AE%B1/%E7%AC%94%E8%AE%B0.md"), uri
    print("PASS obsidian:// URI 构造与编码")


def test_legacy_cache():
    tmp = fresh_tmp()
    (tmp / "downloads" / "test123.transcript.json").write_text(
        json.dumps(SEGS, ensure_ascii=False), encoding="utf-8")
    pipeline._run(make_cfg(tmp), make_item())
    text = next((tmp / "vault" / "notes").glob("*.md")).read_text(encoding="utf-8")
    assert "第0句。第1句。" in text, text
    assert "![[离线自测视频.mp4]]" in text, text
    assert (tmp / "vault" / "assets" / "离线自测视频.mp4").exists()
    print("PASS 旧格式缓存复用(免听写,视频归档,笔记渲染)")


def test_dict_cache():
    tmp = fresh_tmp()
    (tmp / "downloads" / "test123.transcript.json").write_text(
        json.dumps({"model": "small", "segments": SEGS}, ensure_ascii=False),
        encoding="utf-8")
    pipeline._run(make_cfg(tmp), make_item())
    assert next((tmp / "vault" / "notes").glob("*.md"))
    print("PASS 新格式缓存复用")


def test_model_mismatch_refetch():
    tmp = fresh_tmp()
    (tmp / "downloads" / "test123.transcript.json").write_text(
        json.dumps({"model": "tiny", "segments": SEGS}, ensure_ascii=False),
        encoding="utf-8")
    raised = False
    try:
        pipeline._run(make_cfg(tmp, model="small"), make_item())
    except Exception:
        # 离线环境:重转写会在解码假 mp4 时失败,这正是"没有复用缓存"的证明
        raised = True
    assert raised, "模型不匹配时应放弃缓存重新转写,而不是复用旧缓存完成任务"
    assert not list((tmp / "vault" / "notes").glob("*.md"))
    print("PASS 模型不匹配 → 缓存作废,重新转写(离线在解码假 mp4 处失败,符合预期)")


if __name__ == "__main__":
    try:
        test_uri()
        test_legacy_cache()
        test_dict_cache()
        test_model_mismatch_refetch()
        print("全部通过 ✓")
    finally:
        # 各测试目录带 dyclip-test- 前缀,统一清扫
        for d in Path(tempfile.gettempdir()).glob("dyclip-test-*"):
            shutil.rmtree(d, ignore_errors=True)
