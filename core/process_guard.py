"""Process guard: close non-whitelisted applications during focus."""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
from typing import Callable, Optional, Set

logger = logging.getLogger(__name__)

# System-critical processes that must never be terminated.
CRITICAL_PROCESSES = {
    "csrss.exe",
    "wininit.exe",
    "winlogon.exe",
    "services.exe",
    "lsass.exe",
    "smss.exe",
    "svchost.exe",
    "fontdrvhost.exe",
    "dwm.exe",
    "registry.exe",
    "system",
    "system idle process",
    "taskmgr.exe",
    "conhost.exe",
    "powershell.exe",
    "cmd.exe",
    "explorer.exe",
    # Windows shell / service host components. Terminating these destabilises
    # the desktop (input, start menu, memory compression) without helping focus.
    "ctfmon.exe",
    "textinputhost.exe",
    "sihost.exe",
    "dllhost.exe",
    "taskhostw.exe",
    "runtimebroker.exe",
    "searchhost.exe",
    "searchapp.exe",
    "startmenuexperiencehost.exe",
    "shellexperiencehost.exe",
    "wmiprvse.exe",
    "spoolsv.exe",
    "audiodg.exe",
    "memcompression",
    "securityhealthservice.exe",
    "msmpeng.exe",
    "nissrv.exe",
}


def _get_self_name() -> str:
    return sys.executable.lower().split("\\")[-1]


def _windowed_pids() -> set[int]:
    """PIDs that own a visible top-level window (Windows only).

    Only these can actually distract the user. Background services, drivers and
    command-line helpers are deliberately left alone: terminating them can break
    input devices, audio or the desktop while doing nothing for focus.
    """
    if os.name != "nt":
        return set()
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        pids: set[int] = set()

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def _callback(hwnd, _lparam):
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True
                if user32.GetWindowTextLengthW(hwnd) == 0:
                    return True
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value:
                    pids.add(int(pid.value))
            except Exception:
                pass
            return True

        user32.EnumWindows(_callback, 0)
        return pids
    except Exception:
        # If the enumeration fails, fall back to scanning by name only.
        return set()


class ProcessGuard:
    """Monitors running processes and terminates non-whitelisted ones."""

    def __init__(
        self,
        whitelist: Optional[Set[str]] = None,
        protected: Optional[Set[str]] = None,
        on_blocked: Optional[Callable[[str, int], None]] = None,
        scan_interval: float = 1.5,
        dry_run: bool = False,
        only_windowed: bool = True,
    ):
        self.whitelist: Set[str] = set(x.lower() for x in (whitelist or []))
        self.protected: Set[str] = set(x.lower() for x in (protected or [])) | CRITICAL_PROCESSES
        self.protected.add(_get_self_name())
        self._self_pid = os.getpid()
        self._parent_pid = os.getppid()
        self.on_blocked = on_blocked
        self.scan_interval = scan_interval
        self.dry_run = dry_run
        self.only_windowed = only_windowed
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def set_whitelist(self, apps: Set[str]) -> None:
        self.whitelist = set(x.lower() for x in apps)
        self.protected.add(_get_self_name())

    def is_allowed(self, name: str) -> bool:
        if not name:
            return True
        pname = name.lower()
        if pname in self.protected:
            return True
        if pname in self.whitelist:
            return True
        return False

    def scan_blockable(self) -> list[tuple[str, int]]:
        """Return the (name, pid) pairs that a focus session would terminate now."""
        try:
            import psutil
        except ImportError:
            return []
        if not self.whitelist:
            return []
        windowed = _windowed_pids() if self.only_windowed else set()
        found: dict[str, int] = {}
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = proc.info["name"]
                pid = proc.info["pid"]
                if not name or pid in (self._self_pid, self._parent_pid):
                    continue
                if self.only_windowed and pid not in windowed:
                    continue
                if self.is_allowed(name):
                    continue
                found.setdefault(name.lower(), pid)
            except Exception:
                continue
        return sorted(found.items())

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        try:
            import psutil
        except ImportError:
            logger.error("psutil is required for app blocking")
            return

        while not self._stop_event.is_set():
            self._scan_once(psutil)
            self._stop_event.wait(self.scan_interval)

    def _scan_once(self, psutil) -> None:
        # An empty whitelist means "do not block anything" (matches the UI hint),
        # otherwise every running application would be terminated.
        if not self.whitelist:
            return
        windowed = _windowed_pids() if self.only_windowed else set()
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = proc.info["name"]
                pid = proc.info["pid"]
                if not name:
                    continue
                if pid in (self._self_pid, self._parent_pid):
                    continue
                if self.only_windowed and pid not in windowed:
                    continue
                pname = name.lower()
                if pname in self.protected:
                    continue
                if pname in self.whitelist:
                    continue
                self._terminate(proc, pname, pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            except Exception as e:
                logger.debug("Error scanning process: %s", e)

    def _terminate(self, proc, name: str, pid: int) -> None:
        if self.dry_run:
            logger.info("[DRY-RUN] Would block process: %s (pid=%d)", name, pid)
            if self.on_blocked:
                try:
                    self.on_blocked(name, pid)
                except Exception:
                    pass
            return
        try:
            proc.terminate()
            logger.info("Blocked process: %s (pid=%d)", name, pid)
            if self.on_blocked:
                try:
                    self.on_blocked(name, pid)
                except Exception:
                    pass
        except psutil.NoSuchProcess:
            pass
        except psutil.AccessDenied:
            logger.debug("Access denied terminating %s", name)
        except Exception as e:
            logger.debug("Failed to terminate %s: %s", name, e)
