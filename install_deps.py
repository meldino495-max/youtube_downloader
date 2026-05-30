from __future__ import annotations

import sys

from deps_installer import ensure_dependencies, missing_components, optional_components
from paths_config import InstallPaths


def _print(msg: str) -> None:
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
            sys.stdout.encoding or "utf-8", errors="replace"
        ))


def main() -> int:
    paths = InstallPaths.from_config()
    missing = missing_components(paths)
    optional = optional_components(paths)
    if not missing and not optional:
        _print("依赖已就绪: yt-dlp, ffmpeg, Node.js")
        return 0

    if missing:
        _print("缺少: " + ", ".join(missing))
    if optional:
        _print("建议安装: " + ", ".join(optional))
    _print("开始自动安装…")

    def log(msg: str) -> None:
        _print(msg)

    ensure_dependencies(
        install_ytdlp="yt-dlp" in missing,
        install_ffmpeg_tool="ffmpeg" in missing,
        install_node=bool(optional),
        log=log,
        paths=paths,
    )
    _print("安装完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
