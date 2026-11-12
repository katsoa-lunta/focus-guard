"""Entry point for the FocusGuard web UI.

Starts a local HTTP server, then opens a chromeless app window (Edge/Chrome
``--app`` mode) so it feels like a desktop application. Falls back to the
default browser when neither is installed.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webui.controller import FocusController  # noqa: E402
from webui.server import DEFAULT_PORT, serve  # noqa: E402

BROWSER_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def _find_browser() -> str | None:
    for path in BROWSER_CANDIDATES:
        if Path(path).is_file():
            return path
    for name in ("msedge", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None


def open_window(url: str) -> None:
    """Open the UI in a borderless app window when possible."""
    browser = _find_browser()
    try:
        if browser:
            subprocess.Popen(
                [browser, f"--app={url}", "--window-size=1200,840"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
    except Exception:
        pass
    try:
        import webbrowser

        webbrowser.open(url)
    except Exception:
        print(f"请手动在浏览器打开：{url}")


def main() -> int:
    parser = argparse.ArgumentParser(description="FocusGuard 网页版")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，局域网访问可用 0.0.0.0")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="服务端口（默认 7788）")
    parser.add_argument("--no-browser", action="store_true", help="只启动服务，不自动开窗口")
    args = parser.parse_args()

    controller = FocusController()
    ready = threading.Event()
    holder: dict = {}

    def run_server() -> None:
        serve(controller, host=args.host, port=args.port, ready=ready, holder=holder)

    server_thread = threading.Thread(target=run_server, name="http", daemon=True)
    server_thread.start()
    ready.wait(timeout=15)
    port = holder.get("port", args.port)
    url = f"http://{args.host}:{port}/"

    print("=" * 52)
    print("  FocusGuard 专注守卫 · 网页版")
    print("=" * 52)
    print(f"  界面地址：{url}")
    print("  快捷键：空格 开始/暂停   Esc 结束")
    print("  关闭本窗口即退出（系统代理会自动还原）")
    print("=" * 52)

    if not args.no_browser:
        threading.Timer(0.5, open_window, args=(url,)).start()

    try:
        while server_thread.is_alive():
            time.sleep(0.4)
    except KeyboardInterrupt:
        print("\n正在退出…")
    finally:
        controller.shutdown()
        print("已退出，系统代理已还原。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
