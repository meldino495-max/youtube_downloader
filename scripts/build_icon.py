"""Generate Windows-friendly multi-size icon.ico for PyInstaller."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "youtube_downloader_icon_2.png"
ASSETS = ROOT / "assets"
ICON_ICO = ASSETS / "icon.ico"
ICON_PNG = ASSETS / "icon.png"


def build_icon() -> None:
    ASSETS.mkdir(exist_ok=True)
    src = Image.open(SOURCE).convert("RGBA")
    base = Image.new("RGB", src.size, (255, 255, 255))
    base.paste(src, mask=src.split()[3])
    base.save(ICON_PNG)

    sizes = [16, 32, 48, 256]
    images = [
        base.resize((size, size), Image.Resampling.LANCZOS).convert("RGB")
        for size in sizes
    ]
    images[-1].save(
        ICON_ICO,
        format="ICO",
        sizes=[(img.width, img.height) for img in images],
        append_images=images[:-1],
    )


if __name__ == "__main__":
    build_icon()
    print(f"Wrote {ICON_ICO}")
