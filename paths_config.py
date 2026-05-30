from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def get_app_dir() -> Path:
    """Writable app root: exe folder when frozen, source folder in dev."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_resource_dir() -> Path:
    """Bundled read-only assets (PyInstaller _MEIPASS when frozen)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", get_app_dir()))
    return Path(__file__).resolve().parent


def _refresh_windows_path() -> None:
    """GUI-launched exe may not inherit the user's PATH from the registry."""
    if sys.platform != "win32":
        return
    try:
        import winreg
    except ImportError:
        return

    parts: list[str] = []
    for root, subkey in (
        (winreg.HKEY_CURRENT_USER, r"Environment"),
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
    ):
        try:
            with winreg.OpenKey(root, subkey) as key:
                value, _ = winreg.QueryValueEx(key, "Path")
                if value:
                    parts.append(str(value))
        except OSError:
            continue
    merged = ";".join(parts + [os.environ.get("PATH", "")])
    os.environ["PATH"] = merged


if getattr(sys, "frozen", False):
    _refresh_windows_path()

APP_DIR = get_app_dir()
CONFIG_PATH = APP_DIR / "config.json"
DEFAULT_FFMPEG_DIR = APP_DIR / "tools" / "ffmpeg"
DEFAULT_NODEJS_DIR = APP_DIR / "tools" / "nodejs"
DEFAULT_YTDLP_DIR = APP_DIR / "tools" / "ytdlp"
VENV_DIR = APP_DIR / ".venv"


@dataclass
class InstallPaths:
    ytdlp_dir: Path
    ffmpeg_dir: Path
    nodejs_dir: Path

    @classmethod
    def defaults(cls) -> InstallPaths:
        return cls(
            ytdlp_dir=DEFAULT_YTDLP_DIR,
            ffmpeg_dir=DEFAULT_FFMPEG_DIR,
            nodejs_dir=DEFAULT_NODEJS_DIR,
        )

    @classmethod
    def from_config(cls, config: Optional[dict] = None) -> InstallPaths:
        cfg = config if config is not None else load_config()
        raw = cfg.get("install_paths") or {}
        paths = cls(
            ytdlp_dir=_resolve_dir(raw.get("ytdlp"), DEFAULT_YTDLP_DIR),
            ffmpeg_dir=_resolve_dir(raw.get("ffmpeg"), DEFAULT_FFMPEG_DIR),
            nodejs_dir=_resolve_dir(raw.get("nodejs"), DEFAULT_NODEJS_DIR),
        )
        return normalize_install_targets(paths)

    def to_config_dict(self) -> dict[str, str]:
        return {
            "ytdlp": str(self.ytdlp_dir),
            "ffmpeg": str(self.ffmpeg_dir),
            "nodejs": str(self.nodejs_dir),
        }


def _resolve_dir(value: Optional[str], default: Path) -> Path:
    if value and str(value).strip():
        return Path(str(value).strip())
    return default


def load_config() -> dict:
    if not CONFIG_PATH.is_file():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_install_paths(paths: InstallPaths) -> None:
    config = load_config()
    config["install_paths"] = paths.to_config_dict()
    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def ensure_ytdlp_on_path(paths: Optional[InstallPaths] = None) -> None:
    target = (paths or InstallPaths.from_config()).ytdlp_dir
    text = str(target)
    if target.is_dir() and text not in sys.path:
        sys.path.insert(0, text)


def _common_node_exe_paths() -> list[Path]:
    candidates: list[Path] = []
    for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env_name)
        if base:
            candidates.append(Path(base) / "nodejs" / "node.exe")
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "Programs" / "node" / "node.exe")
    return candidates


def _find_on_path(name: str) -> Optional[Path]:
    import shutil

    found = shutil.which(name)
    if found:
        return Path(found)
    if sys.platform == "win32" and name == "node":
        for candidate in _common_node_exe_paths():
            if candidate.is_file():
                return candidate
    return None


def find_ffmpeg_exe(paths: Optional[InstallPaths] = None) -> Optional[Path]:
    install_paths = paths or InstallPaths.from_config()
    for name in ("ffmpeg.exe", "ffmpeg"):
        candidate = install_paths.ffmpeg_dir / name
        if candidate.is_file():
            return candidate
    system = _find_on_path("ffmpeg")
    if system:
        return system
    return None


def normalize_install_targets(paths: InstallPaths) -> InstallPaths:
    """Use app-local tools/ dirs as install targets when saved paths have no binaries."""
    defaults = InstallPaths.defaults()

    ytdlp_dir = paths.ytdlp_dir
    if not (ytdlp_dir / "yt-dlp.exe").is_file():
        ytdlp_dir = defaults.ytdlp_dir

    ffmpeg_dir = paths.ffmpeg_dir
    if not (ffmpeg_dir / "ffmpeg.exe").is_file():
        ffmpeg_dir = defaults.ffmpeg_dir

    nodejs_dir = paths.nodejs_dir
    if not (nodejs_dir / "node.exe").is_file():
        nodejs_dir = defaults.nodejs_dir

    return InstallPaths(
        ytdlp_dir=ytdlp_dir,
        ffmpeg_dir=ffmpeg_dir,
        nodejs_dir=nodejs_dir,
    )


def detected_install_paths(paths: Optional[InstallPaths] = None) -> InstallPaths:
    """Return folders where components are actually found (for UI display)."""
    base = paths or InstallPaths.from_config()
    defaults = InstallPaths.defaults()

    ytdlp_dir = base.ytdlp_dir
    if (ytdlp_dir / "yt-dlp.exe").is_file():
        pass
    else:
        which = _find_on_path("yt-dlp")
        if which:
            ytdlp_dir = Path(which).parent
        elif ytdlp_is_ready(base):
            ytdlp_dir = base.ytdlp_dir
        else:
            ytdlp_dir = defaults.ytdlp_dir

    ffmpeg_exe = find_ffmpeg_exe(base)
    ffmpeg_dir = ffmpeg_exe.parent if ffmpeg_exe else defaults.ffmpeg_dir

    node_exe = find_node_exe(base)
    nodejs_dir = node_exe.parent if node_exe else defaults.nodejs_dir

    return InstallPaths(
        ytdlp_dir=ytdlp_dir,
        ffmpeg_dir=ffmpeg_dir,
        nodejs_dir=nodejs_dir,
    )


def find_node_exe(paths: Optional[InstallPaths] = None) -> Optional[Path]:
    install_paths = paths or InstallPaths.from_config()
    candidate = install_paths.nodejs_dir / "node.exe"
    if candidate.is_file():
        return candidate
    system = _find_on_path("node")
    if system:
        return system
    return None


def ytdlp_is_ready(paths: Optional[InstallPaths] = None) -> bool:
    ensure_ytdlp_on_path(paths)
    try:
        import yt_dlp  # noqa: F401

        return True
    except ImportError:
        return False
