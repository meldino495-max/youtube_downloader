"""UI theme constants matching the modern YouTube Downloader mockup."""

COLORS = {
    "bg": "#f3f4f6",
    "sidebar": "#ffffff",
    "surface": "#ffffff",
    "surface_alt": "#fafafa",
    "accent": "#ff0000",
    "accent_dark": "#cc0000",
    "accent_soft": "#ffe5e5",
    "text": "#111827",
    "text_secondary": "#6b7280",
    "border": "#e5e7eb",
    "success": "#16a34a",
    "warning": "#f59e0b",
    "shadow": "rgba(0,0,0,0.08)",
}

QUALITY_OPTIONS = [
    ("2160", "4K", "2160p"),
    ("1440", "2K", "1440p"),
    ("1080", "1080p", "Full HD"),
    ("720", "720p", "HD"),
    ("480", "480p", "SD"),
    ("360", "360p", "SD"),
    ("240", "240p", "Low"),
]

FORMAT_OPTIONS = [
    ("mp4", "MP4 (Video)"),
    ("audio", "MP3 (Audio)"),
]
