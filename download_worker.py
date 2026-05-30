from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from engine import DownloadCancelled, build_ydl_options, inspect_environment


class TaskStatus(str, Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class DownloadTask:
    task_id: str
    url: str
    format_key: str
    output_dir: Path
    title: str = "等待解析…"
    thumbnail: str = ""
    duration: str = ""
    quality_label: str = ""
    format_label: str = "MP4"
    file_size: str = ""
    progress: float = 0.0
    speed: str = ""
    eta: str = ""
    status: TaskStatus = TaskStatus.QUEUED
    error: str = ""
    cookie_file: Optional[Path] = None
    subtitles: bool = False


class DownloadWorker(QThread):
    task_updated = pyqtSignal(str)
    task_finished = pyqtSignal(str, bool, str)
    log_message = pyqtSignal(str)
    global_speed = pyqtSignal(str)

    def __init__(self, tasks: list[DownloadTask], parent=None) -> None:
        super().__init__(parent)
        self._tasks = {t.task_id: t for t in tasks}
        self._cancelled = False
        self._current_id: Optional[str] = None

    def cancel(self) -> None:
        self._cancelled = True

    def get_task(self, task_id: str) -> Optional[DownloadTask]:
        return self._tasks.get(task_id)

    def all_tasks(self) -> list[DownloadTask]:
        return list(self._tasks.values())

    def _emit_update(self, task_id: str) -> None:
        self.task_updated.emit(task_id)

    def run(self) -> None:
        try:
            import yt_dlp
        except ImportError:
            for task in self._tasks.values():
                task.status = TaskStatus.FAILED
                task.error = "未安装 yt-dlp"
                self.task_finished.emit(task.task_id, False, task.error)
            return

        env = inspect_environment()
        if not env.yt_dlp_ready:
            for task in self._tasks.values():
                task.status = TaskStatus.FAILED
                task.error = "未安装 yt-dlp"
                self.task_finished.emit(task.task_id, False, task.error)
            return

        for task in self._tasks.values():
            if self._cancelled:
                task.status = TaskStatus.CANCELLED
                self.task_finished.emit(task.task_id, False, "已取消")
                continue

            self._current_id = task.task_id
            task.status = TaskStatus.DOWNLOADING
            self._emit_update(task.task_id)

            cancel_flag = {"v": False}

            def cancel_check() -> bool:
                return self._cancelled or cancel_flag["v"]

            def hook(data: dict) -> None:
                if cancel_check():
                    raise DownloadCancelled()
                if data.get("status") == "downloading":
                    total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                    downloaded = data.get("downloaded_bytes") or 0
                    task.progress = (downloaded / total * 100) if total else task.progress
                    task.speed = data.get("_speed_str") or ""
                    task.eta = data.get("_eta_str") or ""
                    if task.speed:
                        self.global_speed.emit(task.speed)
                    self._emit_update(task.task_id)

            opts = build_ydl_options(
                task.output_dir,
                task.format_key,
                subtitles=task.subtitles,
                cookie_file=task.cookie_file,
            )
            opts["progress_hooks"] = [hook]
            opts["logger"] = _QuietLogger(self.log_message.emit)

            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(task.url, download=False)
                    if info is None:
                        raise RuntimeError("无法读取视频信息")
                    if info.get("_type") == "playlist":
                        task.title = info.get("title") or "播放列表"
                        ydl.download([task.url])
                    else:
                        task.title = info.get("title") or task.url
                        task.thumbnail = info.get("thumbnail") or ""
                        duration = info.get("duration")
                        if duration:
                            mins, secs = divmod(int(duration), 60)
                            task.duration = f"{mins}:{secs:02d}"
                        ydl.download([task.url])
                task.progress = 100.0
                task.status = TaskStatus.COMPLETED
                self.task_finished.emit(task.task_id, True, "完成")
            except DownloadCancelled:
                task.status = TaskStatus.CANCELLED
                self.task_finished.emit(task.task_id, False, "已取消")
            except Exception as exc:
                task.status = TaskStatus.FAILED
                task.error = str(exc)
                self.task_finished.emit(task.task_id, False, str(exc))
            finally:
                self._emit_update(task.task_id)

        self.global_speed.emit("")


def new_task(
    url: str,
    format_key: str,
    output_dir: Path,
    *,
    quality_label: str,
    format_label: str,
    cookie_file: Optional[Path] = None,
    subtitles: bool = False,
) -> DownloadTask:
    return DownloadTask(
        task_id=str(uuid.uuid4()),
        url=url,
        format_key=format_key,
        output_dir=output_dir,
        quality_label=quality_label,
        format_label=format_label,
        cookie_file=cookie_file,
        subtitles=subtitles,
    )


class _QuietLogger:
    def __init__(self, emit) -> None:
        self._emit = emit

    def debug(self, msg: str) -> None:
        pass

    def info(self, msg: str) -> None:
        if not msg.startswith("[debug]"):
            self._emit(msg)

    def warning(self, msg: str) -> None:
        self._emit(f"警告: {msg}")

    def error(self, msg: str) -> None:
        self._emit(f"错误: {msg}")
