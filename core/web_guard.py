"""Web guard: local HTTP/HTTPS proxy that blocks non-whitelisted websites."""
from __future__ import annotations

import atexit
import logging
import re
import select
import socket
import threading
from typing import Callable, Optional, Set

logger = logging.getLogger(__name__)

BLOCKED_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>FocusGuard · 已拦截</title></head>
<body style="font-family:sans-serif;text-align:center;padding:80px 20px;color:#333;">
  <h1>🚫 专注模式已开启</h1>
  <p>该网站不在白名单内，当前无法访问。</p>
  <p>如需访问，请在 FocusGuard 的白名单设置中添加此网站。</p>
</body>
</html>""".encode("utf-8")


class WebProxy:
    """Minimal HTTP/HTTPS proxy with whitelist support."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 17862,
        whitelist: Optional[Set[str]] = None,
        on_blocked: Optional[Callable[[str], None]] = None,
    ):
        self.host = host
        self.port = port
        self.whitelist: Set[str] = set()
        if whitelist:
            self.set_whitelist(whitelist)
        self.on_blocked = on_blocked
        self._running = False
        self._server: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None

    def set_whitelist(self, domains: Set[str]) -> None:
        cleaned = set()
        for d in domains:
            d = d.lower().strip()
            if d.startswith("http://") or d.startswith("https://"):
                d = d.split("//", 1)[1].split("/", 1)[0]
            d = d.split(":", 1)[0]
            if d:
                cleaned.add(d)
        self.whitelist = cleaned

    def is_allowed(self, host: str) -> bool:
        if not self.whitelist:
            return True
        host = host.lower().strip().split(":", 1)[0]
        for allowed in self.whitelist:
            if host == allowed or host.endswith("." + allowed):
                return True
        return False

    def start(self) -> None:
        if self._running:
            return
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._server.bind((self.host, self.port))
        except OSError as e:
            logger.error("Cannot bind proxy to %s:%d: %s", self.host, self.port, e)
            raise
        self._server.listen(100)
        self._running = True
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()
        logger.info("Web proxy started on %s:%d", self.host, self.port)

    def stop(self) -> None:
        self._running = False
        if self._server:
            try:
                self._server.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        logger.info("Web proxy stopped")

    def _accept_loop(self) -> None:
        while self._running:
            try:
                client, _ = self._server.accept()
            except OSError:
                break
            threading.Thread(target=self._handle_client, args=(client,), daemon=True).start()

    def _handle_client(self, client: socket.socket) -> None:
        try:
            client.settimeout(15)
            data = client.recv(4096)
            if not data:
                client.close()
                return

            first_line = data.split(b"\r\n")[0].decode("utf-8", "ignore")
            parts = first_line.split()
            if len(parts) < 2:
                client.close()
                return

            method, target = parts[0].upper(), parts[1]

            if method == "CONNECT":
                host, port = self._parse_host_port(target, 443)
                if self.is_allowed(host):
                    self._tunnel(client, host, port)
                else:
                    self._send_blocked(client, host)
            else:
                host = self._extract_host(data)
                if not host:
                    client.close()
                    return
                if self.is_allowed(host):
                    self._relay_http(client, data, host)
                else:
                    self._send_blocked(client, host)
        except Exception as e:
            logger.debug("Client handling error: %s", e)
        finally:
            try:
                client.close()
            except Exception:
                pass

    @staticmethod
    def _parse_host_port(target: str, default_port: int) -> tuple[str, int]:
        if ":" in target:
            host, port_str = target.rsplit(":", 1)
            try:
                port = int(port_str)
            except ValueError:
                port = default_port
        else:
            host, port = target, default_port
        return host, port

    @staticmethod
    def _extract_host(data: bytes) -> str:
        match = re.search(rb"Host:\s*([^\r\n]+)", data, re.IGNORECASE)
        if match:
            host = match.group(1).decode("utf-8", "ignore").strip()
            return host.split(":", 1)[0]
        return ""

    def _tunnel(self, client: socket.socket, host: str, port: int) -> None:
        try:
            server = socket.create_connection((host, port), timeout=15)
        except Exception:
            client.close()
            return
        try:
            client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        except Exception:
            server.close()
            client.close()
            return
        self._pipe(client, server)

    def _relay_http(self, client: socket.socket, data: bytes, host: str) -> None:
        try:
            server = socket.create_connection((host, 80), timeout=15)
        except Exception:
            client.close()
            return
        try:
            server.sendall(data)
        except Exception:
            server.close()
            client.close()
            return
        self._pipe(client, server)

    def _send_blocked(self, client: socket.socket, host: str) -> None:
        logger.info("Blocked website: %s", host)
        if self.on_blocked:
            try:
                self.on_blocked(host)
            except Exception:
                pass
        headers = (
            "HTTP/1.1 403 Forbidden\r\n"
            "Content-Type: text/html; charset=utf-8\r\n"
            f"Content-Length: {len(BLOCKED_HTML)}\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode("utf-8")
        try:
            client.sendall(headers + BLOCKED_HTML)
        except Exception:
            pass
        client.close()

    @staticmethod
    def _pipe(s1: socket.socket, s2: socket.socket) -> None:
        try:
            while True:
                readable, _, _ = select.select([s1, s2], [], [], 1)
                for s in readable:
                    data = s.recv(8192)
                    if not data:
                        return
                    other = s2 if s is s1 else s1
                    other.sendall(data)
        except Exception:
            pass
        finally:
            try:
                s1.close()
            except Exception:
                pass
            try:
                s2.close()
            except Exception:
                pass


class SystemProxy:
    """Configure Windows system proxy settings.

    The previous settings are backed up on enable() and restored on disable(),
    so other proxy tools (e.g. Steam++) keep working after a focus session.
    """

    REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"

    def __init__(self, host: str = "127.0.0.1", port: int = 17862):
        self.host = host
        self.port = port
        self._backup: Optional[dict] = None

    @staticmethod
    def _read(key, name: str, default=None):
        try:
            import winreg
            return winreg.QueryValueEx(key, name)[0]
        except OSError:
            return default

    def enable(self) -> bool:
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, self.REG_PATH, 0,
                winreg.KEY_READ | winreg.KEY_WRITE,
            )
            if self._backup is None:
                self._backup = {
                    "ProxyEnable": self._read(key, "ProxyEnable", 0),
                    "ProxyServer": self._read(key, "ProxyServer", ""),
                    "ProxyOverride": self._read(key, "ProxyOverride", ""),
                }
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, f"{self.host}:{self.port}")
            winreg.CloseKey(key)
            self._refresh()
            logger.info("System proxy enabled: %s:%d", self.host, self.port)
            return True
        except Exception as e:
            logger.error("Failed to enable system proxy: %s", e)
            return False

    def disable(self) -> bool:
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, self.REG_PATH, 0,
                winreg.KEY_READ | winreg.KEY_WRITE,
            )
            if self._backup:
                winreg.SetValueEx(
                    key, "ProxyEnable", 0, winreg.REG_DWORD,
                    int(self._backup.get("ProxyEnable") or 0),
                )
                winreg.SetValueEx(
                    key, "ProxyServer", 0, winreg.REG_SZ,
                    str(self._backup.get("ProxyServer") or ""),
                )
                winreg.SetValueEx(
                    key, "ProxyOverride", 0, winreg.REG_SZ,
                    str(self._backup.get("ProxyOverride") or ""),
                )
                self._backup = None
            else:
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
            winreg.CloseKey(key)
            self._refresh()
            logger.info("System proxy restored")
            return True
        except Exception as e:
            logger.error("Failed to disable system proxy: %s", e)
            return False

    @staticmethod
    def _refresh() -> None:
        try:
            import ctypes
            INTERNET_OPTION_SETTINGS_CHANGED = 39
            INTERNET_OPTION_REFRESH = 37
            ctypes.windll.wininet.InternetSetOptionW(0, INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)
            ctypes.windll.wininet.InternetSetOptionW(0, INTERNET_OPTION_REFRESH, 0, 0)
        except Exception:
            pass


class WebGuard:
    """High-level web guard combining proxy and system proxy configuration."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 17862,
        whitelist: Optional[Set[str]] = None,
        on_blocked: Optional[Callable[[str], None]] = None,
    ):
        self.proxy = WebProxy(host=host, port=port, whitelist=whitelist, on_blocked=on_blocked)
        self.system = SystemProxy(host=host, port=port)

    def set_whitelist(self, domains: Set[str]) -> None:
        self.proxy.set_whitelist(domains)

    def start(self) -> None:
        self.proxy.start()
        self.system.enable()
        # Safety net: restore the previous system proxy even if the process
        # exits by an unexpected path (crash, forced close, unhandled error).
        atexit.register(self._restore_on_exit)

    def _restore_on_exit(self) -> None:
        try:
            self.system.disable()
        except Exception:
            pass

    def stop(self) -> None:
        self.system.disable()
        self.proxy.stop()
        try:
            atexit.unregister(self._restore_on_exit)
        except Exception:
            pass
