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
from i18n import (
    FORMAT_KEYS,
    LANG_LABELS,
    LANGUAGES,
    format_option_labels,
    get_language,
    init_language,
    language_code_from_label,
    resolve_format_key,
    set_language,
    t,
    ui_font_family,
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
from paths_config import (
    APP_DIR,
    CONFIG_PATH,
    InstallPaths,
    find_ffmpeg_exe,
    find_node_exe,
    save_install_paths,
    ytdlp_is_ready,
)

URL_TEXT_LINES = 3


def _default_url_pane_height(master: tk.Misc) -> int:
    """Pane height that fits the link card with three text lines."""
    font = tkfont.Font(master=master, font=(ui_font_family(), 10))
    text_h = font.metrics("linespace") * URL_TEXT_LINES + 28
    return int(36 + text_h + 108)


class YouTubeDownloaderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.minsize(820, 700)
        self.geometry("900x860")

        apply_theme(self)
        apply_window_icon(self)
        self._config = self._load_config()
        saved_lang = self._config.get("language", "")
        init_language(saved_lang if saved_lang in LANGUAGES else None)
        self.title(t("app.title"))
        self._dir_is_placeholder = False
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
        if self._dir_is_placeholder:
            saved_dir = ""
        data = {
            "download_dir": saved_dir or str(self._env.download_dir),
            "format": self._format_key(),
            "subtitles": self.subtitles_var.get(),
            "cookie_file": self.cookie_var.get().strip(),
            "install_paths": paths.to_config_dict(),
            "show_log": self._show_log.get(),
            "show_install_paths": self._show_install_paths.get(),
            "language": get_language(),
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

    def _on_language_changed(self, _event: Optional[object] = None) -> None:
        code = language_code_from_label(self.lang_var.get())
        if not code or code == get_language():
            return
        set_language(code)
        self._apply_language()
        self._save_config()

    def _apply_language(self) -> None:
        self.title(t("app.title"))
        self._header_title.configure(text=t("app.title"))
        self._header_subtitle.configure(text=t("app.subtitle"))
        self._lang_label.configure(text=t("lang.label"))
        self._url_card.set_title(t("url.card"))
        self._paste_btn.configure(text=t("url.paste"))
        self._clear_btn.configure(text=t("url.clear"))
        self._url_resize_lbl.configure(text=t("url.resize_hint"))
        self._options_card.set_title(t("options.card"))
        self._quality_lbl.configure(text=t("options.quality"))
        self._subtitles_chk.configure(text=t("options.subtitles"))
        self._save_lbl.configure(text=t("options.save"))
        self._pick_folder_btn.configure(text=t("options.pick_folder"))
        self._open_folder_btn.configure(text=t("options.open_folder"))
        self._cookies_lbl.configure(text=t("options.cookies"))
        self._cookies_pick_btn.configure(text=t("options.cookies_pick"))
        self.download_btn.configure(text=t("action.download"))
        self.cancel_btn.configure(text=t("action.cancel"))
        if self.status_var.get() in (
            t("status.ready"),
            "就绪",
            "Ready",
            "Готово",
        ):
            self.status_var.set(t("status.ready"))
        self._paths_title_lbl.configure(text=t("paths.title"))
        for btn, title_key in self._path_browse_btns:
            btn.configure(text=t("paths.browse"))
        self._sources_lbl.configure(
            text=t(
                "sources.footer",
                ytdlp=SOURCE_URLS["yt-dlp"],
                ffmpeg=SOURCE_URLS["ffmpeg"],
                nodejs=SOURCE_URLS["node.js"],
            )
        )
        self.log_frame.set_title(t("log.card"))
        self.install_all_btn.configure(text=t("msg.install.all"))
        self._apply_install_paths_visibility()
        self._apply_log_visibility()
        key = self._format_key()
        labels = format_option_labels()
        self.format_combo.configure(values=labels)
        idx = FORMAT_KEYS.index(key) if key in FORMAT_KEYS else 0
        self.format_var.set(labels[idx])
        self.format_combo.current(idx)
        if self._dir_is_placeholder:
            self.dir_var.set(t("dir.unset"))
        self.dir_label.configure(font=(ui_font_family(), 9))
        self._env_summary.configure(font=(ui_font_family(), 9))
        self._refresh_environment()

    def _apply_install_paths_visibility(self) -> None:
        if self._show_install_paths.get():
            self.paths_content.pack(
                fill="x",
                padx=12,
                pady=(0, 2),
                before=self.env_btns,
            )
            self._paths_toggle_btn.configure(text=t("paths.hide"))
        else:
            self.paths_content.pack_forget()
            self._paths_toggle_btn.configure(text=t("paths.show"))

    def _apply_log_visibility(self) -> None:
        if self._show_log.get():
            self.log_frame.pack(fill="both", expand=True, padx=12, pady=(0, 4))
            self._log_toggle_btn.configure(text=t("log.hide"))
        else:
            self.log_frame.pack_forget()
            self._log_toggle_btn.configure(text=t("log.show"))

    def _build_ui(self) -> None:
        pad_x = {"padx": 12}
        section = {"padx": 12, "pady": 4}

        outer = ttk.Frame(self, padding=(12, 8))
        outer.pack(fill="both", expand=True)

        self._header_title = ttk.Label(
            outer, text=t("app.title"), style="Header.TLabel"
        )
        self._header_title.pack(anchor="w", **pad_x)
        self._header_subtitle = ttk.Label(
            outer,
            text=t("app.subtitle"),
            style="Muted.TLabel",
        )
        self._header_subtitle.pack(anchor="w", padx=12, pady=(0, 4))

        lang_row = ttk.Frame(outer)
        lang_row.pack(fill="x", padx=12, pady=(0, 6))
        self._lang_label = ttk.Label(lang_row, text=t("lang.label"), style="Card.TLabel")
        self._lang_label.pack(side="left")
        lang_names = [LANG_LABELS[code] for code in LANGUAGES]
        self.lang_var = tk.StringVar(value=LANG_LABELS[get_language()])
        self.lang_combo = ttk.Combobox(
            lang_row,
            textvariable=self.lang_var,
            values=lang_names,
            state="readonly",
            width=14,
            style="Flat.TCombobox",
        )
        self.lang_combo.pack(side="left", padx=8)
        self.lang_combo.bind("<<ComboboxSelected>>", self._on_language_changed)

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

        self._url_card = card_frame(
            url_section,
            text=t("url.card"),
            padding=6,
            expand_vertical=True,
        )
        self._url_card.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

        url_btns = ttk.Frame(self._url_card.content, style="Card.TFrame")
        url_btns.pack(fill="x", padx=4, pady=(0, 4))
        self._paste_btn = ghost_button(url_btns, t("url.paste"), self._paste_clipboard)
        self._paste_btn.pack(side="left")
        self._clear_btn = ghost_button(
            url_btns,
            t("url.clear"),
            lambda: self.url_text.delete("1.0", "end"),
        )
        self._clear_btn.pack(side="left", padx=8)

        url_body = tk.Frame(self._url_card.content, bg=C["surface"])
        url_body.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 2))
        self.url_text = styled_text(url_body, height=URL_TEXT_LINES, expand=True)

        self._url_resize_lbl = ttk.Label(
            url_section,
            text=t("url.resize_hint"),
            style="Muted.TLabel",
        )
        self._url_resize_lbl.pack(anchor="w", padx=14, pady=(0, 2))

        self._options_card = card_frame(bottom_section, text=t("options.card"), padding=8)
        self._options_card.pack(fill="x", **section)

        row1 = ttk.Frame(self._options_card.content, style="Card.TFrame")
        row1.pack(fill="x", pady=2)
        self._quality_lbl = ttk.Label(row1, text=t("options.quality"), style="Card.TLabel")
        self._quality_lbl.pack(side="left")
        saved_key = resolve_format_key(self._config.get("format", "best"))
        labels = format_option_labels()
        self.format_var = tk.StringVar(value=labels[FORMAT_KEYS.index(saved_key)])
        self.format_combo = ttk.Combobox(
            row1,
            textvariable=self.format_var,
            state="readonly",
            width=18,
            values=labels,
            style="Flat.TCombobox",
        )
        self.format_combo.pack(side="left", padx=8)
        self.format_combo.current(FORMAT_KEYS.index(saved_key))

        self.subtitles_var = tk.BooleanVar(value=bool(self._config.get("subtitles", False)))
        self._subtitles_chk = ttk.Checkbutton(
            row1,
            text=t("options.subtitles"),
            variable=self.subtitles_var,
            style="Card.TCheckbutton",
        )
        self._subtitles_chk.pack(side="left", padx=10)

        row2 = ttk.Frame(self._options_card.content, style="Card.TFrame")
        row2.pack(fill="x", pady=2)
        self._save_lbl = ttk.Label(row2, text=t("options.save"), style="Card.TLabel")
        self._save_lbl.pack(side="left")
        saved_dir = self._config.get("download_dir", "").strip()
        self.dir_var = tk.StringVar(value=saved_dir or str(self._env.download_dir))
        self._pick_folder_btn = folder_picker_button(
            row2, t("options.pick_folder"), self._choose_dir
        )
        self._pick_folder_btn.pack(side="left", padx=(4, 6))
        self._open_folder_btn = ghost_button(
            row2, t("options.open_folder"), self._open_download_dir
        )
        self._open_folder_btn.pack(side="left")

        row2_path = ttk.Frame(self._options_card.content, style="Card.TFrame")
        row2_path.pack(fill="x", pady=(0, 2))
        self.dir_label = tk.Label(
            row2_path,
            textvariable=self.dir_var,
            anchor="w",
            justify="left",
            bg=C["surface"],
            fg=C["text_secondary"],
            font=(ui_font_family(), 9),
            wraplength=820,
        )
        self.dir_label.pack(fill="x", padx=4)
        if not self.dir_var.get().strip():
            self._dir_is_placeholder = True
            self.dir_var.set(t("dir.unset"))

        row3 = ttk.Frame(self._options_card.content, style="Card.TFrame")
        row3.pack(fill="x", pady=2)
        self._cookies_lbl = ttk.Label(row3, text=t("options.cookies"), style="Card.TLabel")
        self._cookies_lbl.pack(side="left")
        self.cookie_var = tk.StringVar(value=self._config.get("cookie_file", ""))
        cookie_field = rounded_entry(row3, self.cookie_var)
        cookie_field.pack(side="left", fill="x", expand=True, padx=8)
        self._cookies_pick_btn = ghost_button(row3, t("options.cookies_pick"), self._choose_cookie)
        self._cookies_pick_btn.pack(side="left")

        action = ttk.Frame(bottom_section)
        action.pack(fill="x", padx=12, pady=(6, 2))

        self.download_btn = primary_button(action, t("action.download"), self._start_download)
        self.download_btn.pack(side="left")

        self.cancel_btn = danger_ghost_button(action, t("action.cancel"), self._cancel_download)
        self.cancel_btn.configure(state="disabled")
        self.cancel_btn.pack(side="left", padx=10)

        self.progress = ttk.Progressbar(
            action,
            mode="determinate",
            maximum=100,
            style="Modern.Horizontal.TProgressbar",
        )
        self.progress.pack(side="left", fill="x", expand=True, padx=10)

        self.status_var = tk.StringVar(value=t("status.ready"))
        ttk.Label(action, textvariable=self.status_var, width=10).pack(side="right")

        env_row = ttk.Frame(bottom_section)
        env_row.pack(fill="x", padx=12, pady=(0, 2))

        self._env_summary = tk.Label(
            env_row,
            text=t("env.checking"),
            anchor="w",
            bg=C["bg"],
            fg=C["text_secondary"],
            font=(ui_font_family(), 9),
        )
        self._env_summary.pack(fill="x")

        paths_header = ttk.Frame(bottom_section)
        paths_header.pack(fill="x", padx=12, pady=(2, 0))
        self._paths_toggle_btn = ghost_button(
            paths_header,
            t("paths.show"),
            self._toggle_install_paths,
        )
        self._paths_toggle_btn.pack(anchor="w")

        self.paths_content = ttk.Frame(bottom_section)
        self._paths_title_lbl = ttk.Label(
            self.paths_content,
            text=t("paths.title"),
            style="Muted.TLabel",
        )
        self._paths_title_lbl.pack(anchor="w")

        self.ytdlp_dir_var = tk.StringVar(value=str(self._install_paths.ytdlp_dir))
        self.ffmpeg_dir_var = tk.StringVar(value=str(self._install_paths.ffmpeg_dir))
        self.nodejs_dir_var = tk.StringVar(value=str(self._install_paths.nodejs_dir))

        self._path_browse_btns: list[tuple[object, str]] = []
        for label, var, title_key in (
            ("yt-dlp", self.ytdlp_dir_var, "paths.browse_ytdlp"),
            ("ffmpeg", self.ffmpeg_dir_var, "paths.browse_ffmpeg"),
            ("Node.js", self.nodejs_dir_var, "paths.browse_node"),
        ):
            row = ttk.Frame(self.paths_content)
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=f"{label}:", width=8).pack(side="left")
            field = rounded_entry(row, var)
            field.pack(side="left", fill="x", expand=True, padx=(0, 6))
            browse_btn = ghost_button(
                row,
                t("paths.browse"),
                lambda v=var, k=title_key: self._browse_install_dir(v, t(k)),
            )
            browse_btn.pack(side="left")
            self._path_browse_btns.append((browse_btn, title_key))

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
            env_btns, t("msg.install.all"), self._install_all
        )
        self.install_all_btn.pack(side="left", padx=(0, 4))
        compact_button(env_btns, "↻", self._refresh_environment).pack(side="left")

        self._sources_lbl = tk.Label(
            bottom_section,
            text=t(
                "sources.footer",
                ytdlp=SOURCE_URLS["yt-dlp"],
                ffmpeg=SOURCE_URLS["ffmpeg"],
                nodejs=SOURCE_URLS["node.js"],
            ),
            anchor="w",
            bg=C["bg"],
            fg=C["text_secondary"],
            font=(ui_font_family(), 8),
            wraplength=860,
            justify="left",
        )
        self._sources_lbl.pack(fill="x", padx=12, pady=(2, 4))

        log_header = ttk.Frame(bottom_section)
        log_header.pack(fill="x", padx=12, pady=(0, 2))
        self._log_toggle_btn = ghost_button(
            log_header,
            t("log.hide"),
            self._toggle_log,
        )
        self._log_toggle_btn.pack(anchor="w")

        self.log_frame = card_frame(
            bottom_section, text=t("log.card"), padding=8, expand_vertical=True
        )
        self.log_text = styled_text(
            self.log_frame.content,
            height=18,
            font=(ui_font_family(), 10),
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
        not_inst = t("env.not_installed")
        installed = t("env.installed")
        y_ver = self._env.yt_dlp_version if self._env.yt_dlp_ready else not_inst
        f_hint = self._env.ffmpeg_source if self._env.ffmpeg_available else not_inst
        n_hint = installed if self._env.js_runtime_ready else not_inst
        return t(
            "env.summary",
            y=y,
            y_ver=y_ver,
            f=f,
            f_hint=f_hint,
            n=n,
            n_hint=n_hint,
        )

    def _format_key(self) -> str:
        label = self.format_var.get()
        for key in FORMAT_KEYS:
            if label == t(f"format.{key}"):
                return key
        return "best"

    def _download_dir_from_ui(self) -> Optional[Path]:
        if self._dir_is_placeholder:
            return None
        raw = self.dir_var.get().strip()
        if not raw:
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
        self._dir_is_placeholder = False
        self.dir_var.set(folder)
        self._save_config()

    def _refresh_environment(self) -> None:
        download_dir = self._download_dir_from_ui()
        self._install_paths = self._current_install_paths()
        self._env = inspect_environment(download_dir, self._install_paths)
        if self._dir_is_placeholder or not self.dir_var.get().strip():
            self._dir_is_placeholder = False
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
        self.install_all_btn.configure(
            text=t("msg.install.all"),
            state="normal" if need_any else "disabled",
        )

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
            messagebox.showwarning(t("msg.clipboard.title"), t("msg.clipboard.empty"))
            return
        self.url_text.insert("end", text.strip() + "\n")

    def _dialog_initial_dir(self, current: str) -> str:
        if self._dir_is_placeholder:
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
        chosen = self._pick_folder(t("msg.dir.pick_title"))
        if not chosen:
            return
        try:
            Path(chosen).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showwarning(
                t("msg.dir.bad_title"),
                t("msg.dir.bad", err=exc),
                parent=self,
            )
            return
        self._set_download_dir(chosen)
        messagebox.showinfo(
            t("msg.dir.ok_title"),
            t("msg.dir.ok", path=chosen),
            parent=self,
        )

    def _open_download_dir(self) -> None:
        path = self._download_dir_from_ui() or self._env.download_dir
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showwarning(
                t("msg.dir.bad_title"),
                t("msg.dir.open_fail", path=path, err=exc),
                parent=self,
            )
            return
        import os

        os.startfile(path)

    def _choose_cookie(self) -> None:
        chosen = filedialog.askopenfilename(
            title=t("msg.cookie.title"),
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
            items = t("sep.list").join(missing)
            if messagebox.askyesno(
                t("msg.missing.title"),
                t("msg.missing.body", items=items),
            ):
                self._install_all()
            return
        if optional and messagebox.askyesno(
            t("msg.node.title"),
            t("msg.node.body", url=SOURCE_URLS["node.js"]),
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
            messagebox.showinfo(t("msg.wait.title"), t("msg.wait.busy"))
            return

        self._set_install_busy(True)
        self._append_log(t("log.install.start", title=title))
        self.status_var.set(t("status.installing", title=title))
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
                    lambda: messagebox.showinfo(
                        t("msg.install.done_title"),
                        t("msg.install.done", title=title),
                    ),
                )
            except Exception as exc:
                self._append_log(t("log.install.fail", err=exc))
                self.after(
                    0,
                    lambda: messagebox.showerror(
                        t("msg.install.fail_title"),
                        t("msg.install.fail", err=exc),
                    ),
                )
            finally:
                self.after(0, lambda: self._set_install_busy(False))
                self.after(0, lambda: self.status_var.set(t("status.ready")))

        self._worker = threading.Thread(target=worker, daemon=True)
        self._worker.start()

    def _install_component(self, name: str) -> None:
        paths = self._current_install_paths()
        save_install_paths(paths)
        self._install_paths = paths

        if name == "yt-dlp":
            if ytdlp_is_ready(paths):
                self._refresh_environment()
                messagebox.showinfo(
                    "yt-dlp",
                    t("msg.ytdlp.ok", ver=self._env.yt_dlp_version),
                )
                return
            self._run_install_worker(
                install_ytdlp=True,
                install_ffmpeg_tool=False,
                install_node=False,
                title=t("msg.install.ytdlp", url=SOURCE_URLS["yt-dlp"]),
            )
        elif name == "ffmpeg":
            if find_ffmpeg_exe(paths):
                self._refresh_environment()
                messagebox.showinfo(
                    "ffmpeg",
                    t("msg.ffmpeg.ok", hint=self._env.ffmpeg_source),
                )
                return
            self._run_install_worker(
                install_ytdlp=False,
                install_ffmpeg_tool=True,
                install_node=False,
                title=t("msg.install.ffmpeg", url=SOURCE_URLS["ffmpeg"]),
            )
        elif name == "node.js":
            if find_node_exe(paths):
                self._refresh_environment()
                messagebox.showinfo("Node.js", t("msg.node.ok"))
                return
            self._run_install_worker(
                install_ytdlp=False,
                install_ffmpeg_tool=False,
                install_node=True,
                title=t("msg.install.node", url=SOURCE_URLS["node.js"]),
            )

    def _install_all(self) -> None:
        paths = self._current_install_paths()
        missing = missing_components(paths)
        optional = optional_components(paths)
        if not missing and not optional:
            messagebox.showinfo(t("msg.deps.ok_title"), t("msg.deps.ok"))
            return
        self._run_install_worker(
            install_ytdlp="yt-dlp" in missing,
            install_ffmpeg_tool="ffmpeg" in missing,
            install_node=bool(optional),
            title=t("msg.install.all"),
        )

    def _install_dependencies(self, include_node: bool = True) -> None:
        self._install_all()

    def _start_download(self) -> None:
        if self._worker and self._worker.is_alive():
            return

        urls = extract_urls(self.url_text.get("1.0", "end"))
        if not urls:
            messagebox.showwarning(t("msg.url.title"), t("msg.url.empty"))
            return

        if missing_components(self._current_install_paths()):
            if messagebox.askyesno(t("msg.missing.title"), t("msg.missing.dl")):
                self._install_all()
            return

        if not self._env.js_runtime_ready and messagebox.askyesno(
            t("msg.node.title"),
            t("msg.node.download", url=SOURCE_URLS["node.js"]),
        ):
            self._install_component("node.js")
            return

        output_dir = self._download_dir_from_ui()
        if output_dir is None:
            messagebox.showwarning(
                t("msg.dir.bad_title"),
                t("msg.dir.need_pick"),
                parent=self,
            )
            return
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(
                t("msg.dir.bad_title"),
                t("msg.dir.mkdir_fail", path=output_dir, err=exc),
                parent=self,
            )
            return

        cookie_path = (
            Path(self.cookie_var.get().strip()) if self.cookie_var.get().strip() else None
        )
        if cookie_path and not cookie_path.is_file():
            messagebox.showwarning("Cookies", t("msg.cookie.missing"))
            return

        self._save_config()
        self._cancel_flag = False
        self._set_busy(True)
        self.progress["value"] = 0
        self.status_var.set(t("status.preparing"))
        self._append_log(t("log.dl.start"))
        self._append_log(t("log.dl.format", fmt=format_label(self._format_key())))
        self._append_log(t("log.dl.dir", dir=output_dir))

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
                parts = [t("log.dl.summary_ok", n=success)]
                if failed:
                    parts.append(t("log.dl.summary_fail", n=failed))
                if skipped:
                    parts.append(t("log.dl.summary_skip", n=skipped))
                summary = t("sep.list").join(parts)
                self._append_log(t("log.dl.done", summary=summary))
                self.after(
                    0,
                    lambda: messagebox.showinfo(
                        t("msg.done.title"),
                        summary + f"\n{output_dir}",
                    ),
                )
            except DownloadCancelled:
                self._append_log(t("log.dl.cancelled"))
                self.after(0, lambda: self.status_var.set(t("status.cancelled")))
            except Exception as exc:
                self._append_log(t("log.dl.error", err=exc))
                self.after(0, lambda: messagebox.showerror(t("msg.fail.title"), str(exc)))
            finally:
                self.after(0, lambda: self._set_busy(False))

        self._worker = threading.Thread(target=worker, daemon=True)
        self._worker.start()

    def _cancel_download(self) -> None:
        self._cancel_flag = True
        self.status_var.set(t("status.cancelling"))
        self._append_log(t("log.cancel"))

    def _on_close(self) -> None:
        self._save_config()
        if self._worker and self._worker.is_alive():
            if messagebox.askyesno(t("msg.quit.title"), t("msg.quit.body")):
                self._cancel_flag = True
                self.destroy()
            return
        self.destroy()


def main() -> None:
    app = YouTubeDownloaderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
