"""Application window icon helpers."""

from __future__ import annotations

import tkinter as tk

from paths_config import get_resource_dir

_RESOURCE_DIR = get_resource_dir()
ICON_ICO = _RESOURCE_DIR / "assets" / "icon.ico"
ICON_PNG = _RESOURCE_DIR / "assets" / "icon.png"


def apply_window_icon(window: tk.Tk | tk.Toplevel) -> None:
    try:
        if ICON_ICO.is_file():
            window.iconbitmap(str(ICON_ICO))
            return
        if ICON_PNG.is_file():
            image = tk.PhotoImage(file=str(ICON_PNG))
            window.iconphoto(True, image)
            window._app_icon_ref = image  # type: ignore[attr-defined]
    except Exception:
        pass
