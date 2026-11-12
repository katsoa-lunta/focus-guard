@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ===================================
echo  FocusGuard 专注守卫 · 网页版
echo ===================================
echo.
where py >nul 2>&1
if %errorlevel%==0 (
    py -3 main_web.py %*
) else (
    python main_web.py %*
)
if errorlevel 1 (
    echo.
    echo 启动失败。请确认已安装 Python 3.9+ 并执行过：
    echo   pip install -r requirements.txt
    echo.
    pause
)
