@echo off
setlocal
set "HERE=%~dp0"
cd /d "%HERE%"

if not exist "%HERE%.venv\Scripts\pythonw.exe" (
  if not exist "%HERE%.venv\Scripts\python.exe" (
    echo 首次使用，正在自动安装依赖...
    call "%HERE%setup.bat"
    if errorlevel 1 exit /b 1
  )
)

if not exist "%HERE%.venv\Scripts\python.exe" (
  echo [错误] 未找到虚拟环境，请先运行 setup.bat
  pause
  exit /b 1
)

rem 检查并安装缺失依赖（yt-dlp + ffmpeg）
"%HERE%.venv\Scripts\python.exe" -c "from deps_installer import missing_components; import sys; sys.exit(0 if not missing_components() else 1)" 2>nul
if errorlevel 1 (
  echo 正在自动安装 yt-dlp 和 ffmpeg...
  "%HERE%.venv\Scripts\python.exe" "%HERE%install_deps.py"
)

if exist "%HERE%.venv\Scripts\pythonw.exe" (
  start "YouTubeDownloader" /D "%HERE%" "%HERE%.venv\Scripts\pythonw.exe" "%HERE%main.py"
) else (
  start "YouTubeDownloader" /D "%HERE%" "%HERE%.venv\Scripts\python.exe" "%HERE%main.py"
)
exit /b 0
