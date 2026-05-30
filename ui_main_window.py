from __future__ import annotations

import json
import os
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QFont, QPixmap
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QFileDialog,
    QProgressBar,
    QButtonGroup,
)

from deps_installer import ensure_dependencies, missing_components, optional_components
from download_worker import DownloadTask, DownloadWorker, TaskStatus, new_task
from engine import default_download_dir, extract_urls, format_label, inspect_environment
from ui_theme import COLORS, FORMAT_OPTIONS, QUALITY_OPTIONS

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"


def load_stylesheet() -> str:
    c = COLORS
    return f"""
    QMainWindow, QWidget {{
        background: {c['bg']};
        color: {c['text']};
        font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
        font-size: 13px;
    }}
    QFrame#sidebar {{
        background: {c['sidebar']};
        border-right: 1px solid {c['border']};
    }}
    QFrame#card, QFrame#queueItem, QFrame#footerBar, QFrame#urlCard {{
        background: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: 12px;
    }}
    QLineEdit {{
        background: {c['surface_alt']};
        border: 1px solid {c['border']};
        border-radius: 10px;
        padding: 10px 14px;
        font-size: 14px;
    }}
    QLineEdit:focus {{
        border: 1px solid {c['accent']};
    }}
    QPushButton#primaryBtn {{
        background: {c['accent']};
        color: white;
        border: none;
        border-radius: 10px;
        padding: 10px 22px;
        font-weight: 600;
        font-size: 14px;
    }}
    QPushButton#primaryBtn:hover {{
        background: {c['accent_dark']};
    }}
    QPushButton#ghostBtn {{
        background: transparent;
        border: 1px solid {c['border']};
        border-radius: 8px;
        padding: 6px 12px;
    }}
    QPushButton#ghostBtn:hover {{
        background: {c['surface_alt']};
    }}
    QPushButton#navBtn {{
        background: transparent;
        border: none;
        border-radius: 10px;
        padding: 10px 14px;
        text-align: left;
        font-size: 14px;
    }}
    QPushButton#navBtn:checked {{
        background: {c['accent_soft']};
        color: {c['accent']};
        font-weight: 600;
    }}
    QPushButton#qualityBtn {{
        background: {c['surface']};
        border: 2px solid {c['border']};
        border-radius: 12px;
        padding: 12px 16px;
        min-width: 72px;
    }}
    QPushButton#qualityBtn:checked {{
        border: 2px solid {c['accent']};
        background: {c['accent_soft']};
        color: {c['accent']};
    }}
    QComboBox {{
        background: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: 10px;
        padding: 8px 12px;
        min-width: 160px;
    }}
    QProgressBar {{
        background: {c['surface_alt']};
        border: none;
        border-radius: 6px;
        height: 8px;
        text-align: center;
    }}
    QProgressBar::chunk {{
        background: {c['accent']};
        border-radius: 6px;
    }}
    QScrollArea {{
        border: none;
        background: transparent;
    }}
    """


class NavButton(QPushButton):
    def __init__(self, icon: str, text: str, badge: str = "", parent=None) -> None:
        label = f"  {icon}   {text}"
        if badge:
            label += f"   ({badge})"
        super().__init__(label, parent)
        self.setObjectName("navBtn")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class QualityButton(QPushButton):
    def __init__(self, key: str, title: str, subtitle: str, parent=None) -> None:
        super().__init__(f"{title}\n{subtitle}", parent)
        self.key = key
        self.setObjectName("qualityBtn")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)


