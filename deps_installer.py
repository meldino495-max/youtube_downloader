from __future__ import annotations

import platform
import shutil
import subprocess
import sys
import json
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional

from paths_config import (
    APP_DIR,
    InstallPaths,
    find_ffmpeg_exe,
    find_node_exe,
    ytdlp_is_ready,
)

ProgressCallback = Callable[[str], None]
PercentCallback = Callable[[float, str], None]

TOOLS_DIR = APP_DIR / "tools"
VENV_DIR = APP_DIR / ".venv"

YTDLP_GITHUB_URL = "https://github.com/yt-dlp/yt-dlp"
YTDLP_EXE_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
YTDLP_PIP_PACKAGE = "yt-dlp>=2025.1.0"
YTDLP_GITHUB_ZIP = "https://github.com/yt-dlp/yt-dlp/archive/master.zip"

NODEJS_INDEX_URL = "https://nodejs.org/dist/index.json"
NODEJS_HOMEPAGE = "https://nodejs.org/en/"
NODEJS_FALLBACK_VERSION = "v24.16.0"

FFBINARIES_URL = "https://ffbinaries.com/downloads"
FFMPEG_VERSION = "6.1"
FFBINARIES_BASE = (
    "https://github.com/ffbinaries/ffbinaries-prebuilt/releases/download"
)
FFMPEG_WIN64_URL = (
    f"{FFBINARIES_BASE}/v{FFMPEG_VERSION}/ffmpeg-{FFMPEG_VERSION}-win-64.zip"
)
FFPROBE_WIN64_URL = (
    f"{FFBINARIES_BASE}/v{FFMPEG_VERSION}/ffprobe-{FFMPEG_VERSION}-win-64.zip"
)

SOURCE_URLS = {
    "yt-dlp": YTDLP_GITHUB_URL,
    "ffmpeg": FFBINARIES_URL,
    "node.js": NODEJS_HOMEPAGE,
}


def venv_python() -> Optional[Path]:
    if sys.platform == "win32":
        candidate = VENV_DIR / "Scripts" / "python.exe"
    else:
        candidate = VENV_DIR / "bin" / "python"
    return candidate if candidate.is_file() else None


def ensure_venv(log: ProgressCallback) -> Path:
    py = venv_python()
    if py:
        return py
    log("正在创建 Python 虚拟环境…")
    subprocess.run(
        [sys.executable, "-m", "venv", str(VENV_DIR)],
        check=True,
        cwd=APP_DIR,
    )
    py = venv_python()
    if not py:
        raise RuntimeError("虚拟环境创建失败")
    log(f"虚拟环境: {py}")
    return py


