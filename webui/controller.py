"""UI-agnostic focus session controller.

All focus logic lives here so that any front end (local web UI, future tray app)
can drive it through a plain dict snapshot instead of touching GUI widgets.
"""
from __future__ import annotations

import threading
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional

from core.config import ConfigManager, Session
from core.process_guard import ProcessGuard
from core.timer import FocusTimer, TimerState, TimerTick
from core.web_guard import WebGuard

MAX_EVENTS = 40


class FocusController:
    """Owns the timer plus both guards and exposes thread-safe snapshots."""

    def __init__(self) -> None:
        self.config_manager = ConfigManager()
        self.timer = FocusTimer(self.config_manager.config.focus_duration)
        self._lock = threading.RLock()
        self._process_guard: Optional[ProcessGuard] = None
        self._web_guard: Optional[WebGuard] = None
        self._blocked_apps = 0
        self._blocked_websites = 0
        self._events: Deque[Dict[str, str]] = deque(maxlen=MAX_EVENTS)
        self._tick: TimerTick = self.timer.get_tick()
        self.timer.register_tick(self._on_tick)
        self.timer.register_finish(self._on_finish)

    # ---------------------------------------------------------------- helpers
    def _now(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _event(self, kind: str, text: str) -> None:
        self._events.appendleft({"time": self._now(), "kind": kind, "text": text})

    @property
    def config(self):
        return self.config_manager.config

    def _stats(self) -> Dict[str, Any]:
        sessions = self.config.sessions
        return {
            "sessions": len(sessions),
            "completed": sum(1 for s in sessions if s.get("completed")),
            "total_minutes": sum(s.get("duration_minutes", 0) for s in sessions),
            "blocked_apps": sum(s.get("blocked_apps", 0) for s in sessions),
            "blocked_websites": sum(s.get("blocked_websites", 0) for s in sessions),
        }

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            tick = self._tick
            cfg = self.config
            return {
                "state": tick.state.value,
                "remaining_seconds": tick.remaining_seconds,
                "total_seconds": tick.total_seconds,
                "blocked_apps": self._blocked_apps,
                "blocked_websites": self._blocked_websites,
                "events": list(self._events),
                "stats": self._stats(),
                "web_guard_active": self._web_guard is not None,
                "config": {
                    "focus_duration": cfg.focus_duration,
                    "strict_mode": cfg.strict_mode,
                    "whitelist_apps": list(cfg.whitelist_apps),
                    "whitelist_websites": list(cfg.whitelist_websites),
                    "proxy_port": cfg.proxy_port,
                },
            }

    # ------------------------------------------------------------ timer hooks
    def _on_tick(self, tick: TimerTick) -> None:
        with self._lock:
            self._tick = tick

    def _on_app_blocked(self, name: str, pid: int) -> None:
        with self._lock:
            self._blocked_apps += 1
            self._event("app", f"已关闭 {name}")

    def _on_web_blocked(self, host: str) -> None:
        with self._lock:
            self._blocked_websites += 1
            self._event("web", f"已拦截 {host}")

    def _on_finish(self) -> None:
        self._stop_guards(save_session=True, completed=True)
        with self._lock:
            self._event("info", "专注结束，休息一下吧")

    # ------------------------------------------------------------- operations
    def start(self, minutes: Optional[int] = None) -> Dict[str, Any]:
        with self._lock:
            cfg = self.config
            if self._tick.state == TimerState.RUNNING:
                return self.snapshot()

            if minutes:
                try:
                    value = int(minutes)
                except (TypeError, ValueError):
                    raise ValueError("专注时长必须是数字")
                if value <= 0:
                    raise ValueError("专注时长必须大于 0")
                cfg.focus_duration = value
                self.config_manager.save()

            self.timer.set_duration(cfg.focus_duration)
            self._blocked_apps = 0
            self._blocked_websites = 0

            self._process_guard = ProcessGuard(
                whitelist=set(cfg.whitelist_apps),
                protected=set(cfg.protected_apps),
                on_blocked=self._on_app_blocked,
            )
            self._process_guard.start()

            self._web_guard = WebGuard(
                host=cfg.proxy_host,
                port=cfg.proxy_port,
                whitelist=set(cfg.whitelist_websites),
                on_blocked=self._on_web_blocked,
            )
            try:
                self._web_guard.start()
                self._event("info", f"网页白名单已生效（端口 {cfg.proxy_port}）")
            except OSError as exc:
                self._web_guard = None
                self._event("error", f"网页拦截启动失败：{exc}")

            self.timer.start()
            self._event("info", f"开始专注 {cfg.focus_duration} 分钟")
            return self.snapshot()

    def pause(self) -> Dict[str, Any]:
        with self._lock:
            if self._tick.state != TimerState.RUNNING:
                return self.snapshot()
            if self.config.strict_mode:
                raise PermissionError("严格模式已开启，无法暂停")
            self.timer.pause()
            if self._process_guard:
                self._process_guard.stop()
            if self._web_guard:
                self._web_guard.stop()
                self._web_guard = None
            self._event("info", "已暂停，系统代理已还原")
            return self.snapshot()

    def resume(self) -> Dict[str, Any]:
        with self._lock:
            if self._tick.state != TimerState.PAUSED:
                return self.snapshot()
            cfg = self.config
            if self._web_guard is None:
                self._web_guard = WebGuard(
                    host=cfg.proxy_host,
                    port=cfg.proxy_port,
                    whitelist=set(cfg.whitelist_websites),
                    on_blocked=self._on_web_blocked,
                )
                try:
                    self._web_guard.start()
                except OSError as exc:
                    self._web_guard = None
                    self._event("error", f"网页拦截启动失败：{exc}")
            if self._process_guard:
                self._process_guard.start()
            self.timer.resume()
            self._event("info", "继续专注")
            return self.snapshot()

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            if self._tick.state == TimerState.RUNNING and self.config.strict_mode:
                raise PermissionError("严格模式已开启，无法提前结束")
            was_active = self._tick.state in (TimerState.RUNNING, TimerState.PAUSED)
            self._stop_guards(save_session=was_active, completed=False)
            self.timer.stop()
            if was_active:
                self._event("info", "已提前结束，统计已记录")
            return self.snapshot()

    def _stop_guards(self, save_session: bool, completed: bool) -> None:
        guard, web = self._process_guard, self._web_guard
        self._process_guard = None
        self._web_guard = None
        if guard:
            guard.stop()
        if web:
            web.stop()
        if save_session:
            self.config_manager.add_session(
                Session(
                    started_at=datetime.now().isoformat(),
                    duration_minutes=self.timer.duration_minutes,
                    completed=completed,
                    blocked_apps=self._blocked_apps,
                    blocked_websites=self._blocked_websites,
                )
            )

    # --------------------------------------------------------------- settings
    def update_config(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            cfg = self.config
            if "whitelist_apps" in payload:
                cfg.whitelist_apps = _clean_list(payload["whitelist_apps"])
            if "whitelist_websites" in payload:
                cfg.whitelist_websites = _clean_list(payload["whitelist_websites"])
            if "strict_mode" in payload:
                cfg.strict_mode = bool(payload["strict_mode"])
            if "focus_duration" in payload and self._tick.state == TimerState.IDLE:
                try:
                    minutes = int(payload["focus_duration"])
                except (TypeError, ValueError):
                    raise ValueError("专注时长必须是数字")
                if minutes <= 0:
                    raise ValueError("专注时长必须大于 0")
                cfg.focus_duration = minutes
                self.timer.set_duration(minutes)
            self.config_manager.save()
            return self.snapshot()

    def preview(self) -> Dict[str, Any]:
        """Which windowed apps would be closed right now (dry run)."""
        cfg = self.config
        guard = ProcessGuard(
            whitelist=set(cfg.whitelist_apps),
            protected=set(cfg.protected_apps),
            dry_run=True,
        )
        return {"apps": [name for name, _pid in guard.scan_blockable()]}

    def shutdown(self) -> None:
        try:
            self._stop_guards(save_session=False, completed=False)
        except Exception:
            pass
        try:
            self.timer.stop()
        except Exception:
            pass


def _clean_list(values: List[str]) -> List[str]:
    seen = set()
    cleaned: List[str] = []
    for value in values or []:
        item = str(value).strip()
        if not item or item.lower() in seen:
            continue
        seen.add(item.lower())
        cleaned.append(item)
    return cleaned
