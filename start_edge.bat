@echo off
setlocal
set "EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" set "EDGE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" (
    echo 未找到 Microsoft Edge，请手动安装 Edge 后重试。
    pause
    exit /b 1
)
set "PROFILE=%~dp0data\edge_profile"
echo 正在启动 Edge（CDP 端口 9222，独立配置目录）...
start "" "%EDGE%" --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir="%PROFILE%" "https://www.zhipin.com/web/user/?ka=header-login"
echo Edge 已启动。请在 GUI 中点击「启动自动求职」。
timeout /t 3 >nul
