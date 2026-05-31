"""Canvas-based rounded widgets for a modern flat UI in tkinter."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from typing import Callable, Optional

from ui_theme import COLORS

C = COLORS
FONT = ("Microsoft YaHei UI", 10)
FONT_BOLD = ("Microsoft YaHei UI", 10, "bold")


def _parent_bg(widget: tk.Misc) -> str:
    try:
        return str(widget.cget("bg"))
    except tk.TclError:
        return C["bg"]


def draw_round_rect(
    canvas: tk.Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    radius: float,
    *,
    fill: str = "",
    outline: str = "",
    width: int = 1,
    tags: str = "",
) -> int:
    r = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    if r <= 0:
        return canvas.create_rectangle(
            x1, y1, x2, y2, fill=fill, outline=outline, width=width, tags=tags
        )
    points = [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]
    return canvas.create_polygon(
        points,
        smooth=True,
        fill=fill,
        outline=outline,
        width=width,
        tags=tags,
    )


BUTTON_VARIANTS = {
    "primary": {
        "font": FONT_BOLD,
        "fg": "#ffffff",
        "bg": C["accent"],
        "hover": C["accent_dark"],
        "press": "#b30000",
        "disabled_bg": "#fca5a5",
        "disabled_fg": "#ffffff",
        "border": None,
        "padx": 18,
        "pady": 9,
        "radius": 12,
    },
    "ghost": {
        "font": FONT,
        "fg": C["text"],
        "bg": C["surface"],
        "hover": C["surface_alt"],
        "press": "#eef0f3",
        "disabled_bg": C["surface_alt"],
        "disabled_fg": C["text_secondary"],
        "border": C["border"],
        "padx": 14,
        "pady": 7,
        "radius": 10,
    },
    "accent": {
        "font": FONT_BOLD,
        "fg": C["accent_dark"],
        "bg": C["accent_soft"],
        "hover": "#ffd6d6",
        "press": "#ffb3b3",
        "disabled_bg": C["surface_alt"],
        "disabled_fg": C["text_secondary"],
        "border": "#fecaca",
        "padx": 14,
        "pady": 7,
        "radius": 10,
    },
    "danger": {
        "font": FONT,
        "fg": C["accent_dark"],
        "bg": C["surface"],
        "hover": C["accent_soft"],
        "press": "#ffd6d6",
        "disabled_bg": C["surface_alt"],
        "disabled_fg": C["text_secondary"],
        "border": "#fecaca",
        "padx": 14,
        "pady": 7,
        "radius": 10,
    },
    "compact": {
        "font": FONT_BOLD,
        "fg": C["text_secondary"],
        "bg": C["surface"],
        "hover": C["surface_alt"],
        "press": "#eef0f3",
        "disabled_bg": C["surface_alt"],
        "disabled_fg": C["text_secondary"],
        "border": C["border"],
        "padx": 10,
        "pady": 5,
        "radius": 8,
    },
}


class RoundedButton(tk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        text: str,
        command: Callable[[], None],
        *,
        variant: str = "ghost",
        **kwargs,
    ) -> None:
        bg = _parent_bg(parent)
        super().__init__(parent, bg=bg, **kwargs)
        self._text = text
        self._command = command
        self._variant_name = variant
        self._style = dict(BUTTON_VARIANTS[variant])
        self._enabled = True
        self._hover = False
        self._pressed = False

        self._canvas = tk.Canvas(
            self,
            highlightthickness=0,
            borderwidth=0,
            bg=bg,
            cursor="hand2",
        )
        self._canvas.pack()

        for sequence, handler in (
            ("<Enter>", self._on_enter),
            ("<Leave>", self._on_leave),
            ("<ButtonPress-1>", self._on_press),
            ("<ButtonRelease-1>", self._on_release),
            ("<Button-1>", self._on_click),
            ("<Configure>", lambda _e: self._redraw()),
        ):
            self._canvas.bind(sequence, handler)

        self._measure_and_resize()

    def _measure_and_resize(self) -> None:
        font = tkfont.Font(font=self._style["font"])
        tw = font.measure(self._text)
        th = font.metrics("linespace")
        padx = self._style["padx"]
        pady = self._style["pady"]
        width = tw + padx * 2
        height = th + pady * 2
        self._canvas.configure(width=width, height=height)
        self._redraw()

    def _colors(self) -> tuple[str, str, Optional[str]]:
        style = self._style
        if not self._enabled:
            return style["disabled_bg"], style["disabled_fg"], style["border"]
        if self._pressed:
            return style["press"], style["fg"], style["border"]
        if self._hover:
            return style["hover"], style["fg"], style["border"]
        return style["bg"], style["fg"], style["border"]

    def _redraw(self) -> None:
        self._canvas.delete("all")
        w = int(self._canvas.winfo_width() or 1)
        h = int(self._canvas.winfo_height() or 1)
        fill, fg, border = self._colors()
        radius = self._style["radius"]
        outline = border or fill
        draw_round_rect(
            self._canvas,
            1,
            1,
            w - 1,
            h - 1,
            radius,
            fill=fill,
            outline=outline,
            width=1 if border else 0,
        )
        self._canvas.create_text(
            w // 2,
            h // 2,
            text=self._text,
            fill=fg,
            font=self._style["font"],
        )

    def _on_enter(self, _event: tk.Event) -> None:
        if self._enabled:
            self._hover = True
            self._redraw()

    def _on_leave(self, _event: tk.Event) -> None:
        self._hover = False
        self._pressed = False
        self._redraw()

    def _on_press(self, _event: tk.Event) -> None:
        if self._enabled:
            self._pressed = True
            self._redraw()

    def _on_click(self, _event: tk.Event) -> None:
        if self._enabled:
            self._command()

    def _on_release(self, event: tk.Event) -> None:
        if not self._enabled:
            return
        self._pressed = False
        self._redraw()

    def configure(self, cnf=None, **kwargs):  # noqa: ANN001
        if cnf:
            kwargs.update(cnf)
        if "state" in kwargs:
            self._enabled = str(kwargs.pop("state")) != "disabled"
            self._canvas.configure(cursor="hand2" if self._enabled else "arrow")
            self._redraw()
        if "text" in kwargs:
            self._text = str(kwargs.pop("text"))
            self._measure_and_resize()
        if kwargs:
            super().configure(kwargs)
        return None

    config = configure


class RoundedCard(tk.Frame):
    """White card with rounded border."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        title: str = "",
        padding: int = 12,
        radius: int = 14,
        expand_vertical: bool = False,
        compact: bool = False,
        **kwargs,
    ) -> None:
        page_bg = _parent_bg(parent)
        super().__init__(parent, bg=page_bg, **kwargs)
        self._page_bg = page_bg
        self._title = title
        self._padding = padding
        self._radius = 10 if compact else radius
        self._expand_vertical = expand_vertical
        self._compact = compact

        self._canvas = tk.Canvas(
            self,
            highlightthickness=0,
            borderwidth=0,
            bg=page_bg,
        )
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)

        self.content = tk.Frame(self, bg=C["surface"])
        self.content.place(x=padding, y=padding, relwidth=1, width=-padding * 2)

        self._title_label: tk.Label | None = None
        if title:
            title_font = (FONT_BOLD[0], 9, "bold") if compact else FONT_BOLD
            self._title_label = tk.Label(
                self.content,
                text=title,
                bg=C["surface"],
                fg=C["text"],
                font=title_font,
                anchor="w",
            )
            self._title_label.pack(anchor="w", pady=(0, 3 if compact else 6))

        self.content.bind("<Configure>", self._sync_shape, add="+")
        self.bind("<Configure>", self._sync_shape, add="+")

    def set_title(self, text: str) -> None:
        self._title = text
        if self._title_label is not None:
            self._title_label.configure(text=text)

    def _sync_shape(self, _event: Optional[tk.Event] = None) -> None:
        self.update_idletasks()
        pad = self._padding
        w = max(self.winfo_width(), self.content.winfo_reqwidth() + pad * 2, 1)
        ch = self.content.winfo_reqheight()
        if self._expand_vertical:
            h = max(self.winfo_height(), ch + pad * 2)
            self.content.place(
                x=pad,
                y=pad,
                width=max(w - pad * 2, 0),
                relheight=1,
                height=-pad * 2,
            )
        else:
            h = ch + pad * 2
            self.content.place(
                x=pad,
                y=pad,
                width=max(w - pad * 2, 0),
            )
            if h > 0:
                self.configure(height=h)
        self._canvas.delete("all")
        draw_round_rect(
            self._canvas,
            1,
            1,
            max(w - 1, 2),
            max(h - 1, 2),
            self._radius,
            fill=C["surface"],
            outline="#dfe3ea",
            width=1,
        )
        self.content.lift()


