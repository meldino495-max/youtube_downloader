"""Tkinter styling helpers — modern YouTube Downloader look on classic layout."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from rounded_widgets import (
    RoundedButton,
    RoundedCard,
    RoundedComboboxShell,
    RoundedField,
    RoundedTextShell,
)
from ui_theme import COLORS

C = COLORS
FONT = ("Microsoft YaHei UI", 10)
FONT_BOLD = ("Microsoft YaHei UI", 10, "bold")
FONT_TITLE = ("Microsoft YaHei UI", 11)
FONT_HEADER = ("Microsoft YaHei UI", 14, "bold")


def apply_theme(root: tk.Tk) -> ttk.Style:
    root.configure(bg=C["bg"])
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure(".", background=C["bg"], foreground=C["text"], font=FONT)
    style.configure("TFrame", background=C["bg"])
    style.configure("Card.TFrame", background=C["surface"])
    style.configure("TLabel", background=C["bg"], foreground=C["text"], font=FONT)
    style.configure("Card.TLabel", background=C["surface"], foreground=C["text"], font=FONT)
    style.configure("Muted.TLabel", background=C["bg"], foreground=C["text_secondary"], font=FONT)
    style.configure("CardMuted.TLabel", background=C["surface"], foreground=C["text_secondary"], font=FONT)
    style.configure("Header.TLabel", background=C["bg"], foreground=C["text"], font=FONT_HEADER)

    style.configure(
        "Flat.TCombobox",
        fieldbackground=C["surface"],
        background=C["surface"],
        foreground=C["text"],
        borderwidth=0,
        relief="flat",
        arrowsize=14,
        padding=(4, 6),
    )
    style.map(
        "Flat.TCombobox",
        fieldbackground=[("readonly", C["surface"])],
        background=[("readonly", C["surface"])],
    )

    style.configure(
        "TCheckbutton",
        background=C["bg"],
        foreground=C["text"],
        font=FONT,
    )
    style.map("TCheckbutton", background=[("active", C["bg"])])
    style.configure(
        "Card.TCheckbutton",
        background=C["surface"],
        foreground=C["text"],
        font=FONT,
    )
    style.map("Card.TCheckbutton", background=[("active", C["surface"])])

    style.configure(
        "Modern.Horizontal.TProgressbar",
        troughcolor=C["surface_alt"],
        background=C["accent"],
        borderwidth=0,
        lightcolor=C["accent"],
        darkcolor=C["accent"],
        thickness=10,
    )
    return style


def folder_picker_button(parent, text: str, command: Callable, **kwargs) -> tk.Button:
    """Native tk button for folder dialogs (reliable with pythonw on Windows)."""
    return tk.Button(
        parent,
        text=text,
        command=command,
        bg=C["accent_soft"],
        fg=C["accent_dark"],
        activebackground="#ffd6d6",
        activeforeground=C["accent_dark"],
        font=FONT_BOLD,
        relief="flat",
        padx=14,
        pady=7,
        cursor="hand2",
        highlightthickness=0,
        **kwargs,
    )


def primary_button(parent, text: str, command: Callable, **kwargs) -> RoundedButton:
    return RoundedButton(parent, text, command, variant="primary", **kwargs)


def ghost_button(parent, text: str, command: Callable, **kwargs) -> RoundedButton:
    return RoundedButton(parent, text, command, variant="ghost", **kwargs)


def accent_button(parent, text: str, command: Callable, **kwargs) -> RoundedButton:
    return RoundedButton(parent, text, command, variant="accent", **kwargs)


def danger_ghost_button(parent, text: str, command: Callable, **kwargs) -> RoundedButton:
    return RoundedButton(parent, text, command, variant="danger", **kwargs)


def compact_button(parent, text: str, command: Callable, **kwargs) -> RoundedButton:
    return RoundedButton(parent, text, command, variant="compact", **kwargs)


def card_frame(
    parent,
    text: str = "",
    padding: int = 12,
    *,
    expand_vertical: bool = False,
) -> RoundedCard:
    return RoundedCard(
        parent,
        title=text,
        padding=padding,
        expand_vertical=expand_vertical,
    )


def path_entry(parent, textvariable: tk.Variable, **kwargs) -> tk.Entry:
    """Reliable full-width path input (used for save location)."""
    defaults = dict(
        textvariable=textvariable,
        bg=C["surface_alt"],
        fg=C["text"],
        insertbackground=C["text"],
        relief="flat",
        font=FONT,
        highlightthickness=1,
        highlightbackground="#dfe3ea",
        highlightcolor=C["accent"],
    )
    defaults.update(kwargs)
    return tk.Entry(parent, **defaults)


def rounded_entry(parent, textvariable: tk.Variable, **kwargs) -> RoundedField:
    return RoundedField(parent, textvariable, **kwargs)


def rounded_combobox(parent, **kwargs) -> ttk.Combobox:
    shell = RoundedComboboxShell(parent)
    shell.pack(fill="both", expand=True)
    combo = ttk.Combobox(shell.inner, style="Flat.TCombobox", **kwargs)
    combo.pack(fill="both", expand=True, padx=2, pady=2)
    shell.combo = combo  # type: ignore[attr-defined]
    return combo


def styled_text(parent, *, expand: bool = False, compact: bool = False, **kwargs) -> tk.Text:
    kwargs_with_flags = dict(kwargs)
    if expand:
        kwargs_with_flags["expand"] = True
    if compact:
        kwargs_with_flags["compact"] = True
    shell = RoundedTextShell(parent, **kwargs_with_flags)
    if expand:
        shell.pack(fill="both", expand=True, padx=2, pady=2)
    else:
        shell.pack(fill="x", padx=2, pady=(0, 2))
    return shell.text
