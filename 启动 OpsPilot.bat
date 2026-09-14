@echo off
chcp 65001 >nul
setlocal

rem ============================================================
rem  OpsPilot 一键启动
rem  1) 启动后端 FastAPI (127.0.0.1:8791)
rem  2) 端口就绪后打开桌面端；没装桌面端就用浏览器打开
rem ============================================================

set "ROOT=%~dp0"
set "PY=%ROOT%backend\.venv\Scripts\python.exe"
set "PORT=8791"

if not exist "%PY%" (
    echo [X] 未找到后端环境：%PY%
    echo     请先执行一次：
    echo       cd backend ^&^& py -3 -m venv .venv
    echo       .venv\Scripts\python.exe -m pip install -e ".[sdk,dev]"
    pause
    exit /b 1
)

rem 端口已被占用 = 后端已在跑，直接进前端
netstat -ano | findstr ":%PORT% " | findstr LISTENING >nul
if %errorlevel%==0 (
    echo [=] 后端已在运行 :%PORT%
    goto :open_ui
)

echo [1/2] 正在启动后端 :%PORT% ...
start "OpsPilot Backend" /min "%PY%" -m uvicorn ops_pilot.server.app:app --host 127.0.0.1 --port %PORT%
cd /d "%ROOT%backend"

rem 等端口就绪，最多 30 秒
set /a TRY=0
:wait
set /a TRY+=1
if %TRY% gtr 30 (
    echo [X] 后端启动超时，请查看上一步窗口的报错
    pause
    exit /b 1
)
timeout /t 1 /nobreak >nul
netstat -ano | findstr ":%PORT% " | findstr LISTENING >nul
if not %errorlevel%==0 goto :wait
echo [OK] 后端就绪 :%PORT%

:open_ui
set "EXE=%LOCALAPPDATA%\OpsPilot\opspilot.exe"
if exist "%EXE%" (
    echo [2/2] 启动桌面端 OpsPilot ...
    start "" "%EXE%"
) else (
    echo [2/2] 未找到桌面端，改用浏览器打开 http://127.0.0.1:%PORT%
    start "" "http://127.0.0.1:%PORT%"
)

echo.
echo 用完关闭后端：任务管理器结束 "OpsPilot Backend" 窗口，或关闭本窗口后运行 停止 OpsPilot.bat
endlocal
