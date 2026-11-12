"""Dry-run test for FocusGuard.

This script only *reports* what would be blocked. It does not kill any
processes or change system proxy settings, so it is safe to run.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.process_guard import ProcessGuard


def main():
    print("=" * 60)
    print("FocusGuard 干跑测试（不会关闭任何程序）")
    print("=" * 60)

    # Example whitelist: only these apps would be allowed in real mode.
    whitelist = {
        "explorer.exe",
        "python.exe",
        "focusguard.exe",
    }

    blocked_log = []

    def on_blocked(name: str, pid: int):
        blocked_log.append((name, pid))
        print(f"  [会被拦截] {name} (pid={pid})")

    guard = ProcessGuard(
        whitelist=whitelist,
        dry_run=True,
        on_blocked=on_blocked,
        scan_interval=1.0,
    )

    print(f"\n白名单：{', '.join(sorted(whitelist))}")
    print("10 秒内会扫描当前运行的进程，列出白名单外的程序。\n")

    guard.start()
    try:
        for i in range(10, 0, -1):
            print(f"剩余 {i} 秒...")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n用户中断")
    finally:
        guard.stop()

    print("\n" + "=" * 60)
    print(f"测试结束。共发现 {len(blocked_log)} 个会被拦截的进程。")
    print("=" * 60)


if __name__ == "__main__":
    main()