def _download(
    url: str,
    dest: Path,
    *,
    log: ProgressCallback,
    percent: Optional[PercentCallback] = None,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    log(f"下载: {url}")

    def report(block_num: int, block_size: int, total_size: int) -> None:
        if not percent or total_size <= 0:
            return
        done = block_num * block_size
        pct = min(99.0, done * 100.0 / total_size)
        mb = total_size / (1024 * 1024)
        percent(pct, f"下载中 {pct:.0f}% ({mb:.1f} MB)")

    urllib.request.urlretrieve(url, dest, reporthook=report)
    if percent:
        percent(100.0, "下载完成")
    log(f"已保存: {dest}")


def _extract_exe_from_zip(zip_path: Path, dest_dir: Path, exe_name: str) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            name = Path(info.filename).name
            if name.lower() == exe_name.lower():
                target = dest_dir / name
                with zf.open(info) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
                return target
    raise FileNotFoundError(f"在 {zip_path.name} 中未找到 {exe_name}")


def has_js_runtime(paths: Optional[InstallPaths] = None) -> bool:
    if find_node_exe(paths):
        return True
    return bool(shutil.which("deno") or shutil.which("bun"))


def fetch_node_lts_version(log: Optional[ProgressCallback] = None) -> str:
    try:
        with urllib.request.urlopen(NODEJS_INDEX_URL, timeout=30) as resp:
            releases = json.loads(resp.read())
        for release in releases:
            if release.get("lts"):
                version = release["version"]
                if log:
                    log(f"Node.js 最新 LTS: {version}")
                return version
    except Exception as exc:
        if log:
            log(f"获取 Node.js 版本失败，使用备用版本: {exc}")
    return NODEJS_FALLBACK_VERSION


def install_nodejs(
    log: ProgressCallback,
    percent: Optional[PercentCallback] = None,
    *,
    paths: Optional[InstallPaths] = None,
) -> Path:
    if sys.platform != "win32":
        raise RuntimeError("当前自动安装 Node.js 仅支持 Windows。请访问 nodejs.org 手动安装。")

    install_paths = paths or InstallPaths.from_config()
    node_dir = install_paths.nodejs_dir
    node_dir.mkdir(parents=True, exist_ok=True)

    machine = platform.machine().lower()
    if machine in ("amd64", "x86_64"):
        arch = "x64"
    elif machine == "arm64":
        arch = "arm64"
    else:
        raise RuntimeError(f"不支持的 CPU 架构: {machine}")

    node_exe = node_dir / "node.exe"
    if node_exe.is_file():
        log(f"Node.js 已存在，跳过下载: {node_exe}")
        return node_exe

    version = fetch_node_lts_version(log)
    zip_name = f"node-{version}-win-{arch}.zip"
    url = f"https://nodejs.org/dist/{version}/{zip_name}"
    log(f"正在从 nodejs.org 下载 Node.js …")
    log(f"来源: {NODEJS_HOMEPAGE}")
    log(f"安装目录: {node_dir}")

    cache = TOOLS_DIR / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    zip_path = cache / zip_name

    _download(url, zip_path, log=log, percent=percent)
    with zipfile.ZipFile(zip_path, "r") as zf:
        node_entries = [i for i in zf.infolist() if i.filename.endswith("node.exe")]
        if not node_entries:
            raise FileNotFoundError(f"在 {zip_name} 中未找到 node.exe")
        with zf.open(node_entries[0]) as src, open(node_exe, "wb") as out:
            shutil.copyfileobj(src, out)

    result = subprocess.run(
        [str(node_exe), "--version"],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    ver = (result.stdout or result.stderr or "").strip()
    log(f"Node.js 已安装: {ver}")
    log(f"路径: {node_exe}")
    return node_exe


def install_ffmpeg(
    log: ProgressCallback,
    percent: Optional[PercentCallback] = None,
    *,
    paths: Optional[InstallPaths] = None,
) -> Path:
    if sys.platform != "win32":
        raise RuntimeError("当前自动安装 ffmpeg 仅支持 Windows。请手动安装 ffmpeg。")

    install_paths = paths or InstallPaths.from_config()
    ffmpeg_dir = install_paths.ffmpeg_dir
    ffmpeg_dir.mkdir(parents=True, exist_ok=True)

    machine = platform.machine().lower()
    if machine not in ("amd64", "x86_64", "arm64"):
        raise RuntimeError(f"不支持的 CPU 架构: {machine}")

    cache = TOOLS_DIR / "cache"
    cache.mkdir(parents=True, exist_ok=True)

    ffmpeg_exe = ffmpeg_dir / "ffmpeg.exe"
    ffprobe_exe = ffmpeg_dir / "ffprobe.exe"

    if ffmpeg_exe.is_file() and ffprobe_exe.is_file():
        log(f"ffmpeg 已存在，跳过下载: {ffmpeg_dir}")
        return ffmpeg_exe

    log(f"安装目录: {ffmpeg_dir}")
    ffmpeg_zip = cache / f"ffmpeg-{FFMPEG_VERSION}-win-64.zip"
    ffprobe_zip = cache / f"ffprobe-{FFMPEG_VERSION}-win-64.zip"

    if not ffmpeg_exe.is_file():
        log(f"正在从 ffbinaries 下载 ffmpeg …")
        log(f"来源: {FFBINARIES_URL}")
        _download(FFMPEG_WIN64_URL, ffmpeg_zip, log=log, percent=percent)
        _extract_exe_from_zip(ffmpeg_zip, ffmpeg_dir, "ffmpeg.exe")
        log(f"ffmpeg 安装到: {ffmpeg_exe}")

    if not ffprobe_exe.is_file():
        log("正在下载 ffprobe …")
        _download(FFPROBE_WIN64_URL, ffprobe_zip, log=log, percent=percent)
        _extract_exe_from_zip(ffprobe_zip, ffmpeg_dir, "ffprobe.exe")
        log(f"ffprobe 安装到: {ffprobe_exe}")

    if not ffmpeg_exe.is_file():
        raise RuntimeError("ffmpeg 安装失败")
    return ffmpeg_exe


def install_yt_dlp_pip(
    log: ProgressCallback,
    *,
    paths: Optional[InstallPaths] = None,
) -> str:
    install_paths = paths or InstallPaths.from_config()
    target_dir = install_paths.ytdlp_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    py = ensure_venv(log)
    log("正在安装 yt-dlp …")
    log(f"来源: {YTDLP_GITHUB_URL}")
    log(f"安装目录: {target_dir}")

    subprocess.run(
        [str(py), "-m", "pip", "install", "-U", "pip"],
        check=True,
        cwd=APP_DIR,
        capture_output=True,
        text=True,
    )

    pip_cmd = [
        str(py),
        "-m",
        "pip",
        "install",
        "-U",
        "--target",
        str(target_dir),
        YTDLP_PIP_PACKAGE,
    ]
    try:
        result = subprocess.run(
            pip_cmd,
            check=True,
            cwd=APP_DIR,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        log("PyPI 安装失败，尝试从 GitHub 直接安装 …")
        pip_cmd[-1] = YTDLP_GITHUB_ZIP
        result = subprocess.run(
            pip_cmd,
            check=True,
            cwd=APP_DIR,
            capture_output=True,
            text=True,
        )
    if result.stdout:
        for line in result.stdout.strip().splitlines()[-3:]:
            log(line)

    sys.path.insert(0, str(target_dir))
    import yt_dlp

    ver = yt_dlp.version.__version__
    log(f"yt-dlp 已安装: {ver}")
    return ver


def download_yt_dlp_exe(
    log: ProgressCallback,
    percent: Optional[PercentCallback] = None,
    *,
    paths: Optional[InstallPaths] = None,
) -> Path:
    install_paths = paths or InstallPaths.from_config()
    dest_dir = install_paths.ytdlp_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "yt-dlp.exe"
    if dest.is_file():
        log(f"yt-dlp.exe 已存在: {dest}")
        return dest
    log(f"安装目录: {dest_dir}")
    _download(YTDLP_EXE_URL, dest, log=log, percent=percent)
    log(f"yt-dlp.exe 已下载: {dest}")
    return dest


def install_yt_dlp(
    log: ProgressCallback,
    percent: Optional[PercentCallback] = None,
    *,
    paths: Optional[InstallPaths] = None,
) -> str:
    try:
        return install_yt_dlp_pip(log, paths=paths)
    except Exception as pip_err:
        log(f"pip 安装失败: {pip_err}")
        log("尝试从 GitHub 下载 yt-dlp.exe …")
        log(f"来源: {YTDLP_EXE_URL}")
        download_yt_dlp_exe(log, percent, paths=paths)
        raise RuntimeError(
            "已下载 yt-dlp.exe，但本程序需要 Python 模块。"
            "请检查网络后重试，或更换安装目录。"
        ) from pip_err


def ensure_dependencies(
    *,
    install_ytdlp: bool = True,
    install_ffmpeg_tool: bool = True,
    install_node: bool = False,
    log: ProgressCallback,
    percent: Optional[PercentCallback] = None,
    paths: Optional[InstallPaths] = None,
) -> dict[str, str]:
    install_paths = paths or InstallPaths.from_config()
    results: dict[str, str] = {}

    if install_ytdlp:
        if ytdlp_is_ready(install_paths):
            from paths_config import ensure_ytdlp_on_path

            ensure_ytdlp_on_path(install_paths)
            import yt_dlp

            results["yt-dlp"] = yt_dlp.version.__version__
            log(f"yt-dlp 已就绪: {results['yt-dlp']} ({install_paths.ytdlp_dir})")
        else:
            results["yt-dlp"] = install_yt_dlp(log, percent, paths=install_paths)

    if install_ffmpeg_tool:
        existing = find_ffmpeg_exe(install_paths)
        if existing:
            results["ffmpeg"] = str(existing)
            log(f"ffmpeg 已就绪: {existing}")
        else:
            exe = install_ffmpeg(log, percent, paths=install_paths)
            results["ffmpeg"] = str(exe)

    if install_node:
        existing = find_node_exe(install_paths)
        if existing:
            results["node.js"] = str(existing)
            log(f"Node.js 已就绪: {existing}")
        else:
            exe = install_nodejs(log, percent, paths=install_paths)
            results["node.js"] = str(exe)

    return results


def missing_components(paths: Optional[InstallPaths] = None) -> list[str]:
    install_paths = paths or InstallPaths.from_config()
    missing: list[str] = []
    if not ytdlp_is_ready(install_paths):
        missing.append("yt-dlp")
    if not find_ffmpeg_exe(install_paths):
        missing.append("ffmpeg")
    return missing


def optional_components(paths: Optional[InstallPaths] = None) -> list[str]:
    if not has_js_runtime(paths):
        return ["Node.js"]
    return []
