@echo off
chcp 65001 >nul 2>&1
setlocal EnableExtensions
set "HERE=%~dp0"
set "ROOT=%HERE%"
set "LAUNCH=%HERE%打开YouTube下载器.bat"
set "ICON=%HERE%assets\icon.ico"

if not exist "%LAUNCH%" (
    echo [错误] 未找到启动脚本: %LAUNCH%
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell; $lnk = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\YouTube 下载器.lnk'); $lnk.TargetPath = '%LAUNCH%'; $lnk.WorkingDirectory = '%ROOT%'; if (Test-Path '%ICON%') { $lnk.IconLocation = '%ICON%,0' }; $lnk.Description = 'YouTube 视频下载器'; $lnk.Save()"

if errorlevel 1 (
    echo [错误] 创建快捷方式失败
    pause
    exit /b 1
)

echo [完成] 已在桌面创建快捷方式: YouTube 下载器.lnk
pause
