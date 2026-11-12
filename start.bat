@echo off
chcp 65001 >nul
echo ===================================
echo 启动 FocusGuard
echo ===================================
echo.
if not exist venv (
    echo 请先双击运行 setup.bat 安装环境
    pause
    exit /b 1
)
echo 正在启动 FocusGuard...
echo 建议右键本文件，选择"以管理员身份运行"
echo.
venv\Scripts\python main.py
pause
