"""Auto-clip page: per-URL time ranges with add-segment support."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass, field
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Optional

from clip_engine import ClipSegment, ClipUrlJob, seconds_from_hms
from engine import extract_urls
from i18n import t, ui_font_family
from ui_styles import (
    C,
    accent_button,
    card_frame,
    danger_ghost_button,
    compact_folder_picker_button,
    ghost_button,
    rounded_entry,
)

_TIME_ENTRY_FONT = (ui_font_family(), 10)
_TIME_ENTRY_STYLE = dict(
    bg=C["surface_alt"],
    fg=C["text"],
    insertbackground=C["text"],
    relief="solid",
    bd=1,
    highlightthickness=1,
    highlightbackground="#dfe3ea",
    highlightcolor=C["accent"],
    justify="center",
)

if TYPE_CHECKING:
    from main import YouTubeDownloaderApp


@dataclass
class _TimeFields:
    h_var: tk.StringVar
    m_var: tk.StringVar
    s_var: tk.StringVar
    h_unit_lbl: tk.Label
    m_unit_lbl: tk.Label
    s_unit_lbl: tk.Label


@dataclass
class _SegmentRow:
    frame: tk.Frame
    start_title_lbl: tk.Label
    end_title_lbl: tk.Label
    start: _TimeFields
    end: _TimeFields
    remove_btn: tk.Button


@dataclass
class _UrlEntry:
    card: object
    url_var: tk.StringVar
    url_lbl: tk.Label
    segments_host: tk.Frame
    remove_url_btn: Optional[tk.Button] = None
    add_segment_btn: Optional[tk.Button] = None
    add_segment_row: Optional[tk.Frame] = None
    segments: list[_SegmentRow] = field(default_factory=list)


class ClipPage(ttk.Frame):
    def __init__(self, master: tk.Misc, app: YouTubeDownloaderApp) -> None:
        super().__init__(master, style="TFrame")
        self._app = app
        self._url_entries: list[_UrlEntry] = []
        self._build_ui()
        self._add_url_entry(initial=True)

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self, style="TFrame")
        toolbar.pack(fill="x", padx=12, pady=(8, 4))

        self._hint_lbl = ttk.Label(
            toolbar,
            text=t("clip.hint"),
            style="Muted.TLabel",
            wraplength=820,
        )
        self._hint_lbl.pack(anchor="w", fill="x")

        paths_card = card_frame(
            self,
            text=t("clip.paths_card"),
            padding=4,
            compact=True,
        )
        paths_card.pack(fill="x", padx=12, pady=(2, 2))
        self._app._clip_paths_card = paths_card

        save_row = ttk.Frame(paths_card.content, style="Card.TFrame")
        save_row.pack(fill="x", pady=(0, 1))
        self._app._clip_save_lbl = ttk.Label(
            save_row, text=t("clip.save"), style="Card.TLabel"
        )
        self._app._clip_save_lbl.pack(side="left")
        self._app._clip_pick_folder_btn = compact_folder_picker_button(
            save_row, t("clip.pick_folder"), self._app._choose_clip_dir
        )
        self._app._clip_pick_folder_btn.pack(side="left", padx=(4, 3))
        self._app._clip_open_folder_btn = ghost_button(
            save_row, t("clip.open_folder"), self._app._open_clip_dir
        )
        self._app._clip_open_folder_btn.pack(side="left")

        self._app._clip_dir_label = tk.Label(
            paths_card.content,
            textvariable=self._app.clip_dir_var,
            anchor="w",
            justify="left",
            bg=C["surface"],
            fg=C["text_secondary"],
            font=(ui_font_family(), 8),
            wraplength=780,
        )
        self._app._clip_dir_label.pack(anchor="w", padx=2, pady=(0, 2))

        cache_row = ttk.Frame(paths_card.content, style="Card.TFrame")
        cache_row.pack(fill="x", pady=(2, 1))
        self._app._clip_cache_save_lbl = ttk.Label(
            cache_row, text=t("clip.cache"), style="Card.TLabel"
        )
        self._app._clip_cache_save_lbl.pack(side="left")
        self._app._clip_cache_pick_btn = compact_folder_picker_button(
            cache_row, t("clip.pick_cache"), self._app._choose_clip_cache_dir
        )
        self._app._clip_cache_pick_btn.pack(side="left", padx=(4, 3))
        self._app._clip_cache_open_btn = ghost_button(
            cache_row, t("clip.open_cache"), self._app._open_clip_cache_dir
        )
        self._app._clip_cache_open_btn.pack(side="left", padx=(0, 3))
        self._app._clip_cache_clear_btn = danger_ghost_button(
            cache_row, t("clip.clear_cache"), self._app._clear_clip_cache
        )
        self._app._clip_cache_clear_btn.pack(side="left")

        self._app._clip_cache_dir_label = tk.Label(
            paths_card.content,
            textvariable=self._app.clip_cache_dir_var,
            anchor="w",
            justify="left",
            bg=C["surface"],
            fg=C["text_secondary"],
            font=(ui_font_family(), 8),
            wraplength=780,
        )
        self._app._clip_cache_dir_label.pack(anchor="w", padx=2)
        self._app._clip_cache_hint_lbl = ttk.Label(
            paths_card.content,
            text=t("clip.cache_hint"),
            style="CardMuted.TLabel",
            wraplength=780,
            font=(ui_font_family(), 8),
        )
        self._app._clip_cache_hint_lbl.pack(anchor="w", padx=2, pady=(0, 0))
        # Backward compat for language refresh in main.py
        self._app._clip_cache_card = paths_card

        btn_row = ttk.Frame(self, style="TFrame")
        btn_row.pack(fill="x", padx=12, pady=(2, 4))
        self._add_url_btn = ghost_button(btn_row, t("clip.add_url"), self._add_url_entry)
        self._add_url_btn.pack(side="left")
        self._paste_btn = ghost_button(btn_row, t("clip.paste_url"), self._paste_url)
        self._paste_btn.pack(side="left", padx=8)

        scroll_wrap = ttk.Frame(self, style="TFrame")
        scroll_wrap.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 6))

        self._canvas = tk.Canvas(
            scroll_wrap,
            bg=C["bg"],
            highlightthickness=0,
            borderwidth=0,
        )
        scrollbar = ttk.Scrollbar(scroll_wrap, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill=tk.BOTH, expand=True)

        self._entries_frame = ttk.Frame(self._canvas, style="TFrame")
        self._canvas_window = self._canvas.create_window(
            (0, 0),
            window=self._entries_frame,
            anchor="nw",
        )
        self._entries_frame.bind(
            "<Configure>",
            lambda _e: self._canvas.configure(scrollregion=self._canvas.bbox("all")),
        )
        self._canvas.bind("<Configure>", self._on_canvas_resize)
        scroll_wrap.bind("<Enter>", self._bind_mousewheel)
        scroll_wrap.bind("<Leave>", self._unbind_mousewheel)

        action_row = ttk.Frame(self, style="TFrame")
        action_row.pack(fill="x", padx=12, pady=(0, 8))
        self._clip_btn = accent_button(
            action_row, t("clip.start"), self._start_clip
        )
        self._clip_btn.pack(side="left")

    def _on_canvas_resize(self, event: tk.Event) -> None:
        self._canvas.itemconfigure(self._canvas_window, width=event.width)

    def _bind_mousewheel(self, _event: tk.Event) -> None:
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event: tk.Event) -> None:
        self._canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event: tk.Event) -> None:
        delta = int(-1 * (event.delta / 120))
        self._canvas.yview_scroll(delta, "units")

    def _apply_time_field_labels(self, fields: _TimeFields) -> None:
        fields.h_unit_lbl.configure(text=t("clip.hour"))
        fields.m_unit_lbl.configure(text=t("clip.minute"))
        fields.s_unit_lbl.configure(text=t("clip.second"))

    def apply_language(self) -> None:
        self._hint_lbl.configure(text=t("clip.hint"))
        if hasattr(self._app, "_clip_save_lbl"):
            self._app._clip_save_lbl.configure(text=t("clip.save"))
            self._app._clip_pick_folder_btn.configure(text=t("clip.pick_folder"))
            self._app._clip_open_folder_btn.configure(text=t("clip.open_folder"))
        if hasattr(self._app, "_clip_paths_card"):
            self._app._clip_paths_card.set_title(t("clip.paths_card"))
        if hasattr(self._app, "_clip_cache_save_lbl"):
            self._app._clip_cache_save_lbl.configure(text=t("clip.cache"))
            self._app._clip_cache_pick_btn.configure(text=t("clip.pick_cache"))
            self._app._clip_cache_open_btn.configure(text=t("clip.open_cache"))
            self._app._clip_cache_clear_btn.configure(text=t("clip.clear_cache"))
        if hasattr(self._app, "_clip_cache_hint_lbl"):
            self._app._clip_cache_hint_lbl.configure(text=t("clip.cache_hint"))
        self._add_url_btn.configure(text=t("clip.add_url"))
        self._paste_btn.configure(text=t("clip.paste_url"))
        self._clip_btn.configure(text=t("clip.start"))
        for index, entry in enumerate(self._url_entries, start=1):
            entry.card.set_title(t("clip.url_card", index=index))
            entry.url_lbl.configure(text=t("clip.url_label"))
            if entry.remove_url_btn is not None:
                entry.remove_url_btn.configure(text=t("clip.remove_url"))
            if entry.add_segment_btn is not None:
                entry.add_segment_btn.configure(text=t("clip.add_segment"))
            for seg in entry.segments:
                seg.start_title_lbl.configure(text=t("clip.start_label"))
                seg.end_title_lbl.configure(text=t("clip.end"))
                seg.remove_btn.configure(text=t("clip.remove_segment"))
                self._apply_time_field_labels(seg.start)
                self._apply_time_field_labels(seg.end)

    def _reset_time_fields(self, fields: _TimeFields) -> None:
        fields.h_var.set("0")
        fields.m_var.set("0")
        fields.s_var.set("0")

    def _time_entry(self, parent: tk.Misc, var: tk.StringVar, *, width: int) -> tk.Entry:
        entry = tk.Entry(
            parent,
            textvariable=var,
            width=width,
            font=_TIME_ENTRY_FONT,
            **_TIME_ENTRY_STYLE,
        )
        return entry

    def _build_time_fields(
        self,
        parent: tk.Frame,
        *,
        h: str = "0",
        m: str = "0",
        s: str = "0",
    ) -> _TimeFields:
        grid = tk.Frame(parent, bg=C["surface"])
        grid.pack(side="left")

        h_var = tk.StringVar(value=h)
        m_var = tk.StringVar(value=m)
        s_var = tk.StringVar(value=s)

        col = 0
        self._time_entry(grid, h_var, width=3).grid(
            row=0, column=col, padx=(0, 2), pady=1, sticky="w"
        )
        col += 1
        h_unit = tk.Label(
            grid,
            text=t("clip.hour"),
            bg=C["surface"],
            fg=C["text_secondary"],
            font=(ui_font_family(), 9),
        )
        h_unit.grid(row=0, column=col, padx=(0, 10), sticky="w")
        col += 1

        self._time_entry(grid, m_var, width=2).grid(
            row=0, column=col, padx=(0, 2), pady=1, sticky="w"
        )
        col += 1
        m_unit = tk.Label(
            grid,
            text=t("clip.minute"),
            bg=C["surface"],
            fg=C["text_secondary"],
            font=(ui_font_family(), 9),
        )
        m_unit.grid(row=0, column=col, padx=(0, 10), sticky="w")
        col += 1

        self._time_entry(grid, s_var, width=2).grid(
            row=0, column=col, padx=(0, 2), pady=1, sticky="w"
        )
        col += 1
        s_unit = tk.Label(
            grid,
            text=t("clip.second"),
            bg=C["surface"],
            fg=C["text_secondary"],
            font=(ui_font_family(), 9),
        )
        s_unit.grid(row=0, column=col, sticky="w")

        return _TimeFields(
            h_var=h_var,
            m_var=m_var,
            s_var=s_var,
            h_unit_lbl=h_unit,
            m_unit_lbl=m_unit,
            s_unit_lbl=s_unit,
        )

    def _read_seconds(self, fields: _TimeFields) -> float:
        return seconds_from_hms(
            fields.h_var.get(),
            fields.m_var.get(),
            fields.s_var.get(),
        )

    def _time_fields_empty(self, fields: _TimeFields) -> bool:
        return self._read_seconds(fields) <= 0

    def _paste_url(self) -> None:
        try:
            text = self._app.clipboard_get().strip()
        except tk.TclError:
            messagebox.showwarning(
                t("msg.clipboard.title"),
                t("msg.clipboard.empty"),
                parent=self._app,
            )
            return
        urls = extract_urls(text)
        if not urls:
            messagebox.showwarning(
                t("clip.no_url_title"),
                t("clip.no_url_body"),
                parent=self._app,
            )
            return
        for url in urls:
            entry = self._add_url_entry()
            entry.url_var.set(url)

    def _add_url_entry(self, *, initial: bool = False) -> _UrlEntry:
        index = len(self._url_entries) + 1
        card = card_frame(
            self._entries_frame,
            text=t("clip.url_card", index=index),
            padding=8,
        )
        card.pack(fill="x", pady=(0, 8))

        url_var = tk.StringVar()
        url_lbl = tk.Label(
            card.content,
            text="",
            bg=C["surface"],
            fg=C["text"],
            font=(ui_font_family(), 10),
        )
        entry = _UrlEntry(
            card=card,
            url_var=url_var,
            url_lbl=url_lbl,
            segments_host=tk.Frame(card.content, bg=C["surface"]),
        )

        url_row = tk.Frame(card.content, bg=C["surface"])
        url_row.pack(fill="x", pady=(0, 6))
        remove_btn = danger_ghost_button(
            url_row,
            t("clip.remove_url"),
            lambda e=entry: self._remove_url_entry(e),
        )
        remove_btn.pack(side="left", padx=(0, 8))
        entry.remove_url_btn = remove_btn
        url_lbl.pack(in_=url_row, side="left")
        url_field = rounded_entry(url_row, entry.url_var)
        url_field.pack(side="left", fill="x", expand=True, padx=(8, 0))

        entry.segments_host.pack(fill="x")
        self._url_entries.append(entry)

        self._add_segment_row(entry, is_first=True)
        entry.url_lbl.configure(text=t("clip.url_label"))
        return entry

    def _remove_url_entry(self, entry: _UrlEntry) -> None:
        if len(self._url_entries) <= 1:
            entry.url_var.set("")
            for seg in entry.segments:
                self._reset_time_fields(seg.start)
                self._reset_time_fields(seg.end)
            return
        entry.card.destroy()
        self._url_entries.remove(entry)
        self._renumber_url_cards()

    def _renumber_url_cards(self) -> None:
        for index, entry in enumerate(self._url_entries, start=1):
            entry.card.set_title(t("clip.url_card", index=index))

    def _add_segment_row(self, entry: _UrlEntry, *, is_first: bool = False) -> _SegmentRow:
        if entry.add_segment_row is not None:
            entry.add_segment_row.pack_forget()

        row = tk.Frame(entry.segments_host, bg=C["surface"])
        row.pack(fill="x", pady=4)

        tools_row = tk.Frame(row, bg=C["surface"])
        tools_row.pack(fill="x", anchor="w")
        remove_btn = danger_ghost_button(
            tools_row,
            t("clip.remove_segment"),
            lambda e=entry, r=row: self._remove_segment_row(e, r),
        )
        remove_btn.pack(side="left")

        start_line = tk.Frame(row, bg=C["surface"])
        start_line.pack(anchor="w", pady=(4, 2))
        start_title_lbl = tk.Label(
            start_line,
            text=t("clip.start_label"),
            bg=C["surface"],
            fg=C["text"],
            font=(ui_font_family(), 10),
            width=6,
            anchor="w",
        )
        start_title_lbl.pack(side="left", padx=(0, 6))
        start_fields = self._build_time_fields(start_line, h="0", m="0", s="0")

        end_line = tk.Frame(row, bg=C["surface"])
        end_line.pack(anchor="w", pady=(0, 2))
        end_title_lbl = tk.Label(
            end_line,
            text=t("clip.end"),
            bg=C["surface"],
            fg=C["text"],
            font=(ui_font_family(), 10),
            width=6,
            anchor="w",
        )
        end_title_lbl.pack(side="left", padx=(0, 6))
        end_fields = self._build_time_fields(end_line)

        seg = _SegmentRow(
            frame=row,
            start_title_lbl=start_title_lbl,
            end_title_lbl=end_title_lbl,
            start=start_fields,
            end=end_fields,
            remove_btn=remove_btn,
        )
        entry.segments.append(seg)

        add_row = tk.Frame(entry.segments_host, bg=C["surface"])
        add_row.pack(fill="x", pady=(4, 0))
        entry.add_segment_btn = ghost_button(
            add_row,
            t("clip.add_segment"),
            lambda e=entry: self._add_segment_row(e),
        )
        entry.add_segment_btn.pack(anchor="w")
        entry.add_segment_row = add_row
        return seg

    def _remove_segment_row(self, entry: _UrlEntry, row: tk.Frame) -> None:
        if len(entry.segments) <= 1:
            seg = entry.segments[0]
            if seg.frame is row:
                self._reset_time_fields(seg.start)
                self._reset_time_fields(seg.end)
            return
        for seg in list(entry.segments):
            if seg.frame is row:
                seg.frame.destroy()
                entry.segments.remove(seg)
                break

    def collect_jobs(self) -> list[ClipUrlJob]:
        jobs: list[ClipUrlJob] = []
        for entry in self._url_entries:
            url = entry.url_var.get().strip()
            if not url:
                continue
            segments: list[ClipSegment] = []
            for seg_index, seg in enumerate(entry.segments, start=1):
                try:
                    start = self._read_seconds(seg.start)
                    end = self._read_seconds(seg.end)
                except ValueError:
                    raise ValueError(
                        t("clip.bad_time", index=seg_index, url=url[:60])
                    ) from None

                if self._time_fields_empty(seg.start) and self._time_fields_empty(seg.end):
                    continue
                if self._time_fields_empty(seg.end):
                    raise ValueError(
                        t("clip.no_end", index=seg_index, url=url[:60])
                    )
                if end <= start:
                    raise ValueError(
                        t("clip.bad_range", index=seg_index, url=url[:60])
                    )
                segments.append(ClipSegment(start=start, end=end))
            if not segments:
                raise ValueError(t("clip.no_segments", url=url[:60]))
            jobs.append(ClipUrlJob(url=url, segments=segments))
        if not jobs:
            raise ValueError(t("clip.no_jobs"))
        return jobs

    def _start_clip(self) -> None:
        try:
            jobs = self.collect_jobs()
        except ValueError as exc:
            messagebox.showwarning(
                t("clip.no_url_title"),
                str(exc),
                parent=self._app,
            )
            return
        self._app.start_clip_jobs(jobs)
