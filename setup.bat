@echo off
setlocal
set "HERE=%~dp0"
cd /d "%HERE%"

echo ========================================
echo   YouTube 下载器 - 依赖安装
echo   yt-dlp: https://github.com/yt-dlp/yt-dlp
echo   ffmpeg: https://ffbinaries.com/downloads
echo   Node.js: https://nodejs.org/en/
echo ========================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo 正在创建虚拟环境...
  python -m venv .venv
  if errorlevel 1 (
    echo [错误] 无法创建虚拟环境，请确认已安装 Python 3.10+
    pause
    exit /b 1
  )
)

echo 正在安装 yt-dlp 和 ffmpeg...
".venv\Scripts\python.exe" "%HERE%install_deps.py"
if errorlevel 1 (
  echo [错误] 依赖安装失败
  pause
  exit /b 1
)

echo.
echo 安装完成。可双击「打开YouTube下载器.bat」启动。
pause