class QueueItemWidget(QFrame):
    def __init__(self, task: DownloadTask, on_cancel, parent=None) -> None:
        super().__init__(parent)
        self.task = task
        self._on_cancel = on_cancel
        self._thumb_loaded = False
        self.setObjectName("queueItem")
        self._thumb = QLabel("▶")
        self._thumb.setFixedSize(120, 68)
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb.setStyleSheet(
            f"background:{COLORS['surface_alt']}; border-radius:8px; color:{COLORS['text_secondary']};"
        )
        self._duration = QLabel("", self._thumb)
        self._duration.setStyleSheet(
            "background:rgba(0,0,0,0.65); color:white; padding:2px 6px; border-radius:4px;"
        )
        self._duration.move(72, 44)
        self._title = QLabel(task.title)
        self._title.setWordWrap(True)
        font = self._title.font()
        font.setBold(True)
        self._title.setFont(font)
        self._meta = QLabel(
            f"{task.quality_label}  •  {task.format_label}  •  {task.file_size or '计算中…'}"
        )
        self._meta.setStyleSheet(f"color:{COLORS['text_secondary']};")
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setTextVisible(False)
        self._status = QLabel("排队中…")
        self._status.setStyleSheet(f"color:{COLORS['text_secondary']};")
        self._cancel_btn = QPushButton("✕")
        self._cancel_btn.setObjectName("ghostBtn")
        self._cancel_btn.setFixedSize(32, 32)
        self._cancel_btn.clicked.connect(lambda: self._on_cancel(task.task_id))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(14)
        layout.addWidget(self._thumb)
        info = QVBoxLayout()
        info.addWidget(self._title)
        info.addWidget(self._meta)
        info.addWidget(self._progress)
        info.addWidget(self._status)
        layout.addLayout(info, stretch=1)
        layout.addWidget(self._cancel_btn, alignment=Qt.AlignmentFlag.AlignTop)
        self.refresh()

    def refresh(self) -> None:
        t = self.task
        self._title.setText(t.title)
        self._meta.setText(
            f"{t.quality_label}  •  {t.format_label}  •  {t.file_size or '计算中…'}"
        )
        self._progress.setValue(int(t.progress))
        if t.duration:
            self._duration.setText(t.duration)
            self._duration.adjustSize()
        if t.status == TaskStatus.QUEUED:
            self._status.setText("排队中…")
        elif t.status == TaskStatus.DOWNLOADING:
            extra = f"  {t.speed}" if t.speed else ""
            self._status.setText(f"下载中… {t.progress:.0f}%{extra}")
        elif t.status == TaskStatus.COMPLETED:
            self._status.setText("已完成")
            self._status.setStyleSheet(f"color:{COLORS['success']};")
            self._cancel_btn.hide()
        elif t.status == TaskStatus.FAILED:
            self._status.setText(f"失败: {t.error}")
            self._status.setStyleSheet(f"color:{COLORS['accent']};")
        elif t.status == TaskStatus.CANCELLED:
            self._status.setText("已取消")
        if t.thumbnail and not self._thumb_loaded:
            self._thumb_loaded = True
            self._load_thumbnail(t.thumbnail)

    def _load_thumbnail(self, url: str) -> None:
        mgr = QNetworkAccessManager(self)

        def done(reply) -> None:
            data = reply.readAll()
            pix = QPixmap()
            if pix.loadFromData(data):
                self._thumb.setPixmap(
                    pix.scaled(
                        120,
                        68,
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            reply.deleteLater()

        mgr.finished.connect(done)
        mgr.get(QNetworkRequest(QUrl(url)))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("YouTube Downloader")
        self.resize(1180, 760)
        self.setMinimumSize(980, 640)

        self._config = self._load_config()
        self._download_dir = Path(
            self._config.get("download_dir") or default_download_dir()
        )
        self._tasks: dict[str, DownloadTask] = {}
        self._queue_widgets: dict[str, QueueItemWidget] = {}
        self._worker: DownloadWorker | None = None
        self._history: list[str] = []

        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._sidebar = self._build_sidebar()
        root_layout.addWidget(self._sidebar)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self._stack = QStackedWidget()
        self._pages = {
            "home": self._build_home_page(),
            "downloads": self._build_downloads_page(),
            "queue": self._build_queue_page(),
            "history": self._build_history_page(),
            "settings": self._build_settings_page(),
            "about": self._build_about_page(),
        }
        for page in self._pages.values():
            self._stack.addWidget(page)
        body_layout.addWidget(self._stack, stretch=1)
        body_layout.addWidget(self._build_footer())
        root_layout.addWidget(body, stretch=1)

        self._nav_buttons["home"].setChecked(True)
        QTimer.singleShot(400, self._maybe_prompt_install)

    def _load_config(self) -> dict:
        if CONFIG_PATH.is_file():
            try:
                return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_config(self) -> None:
        data = {
            "download_dir": str(self._download_dir),
            "quality": self._selected_quality(),
            "format": self._format_combo.currentData(),
            "subtitles": self._subtitles_cb.isChecked(),
            "cookie_file": self._cookie_edit.text().strip(),
        }
        CONFIG_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _build_sidebar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("sidebar")
        frame.setFixedWidth(240)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 20, 16, 20)
        layout.setSpacing(8)

        brand = QLabel("▶  YouTube Downloader")
        brand_font = QFont("Segoe UI", 13)
        brand_font.setBold(True)
        brand.setFont(brand_font)
        brand.setStyleSheet(f"color:{COLORS['accent']}; padding: 8px 4px 16px 4px;")
        layout.addWidget(brand)

        self._nav_buttons: dict[str, NavButton] = {}
        nav_items = [
            ("home", "🏠", "Home", ""),
            ("downloads", "⬇", "Downloads", ""),
            ("queue", "📋", "Queue", ""),
            ("history", "🕘", "History", ""),
            ("settings", "⚙", "Settings", ""),
            ("about", "ℹ", "About", ""),
        ]
        for key, icon, text, badge in nav_items:
            btn = NavButton(icon, text, badge)
            btn.clicked.connect(lambda checked, k=key: self._switch_page(k))
            self._nav_buttons[key] = btn
            layout.addWidget(btn)
        layout.addStretch()

        promo = QFrame()
        promo.setStyleSheet(
            f"background:{COLORS['accent_soft']}; border-radius:12px; padding:12px;"
        )
        promo_layout = QVBoxLayout(promo)
        promo_layout.addWidget(QLabel("👑  Go Premium"))
        promo_layout.addWidget(QLabel("Unlock faster downloads\nand batch processing."))
        upgrade = QPushButton("Upgrade Now")
        upgrade.setObjectName("primaryBtn")
        upgrade.setEnabled(False)
        promo_layout.addWidget(upgrade)
        layout.addWidget(promo)
        return frame

    def _switch_page(self, key: str) -> None:
        for k, btn in self._nav_buttons.items():
            btn.setChecked(k == key)
        index = list(self._pages.keys()).index(key)
        self._stack.setCurrentIndex(index)
        if key == "downloads":
            self._refresh_downloads_page()
        elif key == "queue":
            self._refresh_queue_page()

    def _build_home_page(self) -> QWidget:
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        h1 = QLabel("YouTube Downloader")
        h1_font = QFont("Segoe UI", 24)
        h1_font.setBold(True)
        h1.setFont(h1_font)
        title_box.addWidget(h1)
        title_box.addWidget(
            QLabel("Download your favorite videos in high quality.")
        )
        header.addLayout(title_box)
        header.addStretch()
        help_btn = QPushButton("?")
        help_btn.setObjectName("ghostBtn")
        help_btn.setFixedSize(36, 36)
        help_btn.clicked.connect(
            lambda: QMessageBox.information(
                self,
                "帮助",
                "粘贴 YouTube 链接，选择画质和格式，点击 Download 开始下载。",
            )
        )
        header.addWidget(help_btn)
        layout.addLayout(header)

        url_card = QFrame()
        url_card.setObjectName("urlCard")
        url_layout = QVBoxLayout(url_card)
        url_layout.setContentsMargins(16, 16, 16, 16)
        url_layout.addWidget(QLabel("Video URL"))
        row = QHBoxLayout()
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("https://www.youtube.com/watch?v=...")
        row.addWidget(self._url_edit, stretch=1)
        download_btn = QPushButton("⬇  Download")
        download_btn.setObjectName("primaryBtn")
        download_btn.clicked.connect(self._start_download)
        row.addWidget(download_btn)
        url_layout.addLayout(row)
        layout.addWidget(url_card)

        layout.addWidget(QLabel("Quality"))
        quality_row = QHBoxLayout()
        quality_row.setSpacing(10)
        self._quality_group = QButtonGroup(self)
        saved_quality = self._config.get("quality", "1080")
        for key, title, subtitle in QUALITY_OPTIONS:
            btn = QualityButton(key, title, subtitle)
            self._quality_group.addButton(btn)
            if key == saved_quality:
                btn.setChecked(True)
            quality_row.addWidget(btn)
        if not any(b.isChecked() for b in self._quality_group.buttons()):
            self._quality_group.buttons()[2].setChecked(True)
        quality_wrap = QWidget()
        quality_wrap.setLayout(quality_row)
        layout.addWidget(quality_wrap)

        format_row = QHBoxLayout()
        format_row.addWidget(QLabel("Format"))
        self._format_combo = QComboBox()
        for key, label in FORMAT_OPTIONS:
            self._format_combo.addItem(label, key)
        saved_fmt = self._config.get("format", "mp4")
        idx = max(0, self._format_combo.findData(saved_fmt))
        self._format_combo.setCurrentIndex(idx)
        format_row.addWidget(self._format_combo)
        format_row.addStretch()
        layout.addLayout(format_row)

        queue_header = QHBoxLayout()
        self._queue_title = QLabel("Download Queue")
        queue_header.addWidget(self._queue_title)
        self._queue_badge = QLabel("0")
        self._queue_badge.setStyleSheet(
            f"background:{COLORS['accent']}; color:white; border-radius:10px; padding:2px 8px;"
        )
        queue_header.addWidget(self._queue_badge)
        queue_header.addStretch()
        clear_btn = QPushButton("Clear Completed")
        clear_btn.setObjectName("ghostBtn")
        clear_btn.clicked.connect(self._clear_completed)
        queue_header.addWidget(clear_btn)
        layout.addLayout(queue_header)

        self._queue_container = QVBoxLayout()
        self._queue_container.setSpacing(10)
        queue_box = QWidget()
        queue_box.setLayout(self._queue_container)
        layout.addWidget(queue_box)
        layout.addStretch()

        scroll.setWidget(inner)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll)
        return page

    def _build_downloads_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        h = QLabel("Downloads")
        h.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        layout.addWidget(h)
        self._downloads_label = QLabel("已完成下载会显示在这里。")
        self._downloads_label.setWordWrap(True)
        self._downloads_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._downloads_label, stretch=1)
        return page

    def _build_queue_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        h = QLabel("Queue")
        h.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        layout.addWidget(h)
        self._queue_label = QLabel("当前下载队列。")
        self._queue_label.setWordWrap(True)
        self._queue_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._queue_label, stretch=1)
        return page

    def _build_history_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.addWidget(QLabel("History"))
        self._history_view = QLabel("暂无历史记录。")
        self._history_view.setWordWrap(True)
        self._history_view.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._history_view, stretch=1)
        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)
        layout.addWidget(QLabel("Settings"))
        self._env_label = QLabel()
        self._env_label.setWordWrap(True)
        layout.addWidget(self._env_label)

        from PyQt6.QtWidgets import QCheckBox

        self._subtitles_cb = QCheckBox("下载字幕")
        self._subtitles_cb.setChecked(bool(self._config.get("subtitles", False)))
        layout.addWidget(self._subtitles_cb)

        cookie_row = QHBoxLayout()
        cookie_row.addWidget(QLabel("Cookies:"))
        self._cookie_edit = QLineEdit(self._config.get("cookie_file", ""))
        cookie_row.addWidget(self._cookie_edit, stretch=1)
        pick = QPushButton("选择文件")
        pick.setObjectName("ghostBtn")
        pick.clicked.connect(self._pick_cookie)
        cookie_row.addWidget(pick)
        layout.addLayout(cookie_row)

        btn_row = QHBoxLayout()
        install_btn = QPushButton("一键安装依赖")
        install_btn.setObjectName("primaryBtn")
        install_btn.clicked.connect(lambda: self._install_deps(include_node=True))
        node_btn = QPushButton("安装 Node.js")
        node_btn.setObjectName("ghostBtn")
        node_btn.clicked.connect(lambda: self._install_deps(include_node=True, node_only=True))
        refresh_btn = QPushButton("刷新状态")
        refresh_btn.setObjectName("ghostBtn")
        refresh_btn.clicked.connect(self._refresh_env_label)
        btn_row.addWidget(install_btn)
        btn_row.addWidget(node_btn)
        btn_row.addWidget(refresh_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        layout.addStretch()
        self._refresh_env_label()
        return page

    def _build_about_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.addWidget(QLabel("About"))
        layout.addWidget(
            QLabel(
                "YouTube Downloader\n\n"
                "基于 yt-dlp 的简易 YouTube 视频下载工具。\n"
                "支持多种画质、MP4/MP3 格式、依赖自动安装。"
            )
        )
        layout.addStretch()
        return page

    def _build_footer(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("footerBar")
        bar.setFixedHeight(56)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 8, 20, 8)
        self._speed_label = QLabel("⚡ 0 MB/s")
        self._speed_label.setStyleSheet(f"color:{COLORS['accent']}; font-weight:600;")
        self._conn_label = QLabel("🌐 Connected")
        self._conn_label.setStyleSheet(f"color:{COLORS['success']};")
        layout.addWidget(self._speed_label)
        layout.addSpacing(20)
        layout.addWidget(self._conn_label)
        layout.addStretch()
        layout.addWidget(QLabel("📁"))
        self._path_label = QLabel(str(self._download_dir))
        self._path_label.setStyleSheet(f"color:{COLORS['text_secondary']};")
        change_btn = QPushButton("Change")
        change_btn.setObjectName("ghostBtn")
        change_btn.clicked.connect(self._choose_dir)
        layout.addWidget(self._path_label)
        layout.addWidget(change_btn)
        return bar

    def _selected_quality(self) -> str:
        btn = self._quality_group.checkedButton()
        return btn.key if isinstance(btn, QualityButton) else "1080"

    def _selected_format_key(self) -> str:
        fmt = self._format_combo.currentData()
        if fmt == "audio":
            return "audio"
        return self._selected_quality()

    def _refresh_env_label(self) -> None:
        env = inspect_environment(self._download_dir)
        text = (
            f"yt-dlp: {env.yt_dlp_version}\n"
            f"ffmpeg: {env.ffmpeg_source}\n"
            f"JS 运行时: {env.js_runtime_source}"
        )
        self._env_label.setText(text)

    def _choose_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "选择保存文件夹", str(self._download_dir)
        )
        if chosen:
            self._download_dir = Path(chosen)
            self._path_label.setText(chosen)
            self._save_config()

    def _pick_cookie(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 cookies.txt", "", "Text (*.txt);;All (*.*)"
        )
        if path:
            self._cookie_edit.setText(path)

    def _update_queue_badge(self) -> None:
        active = sum(
            1
            for t in self._tasks.values()
            if t.status in (TaskStatus.QUEUED, TaskStatus.DOWNLOADING)
        )
        self._queue_badge.setText(str(active))

    def _add_queue_widget(self, task: DownloadTask) -> None:
        widget = QueueItemWidget(task, self._cancel_task)
        self._queue_widgets[task.task_id] = widget
        self._queue_container.addWidget(widget)
        self._update_queue_badge()

    def _start_download(self) -> None:
        url = self._url_edit.text().strip()
        urls = extract_urls(url)
        if not urls:
            QMessageBox.warning(self, "链接", "请输入有效的 YouTube 链接。")
            return
        if missing_components():
            if QMessageBox.question(
                self, "缺少依赖", "需要先安装 yt-dlp 和 ffmpeg。是否现在安装？"
            ) == QMessageBox.StandardButton.Yes:
                self._install_deps(include_node=True)
            return

        self._save_config()
        cookie = self._cookie_edit.text().strip()
        cookie_path = Path(cookie) if cookie else None
        if cookie_path and not cookie_path.is_file():
            QMessageBox.warning(self, "Cookies", "cookies.txt 不存在。")
            return

        fmt_key = self._selected_format_key()
        quality_label = format_label(self._selected_quality())
        format_label_text = self._format_combo.currentText()

        new_tasks = []
        for u in urls:
            task = new_task(
                u,
                fmt_key,
                self._download_dir,
                quality_label=quality_label,
                format_label=format_label_text,
                cookie_file=cookie_path,
                subtitles=self._subtitles_cb.isChecked(),
            )
            self._tasks[task.task_id] = task
            self._add_queue_widget(task)
            new_tasks.append(task)
            self._history.append(f"{u} → {quality_label} / {format_label_text}")
        self._history_view.setText("\n".join(reversed(self._history[-30:])))
        self._url_edit.clear()

        if self._worker and self._worker.isRunning():
            return
        self._run_worker()

    def _run_worker(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        pending = [t for t in self._tasks.values() if t.status == TaskStatus.QUEUED]
        if not pending:
            return
        self._worker = DownloadWorker(pending, self)
        self._worker.task_updated.connect(self._on_task_updated)
        self._worker.task_finished.connect(self._on_task_finished)
        self._worker.global_speed.connect(self._on_speed)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _on_worker_finished(self) -> None:
        if any(t.status == TaskStatus.QUEUED for t in self._tasks.values()):
            self._run_worker()

    def _on_task_updated(self, task_id: str) -> None:
        widget = self._queue_widgets.get(task_id)
        if widget:
            widget.refresh()
        self._update_queue_badge()

    def _on_task_finished(self, task_id: str, success: bool, message: str) -> None:
        self._on_task_updated(task_id)
        self._update_queue_badge()

    def _on_speed(self, speed: str) -> None:
        self._speed_label.setText(f"⚡ {speed or '0 MB/s'}")

    def _cancel_task(self, task_id: str) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
        task = self._tasks.get(task_id)
        if task and task.status == TaskStatus.QUEUED:
            task.status = TaskStatus.CANCELLED
            self._on_task_updated(task_id)

    def _clear_completed(self) -> None:
        remove_ids = [
            tid
            for tid, t in self._tasks.items()
            if t.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.FAILED)
        ]
        for tid in remove_ids:
            widget = self._queue_widgets.pop(tid, None)
            if widget:
                widget.setParent(None)
                widget.deleteLater()
            self._tasks.pop(tid, None)
        self._update_queue_badge()

    def _refresh_downloads_page(self) -> None:
        if not self._downloads_label:
            return
        done = [t for t in self._tasks.values() if t.status == TaskStatus.COMPLETED]
        if not done:
            self._downloads_label.setText("暂无已完成下载。")
            return
        lines = [f"✓ {t.title}  ({t.quality_label})" for t in done[-20:]]
        self._downloads_label.setText("\n".join(reversed(lines)))

    def _refresh_queue_page(self) -> None:
        if not self._queue_label:
            return
        active = [
            t
            for t in self._tasks.values()
            if t.status in (TaskStatus.QUEUED, TaskStatus.DOWNLOADING)
        ]
        if not active:
            self._queue_label.setText("队列为空。")
            return
        lines = [f"• {t.title} — {t.status.value} {t.progress:.0f}%" for t in active]
        self._queue_label.setText("\n".join(lines))

    def _install_deps(self, include_node: bool = True, node_only: bool = False) -> None:
        def log(msg: str) -> None:
            self._history.append(f"[安装] {msg}")
            self._history_view.setText("\n".join(reversed(self._history[-30:])))

        try:
            ensure_dependencies(
                install_ytdlp=not node_only,
                install_ffmpeg_tool=not node_only,
                install_node=include_node or node_only,
                log=log,
            )
            self._refresh_env_label()
            QMessageBox.information(self, "完成", "安装完成。")
        except Exception as exc:
            QMessageBox.critical(self, "安装失败", str(exc))

    def _maybe_prompt_install(self) -> None:
        missing = missing_components()
        optional = optional_components()
        if missing:
            if QMessageBox.question(
                self,
                "缺少依赖",
                f"未安装: {'、'.join(missing)}\n是否自动安装？",
            ) == QMessageBox.StandardButton.Yes:
                self._install_deps(include_node=bool(optional))
        elif optional:
            if QMessageBox.question(
                self,
                "建议安装 Node.js",
                "未检测到 Node.js。是否从 nodejs.org 自动下载？",
            ) == QMessageBox.StandardButton.Yes:
                self._install_deps(include_node=True, node_only=True)

    def closeEvent(self, event) -> None:
        self._save_config()
        if self._worker and self._worker.isRunning():
            if (
                QMessageBox.question(self, "退出", "下载进行中，确定退出？")
                == QMessageBox.StandardButton.Yes
            ):
                self._worker.cancel()
                event.accept()
            else:
                event.ignore()
            return
        event.accept()


def run_app() -> None:
    app = QApplication([])
    app.setStyleSheet(load_stylesheet())
    window = MainWindow()
    window.show()
    app.exec()
