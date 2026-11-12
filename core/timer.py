"""Focus timer with callback support."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, Optional


class TimerState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"


@dataclass
class TimerTick:
    remaining_seconds: int
    total_seconds: int
    state: TimerState


class FocusTimer:
    def __init__(self, duration_minutes: int = 25):
        self.duration_minutes = duration_minutes
        self.total_seconds = duration_minutes * 60
        self.remaining_seconds = self.total_seconds
        self.state = TimerState.IDLE
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._lock = threading.Lock()
        self._callbacks: list[Callable[[TimerTick], None]] = []
        self._finish_callbacks: list[Callable[[], None]] = []

    def register_tick(self, callback: Callable[[TimerTick], None]) -> None:
        self._callbacks.append(callback)

    def register_finish(self, callback: Callable[[], None]) -> None:
        self._finish_callbacks.append(callback)

    def set_duration(self, minutes: int) -> None:
        with self._lock:
            if self.state != TimerState.RUNNING:
                self.duration_minutes = minutes
                self.total_seconds = minutes * 60
                self.remaining_seconds = self.total_seconds
                self._notify()

    def start(self) -> None:
        with self._lock:
            if self.state == TimerState.RUNNING:
                return
            if self.state == TimerState.FINISHED:
                self.remaining_seconds = self.total_seconds
            self.state = TimerState.RUNNING
            self._stop_event.clear()
            self._pause_event.set()
        self._notify()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def pause(self) -> None:
        with self._lock:
            if self.state == TimerState.RUNNING:
                self.state = TimerState.PAUSED
                self._pause_event.clear()
        self._notify()

    def resume(self) -> None:
        with self._lock:
            if self.state == TimerState.PAUSED:
                self.state = TimerState.RUNNING
                self._pause_event.set()
        self._notify()

    def stop(self) -> None:
        self._stop_event.set()
        self._pause_event.set()
        with self._lock:
            self.state = TimerState.IDLE
            self.remaining_seconds = self.total_seconds
        self._notify()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._pause_event.wait()
            if self._stop_event.is_set():
                break
            time.sleep(1)
            with self._lock:
                if self.state != TimerState.RUNNING:
                    continue
                self.remaining_seconds -= 1
                if self.remaining_seconds <= 0:
                    self.remaining_seconds = 0
                    self.state = TimerState.FINISHED
            self._notify()
            if self.state == TimerState.FINISHED:
                for cb in self._finish_callbacks:
                    try:
                        cb()
                    except Exception:
                        pass
                break

    def _notify(self) -> None:
        tick = TimerTick(
            remaining_seconds=self.remaining_seconds,
            total_seconds=self.total_seconds,
            state=self.state,
        )
        for cb in self._callbacks:
            try:
                cb(tick)
            except Exception:
                pass

    def get_tick(self) -> TimerTick:
        return TimerTick(
            remaining_seconds=self.remaining_seconds,
            total_seconds=self.total_seconds,
            state=self.state,
        )
