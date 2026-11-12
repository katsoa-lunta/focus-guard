@echo off
chcp 65001 >nul
echo ===================================
echo FocusGuard 环境安装
echo ===================================
echo.
echo [1/3] 检查 Python 是否已安装...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo 未检测到 Python，请先安装：
    echo https://www.python.org/downloads/
    echo.
    echo 安装时务必勾选 "Add Python to PATH"！
    echo.
    pause
    exit /b 1
)
python --version
echo.

echo [2/3] 创建虚拟环境...
if not exist venv (
    python -m venv venv
    echo 虚拟环境创建完成
) else (
    echo 虚拟环境已存在，跳过
)
echo.

echo [3/3] 安装依赖...
venv\Scripts\pip install -r requirements.txt
echo.

echo 安装完成！现在可以运行 test_dry.bat 或 start.bat
echo.
pause
