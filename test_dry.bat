@echo off
chcp 65001 >nul
echo ===================================
echo FocusGuard 安全干跑测试
echo ===================================
echo.
echo 本次测试只会"看看"哪些程序会被拦截，
echo 不会关闭任何程序，也不会修改系统设置。
echo.
if not exist venv (
    echo 请先双击运行 setup.bat 安装环境
    pause
    exit /b 1
)
echo 开始测试...
venv\Scripts\python tests\test_dry.py
pause
