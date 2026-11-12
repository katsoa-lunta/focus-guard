"""Configuration persistence for FocusGuard."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List


DEFAULT_APPS = [
    "notepad.exe",
    "notepad++.exe",
    "code.exe",
    "obsidian.exe",
    "zoom.exe",
    "teams.exe",
    "wechat.exe",
]

DEFAULT_WEBSITES = [
    "classroom.google.com",
    "zoom.us",
    "teams.microsoft.com",
    "live.com",
]


@dataclass
class Session:
    started_at: str
    duration_minutes: int
    completed: bool
    blocked_apps: int = 0
    blocked_websites: int = 0


@dataclass
class AppConfig:
    focus_duration: int = 25
    strict_mode: bool = False
    autostart: bool = False
    proxy_port: int = 17862
    proxy_host: str = "127.0.0.1"
    whitelist_apps: List[str] = field(default_factory=lambda: DEFAULT_APPS.copy())
    whitelist_websites: List[str] = field(default_factory=lambda: DEFAULT_WEBSITES.copy())
    protected_apps: List[str] = field(default_factory=list)
    sessions: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class ConfigManager:
    def __init__(self, path: str | None = None):
        if path is None:
            base = Path.home() / ".focusguard"
            base.mkdir(parents=True, exist_ok=True)
            path = base / "config.json"
        self.path = Path(path)
        self.config = AppConfig()
        self.load()

    def load(self) -> None:
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.config = AppConfig.from_dict(data)
            except Exception:
                self.config = AppConfig()
        else:
            self.config = AppConfig()
        # Always ensure current executable is protected
        self._ensure_self_protected()

    def save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.config.to_dict(), f, ensure_ascii=False, indent=2)

    def add_session(self, session: Session) -> None:
        self.config.sessions.append(session.__dict__)
        self.save()

    def _ensure_self_protected(self) -> None:
        import sys

        self_name = os.path.basename(sys.executable).lower()
        if self_name and self_name not in self.config.protected_apps:
            self.config.protected_apps.append(self_name)
