"""Emergency script to disable Windows system proxy.

Run this if FocusGuard crashes and leaves the system proxy enabled,
which can cause browser/network issues.
"""
from __future__ import annotations

import ctypes
import sys


def disable_system_proxy():
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE)
        winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
        winreg.CloseKey(key)

        INTERNET_OPTION_SETTINGS_CHANGED = 39
        INTERNET_OPTION_REFRESH = 37
        ctypes.windll.wininet.InternetSetOptionW(0, INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)
        ctypes.windll.wininet.InternetSetOptionW(0, INTERNET_OPTION_REFRESH, 0, 0)
        print("系统代理已关闭。")
    except Exception as e:
        print(f"关闭系统代理失败：{e}")
        sys.exit(1)


if __name__ == "__main__":
    disable_system_proxy()