class RoundedField(tk.Frame):
    """Rounded single-line input shell."""

    def __init__(
        self,
        parent: tk.Misc,
        textvariable: tk.Variable,
        *,
        height: int = 36,
        radius: int = 10,
        compact: bool = False,
        **kwargs,
    ) -> None:
        page_bg = _parent_bg(parent)
        super().__init__(parent, bg=page_bg)
        self._radius = radius
        self._height = height
        self._page_bg = page_bg
        self._compact = compact
        entry_width = kwargs.pop("width", None)
        self._entry_width = int(entry_width) if entry_width else 4

        self._canvas = tk.Canvas(
            self,
            height=height,
            highlightthickness=0,
            borderwidth=0,
            bg=page_bg,
        )
        if compact:
            self._canvas.pack(side="left", fill="none", expand=False)
        else:
            self._canvas.pack(fill="x", expand=True)
        self._canvas.bind("<Configure>", self._redraw_border)

        entry_kwargs = dict(
            textvariable=textvariable,
            relief="flat",
            bd=0,
            bg=C["surface_alt"],
            fg=C["text"],
            insertbackground=C["text"],
            font=FONT,
            highlightthickness=0,
        )
        if compact:
            entry_kwargs["width"] = self._entry_width
            entry_kwargs["justify"] = "center"
        entry_kwargs.update(kwargs)
        self.entry = tk.Entry(self._canvas, **entry_kwargs)
        self._window = self._canvas.create_window(
            radius + 4,
            height // 2,
            window=self.entry,
            anchor="w",
        )
        self._canvas.bind("<Button-1>", self._focus_entry)
        self.entry.bind("<FocusIn>", lambda _e: self._redraw_border())
        self.after_idle(self._redraw_border)

    def _focus_entry(self, _event: Optional[tk.Event] = None) -> None:
        self.entry.focus_set()

    def _redraw_border(self, event: Optional[tk.Event] = None) -> None:
        h = self._height
        if self._compact:
            font = tkfont.Font(font=FONT)
            char_w = max(font.measure("0"), font.metrics("avgcharwidth"))
            w = int(char_w * self._entry_width + self._radius * 2 + 20)
            w = max(w, 44)
            self._canvas.configure(width=w)
        else:
            w = int(event.width if event else self._canvas.winfo_width() or 200)
        self._canvas.delete("border")
        draw_round_rect(
            self._canvas,
            1,
            1,
            w - 1,
            h - 1,
            self._radius,
            fill=C["surface_alt"],
            outline="#dfe3ea",
            width=1,
            tags="border",
        )
        inner_w = max(w - self._radius * 2 - 12, 24 if self._compact else 40)
        self._canvas.itemconfigure(self._window, width=inner_w)
        self._canvas.coords(self._window, self._radius + 6, h // 2)


class RoundedComboboxShell(tk.Frame):
    """Rounded shell for ttk.Combobox."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        height: int = 36,
        radius: int = 10,
    ) -> None:
        page_bg = _parent_bg(parent)
        super().__init__(parent, bg=page_bg)
        self._radius = radius
        self._height = height

        self._canvas = tk.Canvas(
            self,
            height=height,
            highlightthickness=0,
            borderwidth=0,
            bg=page_bg,
        )
        self._canvas.pack(fill="x", expand=True)
        self._canvas.bind("<Configure>", self._redraw_border)

        self.inner = tk.Frame(self._canvas, bg=C["surface"])
        self._window = self._canvas.create_window(
            self._radius + 4,
            height // 2,
            window=self.inner,
            anchor="w",
        )

    def _redraw_border(self, event: Optional[tk.Event] = None) -> None:
        w = int(event.width if event else self._canvas.winfo_width() or 200)
        h = self._height
        self._canvas.delete("border")
        draw_round_rect(
            self._canvas,
            1,
            1,
            w - 1,
            h - 1,
            self._radius,
            fill=C["surface"],
            outline="#dfe3ea",
            width=1,
            tags="border",
        )
        inner_w = max(w - self._radius * 2 - 12, 60)
        self.inner.configure(width=inner_w, height=h - 8)
        self._canvas.itemconfigure(self._window, width=inner_w)
        self._canvas.coords(self._window, self._radius + 6, h // 2)


class RoundedTextShell(tk.Frame):
    """Rounded shell for multiline Text."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        radius: int = 12,
        padding: int = 2,
        **text_kwargs,
    ) -> None:
        page_bg = _parent_bg(parent)
        super().__init__(parent, bg=page_bg)
        self._radius = radius
        self._padding = padding

        self._canvas = tk.Canvas(
            self,
            highlightthickness=0,
            borderwidth=0,
            bg=page_bg,
        )
        self._canvas.bind("<Configure>", self._redraw_border)

        self._expand = bool(text_kwargs.pop("expand", False))
        self._compact = bool(text_kwargs.pop("compact", False))
        defaults = dict(
            bg=C["surface_alt"],
            fg=C["text"],
            insertbackground=C["text"],
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=FONT,
            padx=8 if self._compact else 10,
            pady=4 if self._compact else 8,
            wrap="word",
        )
        defaults.update(text_kwargs)
        self.text = tk.Text(self._canvas, **defaults)
        self._window = self._canvas.create_window(
            padding + 2, padding + 2, anchor="nw", window=self.text
        )
        font = tkfont.Font(font=defaults["font"])
        line_count = int(text_kwargs.get("height", 4))
        extra = 8 if self._compact else 12
        self._min_height = line_count * font.metrics("linespace") + padding * 2 + extra
        if self._expand:
            self._canvas.pack(fill="both", expand=True)
        else:
            self.pack_propagate(False)
            self.configure(height=self._min_height)
            self._canvas.pack(fill="x")
            self._canvas.configure(height=self._min_height)

    def _redraw_border(self, event: Optional[tk.Event] = None) -> None:
        w = int(event.width if event else self._canvas.winfo_width() or 200)
        if self._expand:
            h = int(event.height if event else self._canvas.winfo_height() or self._min_height)
            h = max(h, self._min_height)
        else:
            h = self._min_height
        pad = self._padding
        self._canvas.delete("border")
        draw_round_rect(
            self._canvas,
            1,
            1,
            w - 1,
            h - 1,
            self._radius,
            fill=C["surface_alt"],
            outline="#dfe3ea",
            width=1,
            tags="border",
        )
        self._canvas.coords(self._window, pad + 2, pad + 2)
        self._canvas.itemconfigure(self._window, width=max(w - pad * 2 - 4, 40), height=max(h - pad * 2 - 4, 20))
