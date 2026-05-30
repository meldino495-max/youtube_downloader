"""Detect already-downloaded YouTube videos and skip duplicates."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Optional

VIDEO_ID_IN_NAME = re.compile(r"\[([A-Za-z0-9_-]{11})\]")
CHANNEL_URL = re.compile(
    r"youtube\.com/(?:@[\w.-]+(?:/[\w.-]+)?|channel/[\w-]+|c/[\w.-]+|user/[\w.-]+)",
    re.IGNORECASE,
)

MEDIA_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".webm",
    ".mp3",
    ".m4a",
    ".opus",
    ".wav",
    ".flv",
    ".avi",
    ".mov",
}


def classify_url(url: str) -> str:
    """Return ``video``, ``playlist``, or ``channel``."""
    lower = url.strip().lower()
    if CHANNEL_URL.search(lower):
        return "channel"
    if "list=" in lower:
        return "playlist"
    return "video"


def video_id_from_filename(name: str) -> Optional[str]:
    matches = VIDEO_ID_IN_NAME.findall(name)
    if not matches:
        return None
    return matches[-1]


def _scan_folder(folder: Path, ids: set[str]) -> None:
    try:
        items = list(folder.iterdir())
    except OSError:
        return
    for item in items:
        if not item.is_file():
            continue
        if item.suffix.lower() not in MEDIA_EXTENSIONS and item.suffix:
            continue
        vid = video_id_from_filename(item.name)
        if vid:
            ids.add(vid)


def collect_existing_video_ids(
    directory: Path,
    *,
    url_kind: str = "video",
) -> set[str]:
    """
    Collect YouTube video IDs from filenames like ``Title [dQw4w9WgXcQ].mp4``.

    - playlist / video: only files directly in ``directory``
    - channel: files inside each playlist subfolder, plus files in ``directory``
    """
    ids: set[str] = set()
    if not directory.is_dir():
        return ids

    if url_kind in ("video", "playlist"):
        _scan_folder(directory, ids)
        return ids

    for item in directory.iterdir():
        if item.is_dir():
            _scan_folder(item, ids)
    _scan_folder(directory, ids)
    return ids


def build_output_template(output_dir: Path, url_kind: str) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    if url_kind == "channel":
        return str(
            output_dir / "%(playlist_title|Uploads)s" / "%(title)s [%(id)s].%(ext)s"
        )
    return str(output_dir / "%(title)s [%(id)s].%(ext)s")


def make_skip_filter(
    existing_ids: set[str],
    log: Callable[[str], None],
    skipped_counter: list[int],
) -> Callable:
    """Build a yt-dlp ``match_filter`` callback."""

    def skip_filter(info: dict, *, incomplete: bool = False) -> Optional[str]:
        vid = info.get("id")
        if not vid:
            return None
        if vid in existing_ids:
            title = info.get("title") or vid
            playlist = info.get("playlist_title") or info.get("playlist") or ""
            if playlist:
                log(f"跳过（已存在）: {title} [{vid}]  ← 播放列表「{playlist}」")
            else:
                log(f"跳过（已存在）: {title} [{vid}]")
            skipped_counter[0] += 1
            return "already downloaded"
        return None

    return skip_filter


def url_kind_label(url_kind: str) -> str:
    return {"video": "单个视频", "playlist": "播放列表", "channel": "频道"}.get(
        url_kind, url_kind
    )
