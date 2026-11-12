@echo off
chcp 65001 >nul
echo ===================================
echo 恢复系统代理设置
echo ===================================
echo.
echo 如果运行 FocusGuard 后浏览器无法上网，请运行此文件。
echo.
if not exist venv (
    echo 请先双击运行 setup.bat 安装环境
    pause
    exit /b 1
)
venv\Scripts\python tests\reset_proxy.py
echo.
echo 已恢复，如果仍无法上网，请检查：
echo Windows 设置 - 网络和 Internet - 代理 - 关闭"使用代理服务器"
pause
