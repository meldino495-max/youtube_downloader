"""Check and apply updates from GitHub Releases."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from paths_config import get_app_dir
from version import __version__

GITHUB_OWNER = "secure-artifacts"
GITHUB_REPO = "youtube_downloader"
RELEASE_API = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
)
RELEASE_PAGE = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
ASSET_NAME = "YouTubeDownloader.exe"
USER_AGENT = f"YouTubeDownloader/{__version__}"

ProgressCallback = Callable[[float, str], None]


@dataclass(frozen=True)
class ReleaseInfo:
    tag: str
    version: tuple[int, ...]
    download_url: str
    html_url: str


def parse_version(text: str) -> tuple[int, ...]:
    cleaned = text.strip().lstrip("vV")
    parts: list[int] = []
    for piece in re.split(r"[.\-+]", cleaned):
        if not piece:
            continue
        if piece.isdigit():
            parts.append(int(piece))
        else:
            break
    return tuple(parts) if parts else (0,)


def current_version() -> tuple[int, ...]:
    return parse_version(__version__)


def current_version_label() -> str:
    return __version__


def is_newer(latest: tuple[int, ...], current: tuple[int, ...]) -> bool:
    width = max(len(latest), len(current))
    latest_pad = latest + (0,) * (width - len(latest))
    current_pad = current + (0,) * (width - len(current))
    return latest_pad > current_pad


def can_self_update() -> bool:
    return bool(getattr(sys, "frozen", False))


def running_executable() -> Optional[Path]:
    if not can_self_update():
        return None
    return Path(sys.executable).resolve()


def fetch_latest_release() -> ReleaseInfo:
    request = urllib.request.Request(
        RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitHub API HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc

    tag = str(payload.get("tag_name", "")).strip()
    if not tag:
        raise RuntimeError("Release tag missing")

    download_url = ""
    for asset in payload.get("assets") or []:
        if asset.get("name") == ASSET_NAME:
            download_url = str(asset.get("browser_download_url", "")).strip()
            break
    if not download_url:
        raise RuntimeError(f"Asset not found: {ASSET_NAME}")

    return ReleaseInfo(
        tag=tag,
        version=parse_version(tag),
        download_url=download_url,
        html_url=str(payload.get("html_url", RELEASE_PAGE)).strip() or RELEASE_PAGE,
    )


def check_for_update() -> tuple[bool, ReleaseInfo, tuple[int, ...]]:
    latest = fetch_latest_release()
    current = current_version()
    return is_newer(latest.version, current), latest, current


def download_release(
    release: ReleaseInfo,
    destination: Path,
    progress: Optional[ProgressCallback] = None,
) -> Path:
    if not release.download_url.startswith("https://github.com/"):
        raise RuntimeError("Invalid download URL")

    request = urllib.request.Request(
        release.download_url,
        headers={"User-Agent": USER_AGENT},
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = destination.with_suffix(destination.suffix + ".part")

    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            total = int(response.headers.get("Content-Length", 0) or 0)
            read = 0
            chunk_size = 256 * 1024
            with tmp_path.open("wb") as handle:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    handle.write(chunk)
                    read += len(chunk)
                    if progress and total > 0:
                        progress(min(100.0, read * 100.0 / total), release.tag)
        tmp_path.replace(destination)
    except Exception:
        if tmp_path.is_file():
            tmp_path.unlink(missing_ok=True)
        raise

    if progress:
        progress(100.0, release.tag)
    return destination


def apply_update_and_restart(update_file: Path, target_exe: Optional[Path] = None) -> None:
    exe = target_exe or running_executable()
    if exe is None:
        raise RuntimeError("Self-update is only available for packaged exe builds")

    update_file = update_file.resolve()
    exe = exe.resolve()
    if not update_file.is_file():
        raise RuntimeError(f"Update file missing: {update_file}")

    script = exe.parent / "_youtube_apply_update.bat"
    script.write_text(
        "\n".join(
            [
                "@echo off",
                "chcp 65001 >nul",
                "timeout /t 2 /nobreak >nul",
                f'move /Y "{update_file}" "{exe}"',
                f'start "" "{exe}"',
                'del "%~f0"',
            ]
        ),
        encoding="utf-8",
    )

    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        ["cmd", "/c", str(script)],
        cwd=str(exe.parent),
        creationflags=flags,
        close_fds=True,
    )


def default_update_download_path() -> Path:
    exe = running_executable()
    if exe is not None:
        return exe.with_name(f"{exe.stem}.update{exe.suffix}")
    return get_app_dir() / ASSET_NAME
