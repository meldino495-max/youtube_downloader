from __future__ import annotations

import json
import threading
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from app_icon import apply_window_icon
from deps_installer import (
    SOURCE_URLS,
    ensure_dependencies,
    missing_components,
    optional_components,
)
from engine import (
    DownloadCancelled,
    Downloader,
    extract_urls,
    format_label,
    inspect_environment,
)
from ui_styles import (
    C,
    accent_button,
    apply_theme,
    card_frame,
    compact_button,
    danger_ghost_button,
    folder_picker_button,
    ghost_button,
    primary_button,
    rounded_entry,
    styled_text,
)
from paths_config import InstallPaths, find_ffmpeg_exe, find_node_exe, save_install_paths, ytdlp_is_ready

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"

FORMAT_OPTIONS = [
    ("best", "最佳质量"),
    ("2160", "4K (2160p)"),
    ("1440", "2K (1440p)"),
    ("1080", "1080p"),
    ("720", "720p"),
    ("480", "480p"),
    ("360", "360p"),
    ("240", "240p"),
    ("audio", "仅音频 MP3"),
]


URL_TEXT_LINES = 3


def _default_url_pane_height(master: tk.Misc) -> int:
    """Pane height that fits the link card with three text lines."""
    font = tkfont.Font(master=master, font=("Microsoft YaHei UI", 10))
    text_h = font.metrics("linespace") * URL_TEXT_LINES + 28
    return int(36 + text_h + 108)


def _resolve_format_key(saved: str) -> str:
    keys = [key for key, _ in FORMAT_OPTIONS]
    if saved in keys:
        return saved
    for key, label in FORMAT_OPTIONS:
        if saved == label:
            return key
    return "best"


class YouTubeDownloaderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("YouTube 下载器")
        self.minsize(820, 700)
        self.geometry("900x860")

        apply_theme(self)
        apply_window_icon(self)
        self._config = self._load_config()
        self._install_paths = InstallPaths.from_config(self._config)
        self._env = inspect_environment(
            Path(self._config.get("download_dir", "")) or None,
            self._install_paths,
        )
        self._worker: threading.Thread | None = None
        self._cancel_flag = False
        self._show_log = tk.BooleanVar(
            value=bool(self._config.get("show_log", True))
        )
        self._show_install_paths = tk.BooleanVar(
            value=bool(self._config.get("show_install_paths", False))
        )

        self._build_ui()
        self._refresh_environment()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(300, self._maybe_prompt_install)

    def _load_config(self) -> dict:
        if not CONFIG_PATH.is_file():
            return {}
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_config(self) -> None:
        paths = self._current_install_paths()
        saved_dir = self.dir_var.get().strip()
        if saved_dir.startswith("（"):
            saved_dir = ""
        data = {
            "download_dir": saved_dir or str(self._env.download_dir),
            "format": self._format_key(),
            "subtitles": self.subtitles_var.get(),
            "cookie_file": self.cookie_var.get().strip(),
            "install_paths": paths.to_config_dict(),
            "show_log": self._show_log.get(),
            "show_install_paths": self._show_install_paths.get(),
        }
        pane_height = self._url_pane_height()
        if pane_height is not None:
            data["url_pane_height"] = pane_height
        CONFIG_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._install_paths = paths

    def _current_install_paths(self) -> InstallPaths:
        return InstallPaths(
            ytdlp_dir=Path(self.ytdlp_dir_var.get().strip()),
            ffmpeg_dir=Path(self.ffmpeg_dir_var.get().strip()),
            nodejs_dir=Path(self.nodejs_dir_var.get().strip()),
        )

    def _browse_install_dir(self, var: tk.StringVar, title: str) -> None:
        initial = var.get().strip() or str(APP_DIR)
        chosen = self._pick_folder(title, initial)
        if chosen:
            var.set(chosen)
            self._install_paths = self._current_install_paths()
            save_install_paths(self._install_paths)
            self._refresh_environment()

    def _toggle_install_paths(self) -> None:
        self._show_install_paths.set(not self._show_install_paths.get())
        self._apply_install_paths_visibility()
        self._save_config()

    def _toggle_log(self) -> None:
        self._show_log.set(not self._show_log.get())
        self._apply_log_visibility()
        self._save_config()

    def _apply_install_paths_visibility(self) -> None:
        if self._show_install_paths.get():
            self.paths_content.pack(
                fill="x",
                padx=12,
                pady=(0, 2),
                before=self.env_btns,
            )
            self._paths_toggle_btn.configure(text="隐藏安装位置")
        else:
            self.paths_content.pack_forget()
            self._paths_toggle_btn.configure(text="显示安装位置")

    def _apply_log_visibility(self) -> None:
        if self._show_log.get():
            self.log_frame.pack(fill="both", expand=True, padx=12, pady=(0, 4))
            self._log_toggle_btn.configure(text="隐藏日志")
        else:
            self.log_frame.pack_forget()
            self._log_toggle_btn.configure(text="显示日志")

    def _build_ui(self) -> None:
        pad_x = {"padx": 12}
        section = {"padx": 12, "pady": 4}

        outer = ttk.Frame(self, padding=(12, 8))
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="YouTube 下载器", style="Header.TLabel").pack(
            anchor="w", **pad_x
        )
        ttk.Label(
            outer,
            text="粘贴 YouTube 链接，选择格式，一键下载",
            style="Muted.TLabel",
        ).pack(anchor="w", padx=12, pady=(0, 4))

        self._url_pane = tk.PanedWindow(
            outer,
            orient=tk.VERTICAL,
            sashrelief=tk.RAISED,
            sashwidth=7,
            sashpad=1,
            bg=C["border"],
            bd=0,
            opaqueresize=True,
        )
        self._url_pane.pack(fill=tk.BOTH, expand=True, pady=(0, 4))

        url_section = tk.Frame(self._url_pane, bg=C["bg"])
        bottom_section = tk.Frame(self._url_pane, bg=C["bg"])
        default_url_h = _default_url_pane_height(self)
        self._url_pane.add(url_section, minsize=default_url_h - 24)
        self._url_pane.add(bottom_section, minsize=300)

        url_frame = card_frame(
            url_section,
            text="视频链接（每行一个，支持单个视频 / 播放列表 / 频道）",
            padding=6,
            expand_vertical=True,
        )
        url_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

        url_btns = ttk.Frame(url_frame.content, style="Card.TFrame")
        url_btns.pack(fill="x", padx=4, pady=(0, 4))
        ghost_button(url_btns, "从剪贴板粘贴", self._paste_clipboard).pack(side="left")
        ghost_button(
            url_btns,
            "清空",
            lambda: self.url_text.delete("1.0", "end"),
        ).pack(side="left", padx=8)

        url_body = tk.Frame(url_frame.content, bg=C["surface"])
        url_body.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 2))
        self.url_text = styled_text(url_body, height=URL_TEXT_LINES, expand=True)

        ttk.Label(
            url_section,
            text="↕ 拖动下方分隔条可调整链接区域高度",
            style="Muted.TLabel",
        ).pack(anchor="w", padx=14, pady=(0, 2))

        options = card_frame(bottom_section, text="下载选项", padding=8)
        options.pack(fill="x", **section)

        row1 = ttk.Frame(options.content, style="Card.TFrame")
        row1.pack(fill="x", pady=2)
        ttk.Label(row1, text="画质:", style="Card.TLabel").pack(side="left")
        saved_key = _resolve_format_key(self._config.get("format", "best"))
        labels = [label for _, label in FORMAT_OPTIONS]
        keys = [key for key, _ in FORMAT_OPTIONS]
        self.format_var = tk.StringVar(value=labels[keys.index(saved_key)])
        self.format_combo = ttk.Combobox(
            row1,
            textvariable=self.format_var,
            state="readonly",
            width=18,
            values=labels,
            style="Flat.TCombobox",
        )
        self.format_combo.pack(side="left", padx=8)
        self.format_combo.current(keys.index(saved_key))

        self.subtitles_var = tk.BooleanVar(value=bool(self._config.get("subtitles", False)))
        ttk.Checkbutton(
            row1,
            text="下载字幕",
            variable=self.subtitles_var,
            style="Card.TCheckbutton",
        ).pack(side="left", padx=10)

        row2 = ttk.Frame(options.content, style="Card.TFrame")
        row2.pack(fill="x", pady=2)
        ttk.Label(row2, text="保存到:", style="Card.TLabel").pack(side="left")
        saved_dir = self._config.get("download_dir", "").strip()
        self.dir_var = tk.StringVar(value=saved_dir or str(self._env.download_dir))
        folder_picker_button(
            row2, "选择文件夹", self._choose_dir
        ).pack(side="left", padx=(4, 6))
        ghost_button(row2, "打开文件夹", self._open_download_dir).pack(side="left")

        row2_path = ttk.Frame(options.content, style="Card.TFrame")
        row2_path.pack(fill="x", pady=(0, 2))
        self.dir_label = tk.Label(
            row2_path,
            textvariable=self.dir_var,
            anchor="w",
            justify="left",
            bg=C["surface"],
            fg=C["text_secondary"],
            font=("Microsoft YaHei UI", 9),
            wraplength=820,
        )
        self.dir_label.pack(fill="x", padx=4)
        if not self.dir_var.get().strip():
            self.dir_var.set("（请点击「选择文件夹」）")

        row3 = ttk.Frame(options.content, style="Card.TFrame")
        row3.pack(fill="x", pady=2)
        ttk.Label(row3, text="Cookies:", style="Card.TLabel").pack(side="left")
        self.cookie_var = tk.StringVar(value=self._config.get("cookie_file", ""))
        cookie_field = rounded_entry(row3, self.cookie_var)
        cookie_field.pack(side="left", fill="x", expand=True, padx=8)
        ghost_button(row3, "选择", self._choose_cookie).pack(side="left")

        action = ttk.Frame(bottom_section)
        action.pack(fill="x", padx=12, pady=(6, 2))

        self.download_btn = primary_button(action, "开始下载", self._start_download)
        self.download_btn.pack(side="left")

        self.cancel_btn = danger_ghost_button(action, "取消", self._cancel_download)
        self.cancel_btn.configure(state="disabled")
        self.cancel_btn.pack(side="left", padx=10)

        self.progress = ttk.Progressbar(
            action,
            mode="determinate",
            maximum=100,
            style="Modern.Horizontal.TProgressbar",
        )
        self.progress.pack(side="left", fill="x", expand=True, padx=10)

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(action, textvariable=self.status_var, width=10).pack(side="right")

        env_row = ttk.Frame(bottom_section)
        env_row.pack(fill="x", padx=12, pady=(0, 2))

        self._env_summary = tk.Label(
            env_row,
            text="环境检测中…",
            anchor="w",
            bg=C["bg"],
            fg=C["text_secondary"],
            font=("Microsoft YaHei UI", 9),
        )
        self._env_summary.pack(fill="x")

        paths_header = ttk.Frame(bottom_section)
        paths_header.pack(fill="x", padx=12, pady=(2, 0))
        self._paths_toggle_btn = ghost_button(
            paths_header,
            "显示安装位置",
            self._toggle_install_paths,
        )
        self._paths_toggle_btn.pack(anchor="w")

        self.paths_content = ttk.Frame(bottom_section)
        ttk.Label(
            self.paths_content,
            text="安装位置（安装前可自定义）:",
            style="Muted.TLabel",
        ).pack(anchor="w")

        self.ytdlp_dir_var = tk.StringVar(value=str(self._install_paths.ytdlp_dir))
        self.ffmpeg_dir_var = tk.StringVar(value=str(self._install_paths.ffmpeg_dir))
        self.nodejs_dir_var = tk.StringVar(value=str(self._install_paths.nodejs_dir))

        for label, var, title in (
            ("yt-dlp", self.ytdlp_dir_var, "选择 yt-dlp 安装文件夹"),
            ("ffmpeg", self.ffmpeg_dir_var, "选择 ffmpeg 安装文件夹"),
            ("Node.js", self.nodejs_dir_var, "选择 Node.js 安装文件夹"),
        ):
            row = ttk.Frame(self.paths_content)
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=f"{label}:", width=8).pack(side="left")
            field = rounded_entry(row, var)
            field.pack(side="left", fill="x", expand=True, padx=(0, 6))
            ghost_button(
                row,
                "浏览",
                lambda v=var, t=title: self._browse_install_dir(v, t),
            ).pack(side="left")

        env_btns = ttk.Frame(bottom_section)
        env_btns.pack(fill="x", padx=12, pady=(2, 0))
        self.env_btns = env_btns

        self.ytdlp_btn = accent_button(
            env_btns, "↓ yt-dlp", lambda: self._install_component("yt-dlp")
        )
        self.ytdlp_btn.pack(side="left", padx=(0, 4))
        self.ffmpeg_btn = accent_button(
            env_btns, "↓ ffmpeg", lambda: self._install_component("ffmpeg")
        )
        self.ffmpeg_btn.pack(side="left", padx=(0, 4))
        self.install_node_btn = accent_button(
            env_btns, "↓ Node.js", lambda: self._install_component("node.js")
        )
        self.install_node_btn.pack(side="left", padx=(0, 4))
        self.install_all_btn = accent_button(
            env_btns, "全部安装", self._install_all
        )
        self.install_all_btn.pack(side="left", padx=(0, 4))
        compact_button(env_btns, "↻", self._refresh_environment).pack(side="left")

        tk.Label(
            bottom_section,
            text=(
                f"下载源: {SOURCE_URLS['yt-dlp']}  ·  "
                f"{SOURCE_URLS['ffmpeg']}  ·  {SOURCE_URLS['node.js']}"
            ),
            anchor="w",
            bg=C["bg"],
            fg=C["text_secondary"],
            font=("Microsoft YaHei UI", 8),
            wraplength=860,
            justify="left",
        ).pack(fill="x", padx=12, pady=(2, 4))

        log_header = ttk.Frame(bottom_section)
        log_header.pack(fill="x", padx=12, pady=(0, 2))
        self._log_toggle_btn = ghost_button(
            log_header,
            "隐藏日志",
            self._toggle_log,
        )
        self._log_toggle_btn.pack(anchor="w")

        self.log_frame = card_frame(
            bottom_section, text="日志", padding=8, expand_vertical=True
        )
        self.log_text = styled_text(
            self.log_frame.content,
            height=18,
            font=("Microsoft YaHei UI", 10),
            state="disabled",
            expand=True,
        )

        self._apply_install_paths_visibility()
        self._apply_log_visibility()
        self.after_idle(self._restore_url_pane_height)

    def _restore_url_pane_height(self) -> None:
        saved = self._config.get("url_pane_height")
        default_h = _default_url_pane_height(self)
        if saved:
            try:
                height = int(saved)
            except (TypeError, ValueError):
                height = default_h
        else:
            height = default_h
        if height < default_h - 20:
            height = default_h
        try:
            self.update_idletasks()
            self._url_pane.sash_place(0, 0, height)
        except (tk.TclError, ValueError, TypeError):
            pass

    def _url_pane_height(self) -> Optional[int]:
        try:
            return int(self._url_pane.sash_coord(0)[1])
        except (tk.TclError, ValueError, AttributeError):
            return None

    def _compact_env_summary(self) -> str:
        y = "✓" if self._env.yt_dlp_ready else "✗"
        f = "✓" if self._env.ffmpeg_available else "✗"
        n = "✓" if self._env.js_runtime_ready else "✗"
        y_ver = self._env.yt_dlp_version if self._env.yt_dlp_ready else "未安装"
        f_hint = self._env.ffmpeg_source if self._env.ffmpeg_available else "未安装"
        n_hint = "已安装" if self._env.js_runtime_ready else "未安装"
        return (
            f"环境:  {y} yt-dlp ({y_ver})   "
            f"{f} ffmpeg ({f_hint})   "
            f"{n} Node.js ({n_hint})"
        )

    def _format_key(self) -> str:
        label = self.format_var.get()
        for key, item_label in FORMAT_OPTIONS:
            if item_label == label:
                return key
        return "best"

    def _download_dir_from_ui(self) -> Optional[Path]:
        raw = self.dir_var.get().strip()
        if not raw or raw.startswith("（"):
            return None
        try:
            return Path(raw)
        except Exception:
            return None

    def _pick_folder(self, title: str, current: str = "") -> Optional[str]:
        self.update_idletasks()
        self.lift()
        self.focus_force()
        self.attributes("-topmost", True)
        self.update()
        try:
            chosen = filedialog.askdirectory(
                initialdir=self._dialog_initial_dir(
                    current or self.dir_var.get().strip()
                ),
                title=title,
                parent=self,
            )
            return chosen or None
        finally:
            self.attributes("-topmost", False)
            self.lift()
            self.focus_force()

    def _set_download_dir(self, folder: str) -> None:
        self.dir_var.set(folder)
        self._save_config()

    def _refresh_environment(self) -> None:
        download_dir = self._download_dir_from_ui()
        self._install_paths = self._current_install_paths()
        self._env = inspect_environment(download_dir, self._install_paths)
        if not self.dir_var.get().strip() or self.dir_var.get().strip().startswith("（"):
            self.dir_var.set(str(self._env.download_dir))

        self._env_summary.configure(text=self._compact_env_summary())
        if self._env.missing or self._env.optional:
            self._env_summary.configure(fg=C["accent"])
        else:
            self._env_summary.configure(fg=C["success"])

        self.ytdlp_btn.configure(
            state="normal" if not self._env.yt_dlp_ready else "disabled"
        )
        self.ffmpeg_btn.configure(
            state="normal" if not self._env.ffmpeg_available else "disabled"
        )
        self.install_node_btn.configure(
            state="normal" if not self._env.js_runtime_ready else "disabled"
        )
        need_any = bool(self._env.missing or self._env.optional)
        self.install_all_btn.configure(state="normal" if need_any else "disabled")

    def _append_log(self, message: str) -> None:
        def write() -> None:
            self.log_text.configure(state="normal")
            self.log_text.insert("end", message.rstrip() + "\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")

        self.after(0, write)

    def _set_status(self, percent: float, message: str) -> None:
        def update() -> None:
            self.progress["value"] = max(0.0, min(100.0, percent))
            self.status_var.set(message)

        self.after(0, update)

    def _paste_clipboard(self) -> None:
        try:
            text = self.clipboard_get()
        except tk.TclError:
            messagebox.showwarning("剪贴板", "剪贴板为空或无法读取。")
            return
        self.url_text.insert("end", text.strip() + "\n")

    def _dialog_initial_dir(self, current: str) -> str:
        if current.startswith("（"):
            current = ""
        try:
            path = Path(current) if current else self._env.download_dir
        except Exception:
            path = self._env.download_dir
        if path.is_dir():
            return str(path)
        if path.parent.is_dir():
            return str(path.parent)
        fallback = Path.home() / "Downloads"
        return str(fallback if fallback.is_dir() else Path.home())

    def _choose_dir(self) -> None:
        chosen = self._pick_folder("选择下载保存文件夹")
        if not chosen:
            return
        try:
            Path(chosen).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showwarning(
                "保存路径",
                f"无法使用该文件夹:\n{exc}",
                parent=self,
            )
            return
        self._set_download_dir(chosen)
        messagebox.showinfo(
            "保存路径",
            f"已选择文件夹:\n{chosen}",
            parent=self,
        )

    def _open_download_dir(self) -> None:
        path = self._download_dir_from_ui() or self._env.download_dir
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showwarning(
                "保存路径",
                f"无法打开文件夹:\n{path}\n\n{exc}",
                parent=self,
            )
            return
        import os

        os.startfile(path)

    def _choose_cookie(self) -> None:
        chosen = filedialog.askopenfilename(
            title="选择 cookies.txt",
            filetypes=[("Netscape cookies", "*.txt"), ("All files", "*.*")],
            parent=self,
        )
        if chosen:
            self.cookie_var.set(chosen)

    def _set_busy(self, busy: bool) -> None:
        self.download_btn.configure(state="disabled" if busy else "normal")
        self.cancel_btn.configure(state="normal" if busy else "disabled")
        self.format_combo.configure(state="disabled" if busy else "readonly")

    def _set_install_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for btn in (
            self.ytdlp_btn,
            self.ffmpeg_btn,
            self.install_node_btn,
            self.install_all_btn,
        ):
            btn.configure(state=state)
        if not busy:
            self._refresh_environment()

    def _maybe_prompt_install(self) -> None:
        paths = self._current_install_paths()
        missing = missing_components(paths)
        optional = optional_components(paths)
        if not missing and not optional:
            return
        if missing:
            items = "、".join(missing)
            if messagebox.askyesno(
                "缺少依赖",
                f"检测到未安装: {items}\n\n是否现在自动安装？\n"
                "（yt-dlp 来自 GitHub/PyPI，ffmpeg 来自 ffbinaries.com）",
            ):
                self._install_all()
            return
        if optional and messagebox.askyesno(
            "建议安装 Node.js",
            f"未检测到 Node.js。\n\n是否从 {SOURCE_URLS['node.js']} 下载安装？",
        ):
            self._install_component("node.js")

    def _run_install_worker(
        self,
        *,
        install_ytdlp: bool,
        install_ffmpeg_tool: bool,
        install_node: bool,
        title: str,
    ) -> None:
        if self._worker and self._worker.is_alive():
            messagebox.showinfo("请稍候", "当前有任务正在进行，请稍后再安装。")
            return

        self._set_install_busy(True)
        self._append_log(f"—— 开始{title} ——")
        self.status_var.set(f"正在{title}…")
        self.progress["value"] = 0

        def worker() -> None:
            try:
                paths = self._current_install_paths()
                save_install_paths(paths)
                ensure_dependencies(
                    install_ytdlp=install_ytdlp,
                    install_ffmpeg_tool=install_ffmpeg_tool,
                    install_node=install_node,
                    log=self._append_log,
                    percent=self._set_status,
                    paths=paths,
                )
                self.after(0, self._refresh_environment)
                self.after(
                    0,
                    lambda: messagebox.showinfo("安装完成", f"{title}完成。"),
                )
            except Exception as exc:
                self._append_log(f"安装失败: {exc}")
                self.after(
                    0,
                    lambda: messagebox.showerror(
                        "安装失败",
                        f"{exc}\n\n也可手动运行 setup.bat。",
                    ),
                )
            finally:
                self.after(0, lambda: self._set_install_busy(False))
                self.after(0, lambda: self.status_var.set("就绪"))

        self._worker = threading.Thread(target=worker, daemon=True)
        self._worker.start()

    def _install_component(self, name: str) -> None:
        paths = self._current_install_paths()
        save_install_paths(paths)
        self._install_paths = paths

        if name == "yt-dlp":
            if ytdlp_is_ready(paths):
                self._refresh_environment()
                messagebox.showinfo("yt-dlp", f"yt-dlp 已安装: {self._env.yt_dlp_version}")
                return
            self._run_install_worker(
                install_ytdlp=True,
                install_ffmpeg_tool=False,
                install_node=False,
                title=f"安装 yt-dlp（{SOURCE_URLS['yt-dlp']}）",
            )
        elif name == "ffmpeg":
            if find_ffmpeg_exe(paths):
                self._refresh_environment()
                messagebox.showinfo("ffmpeg", f"ffmpeg 已安装: {self._env.ffmpeg_source}")
                return
            self._run_install_worker(
                install_ytdlp=False,
                install_ffmpeg_tool=True,
                install_node=False,
                title=f"安装 ffmpeg（{SOURCE_URLS['ffmpeg']}）",
            )
        elif name == "node.js":
            if find_node_exe(paths):
                self._refresh_environment()
                messagebox.showinfo("Node.js", "Node.js 已安装。")
                return
            self._run_install_worker(
                install_ytdlp=False,
                install_ffmpeg_tool=False,
                install_node=True,
                title=f"安装 Node.js（{SOURCE_URLS['node.js']}）",
            )

    def _install_all(self) -> None:
        paths = self._current_install_paths()
        missing = missing_components(paths)
        optional = optional_components(paths)
        if not missing and not optional:
            messagebox.showinfo("依赖", "yt-dlp、ffmpeg、Node.js 均已就绪。")
            return
        self._run_install_worker(
            install_ytdlp="yt-dlp" in missing,
            install_ffmpeg_tool="ffmpeg" in missing,
            install_node=bool(optional),
            title="安装全部组件",
        )

    def _install_dependencies(self, include_node: bool = True) -> None:
        self._install_all()

    def _start_download(self) -> None:
        if self._worker and self._worker.is_alive():
            return

        urls = extract_urls(self.url_text.get("1.0", "end"))
        if not urls:
            messagebox.showwarning("链接", "请输入至少一个有效的 YouTube 链接。")
            return

        if missing_components(self._current_install_paths()):
            if messagebox.askyesno(
                "缺少依赖",
                "下载前需要 yt-dlp 和 ffmpeg。\n是否现在自动安装？",
            ):
                self._install_all()
            return

        if not self._env.js_runtime_ready and messagebox.askyesno(
            "建议安装 Node.js",
            f"未检测到 Node.js。\n是否从 {SOURCE_URLS['node.js']} 安装？\n（点「否」可继续尝试下载）",
        ):
            self._install_component("node.js")
            return

        output_dir = Path(self.dir_var.get().strip())
        if not self.dir_var.get().strip() or self.dir_var.get().strip().startswith("（"):
            messagebox.showwarning(
                "保存路径",
                "请先点击「选择文件夹」选择下载保存位置。",
                parent=self,
            )
            return
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(
                "保存路径",
                f"无法创建或访问该文件夹:\n{output_dir}\n\n{exc}",
                parent=self,
            )
            return

        cookie_path = (
            Path(self.cookie_var.get().strip()) if self.cookie_var.get().strip() else None
        )
        if cookie_path and not cookie_path.is_file():
            messagebox.showwarning("Cookies", "指定的 cookies.txt 不存在。")
            return

        self._save_config()
        self._cancel_flag = False
        self._set_busy(True)
        self.progress["value"] = 0
        self.status_var.set("准备下载…")
        self._append_log("—— 开始下载 ——")
        self._append_log(f"格式: {format_label(self._format_key())}")
        self._append_log(f"保存目录: {output_dir}")

        def worker() -> None:
            downloader = Downloader(
                log=self._append_log,
                status=self._set_status,
                cancel_check=lambda: self._cancel_flag,
            )
            try:
                success, failed, skipped = downloader.download_urls(
                    urls,
                    output_dir,
                    self._format_key(),
                    subtitles=self.subtitles_var.get(),
                    cookie_file=cookie_path,
                )
                parts = [f"成功 {success} 个链接"]
                if failed:
                    parts.append(f"失败 {failed} 个")
                if skipped:
                    parts.append(f"跳过 {skipped} 个重复视频")
                summary = "完成：" + "，".join(parts)
                self._append_log(summary)
                self.after(
                    0,
                    lambda: messagebox.showinfo(
                        "下载完成",
                        summary + f"\n文件保存在:\n{output_dir}",
                    ),
                )
            except DownloadCancelled:
                self._append_log("已取消下载。")
                self.after(0, lambda: self.status_var.set("已取消"))
            except Exception as exc:
                self._append_log(f"错误: {exc}")
                self.after(0, lambda: messagebox.showerror("下载失败", str(exc)))
            finally:
                self.after(0, lambda: self._set_busy(False))

        self._worker = threading.Thread(target=worker, daemon=True)
        self._worker.start()

    def _cancel_download(self) -> None:
        self._cancel_flag = True
        self.status_var.set("正在取消…")
        self._append_log("正在取消…")

    def _on_close(self) -> None:
        self._save_config()
        if self._worker and self._worker.is_alive():
            if messagebox.askyesno("退出", "下载仍在进行，确定要退出吗？"):
                self._cancel_flag = True
                self.destroy()
            return
        self.destroy()


def main() -> None:
    app = YouTubeDownloaderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
