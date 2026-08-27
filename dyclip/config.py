import shutil
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_config = None


def load() -> dict:
    global _config
    if _config is not None:
        return _config

    path = PROJECT_ROOT / "config.toml"
    if not path.exists():
        raise SystemExit(
            "未找到 config.toml。请先复制 config.example.toml 为 config.toml 并填写你的仓库路径。"
        )
    with open(path, "rb") as f:
        cfg = tomllib.load(f)

    vault = Path(cfg["vault_path"])
    if not vault.is_dir():
        raise SystemExit(f"vault_path 不存在: {vault}")

    downloads = Path(cfg.get("downloads_dir", "downloads"))
    if not downloads.is_absolute():
        downloads = PROJECT_ROOT / downloads
    downloads.mkdir(parents=True, exist_ok=True)

    _config = {
        "vault_path": vault,
        "notes_dir": cfg.get("notes_dir", "剪藏/抖音"),
        "assets_dir": cfg.get("assets_dir", "附件/抖音"),
        "model_size": cfg.get("model_size", "small"),
        "token": str(cfg.get("token", "")),
        # 超过该时长(秒)的视频直接拒收,防止误点长视频烧掉大量时间
        "max_video_sec": int(cfg.get("max_video_sec", 600)),
        "downloads_dir": downloads,
    }
    return _config


def require_ffmpeg_hint() -> str | None:
    """ffmpeg 非必需(faster-whisper 自带 PyAV 解码),保留检测用于未来扩展"""
    return shutil.which("ffmpeg")
