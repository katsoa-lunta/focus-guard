"""Main GUI for FocusGuard using CustomTkinter."""
from __future__ import annotations

import logging
import os
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox
from typing import Optional

# Insert project root so core can be imported when running as script.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    import customtkinter as ctk
except ImportError:
    # Fallback to plain tkinter if customtkinter is missing.
    ctk = None

from core.config import ConfigManager, Session
from core.timer import FocusTimer, TimerState
from core.process_guard import ProcessGuard
from core.web_guard import WebGuard

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

if ctk:
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("green")
    BaseFrame = ctk.CTkFrame
    BaseButton = ctk.CTkButton
    BaseLabel = ctk.CTkLabel
    BaseEntry = ctk.CTkEntry
    BaseSwitch = ctk.CTkSwitch
    BaseTabview = ctk.CTkTabview
    BaseProgress = ctk.CTkProgressBar
else:
    BaseFrame = tk.Frame
    BaseButton = tk.Button
    BaseLabel = tk.Label
    BaseEntry = tk.Entry
    BaseSwitch = tk.Checkbutton
    BaseTabview = tk.Notebook
    BaseProgress = tk.Progressbar


class EditableList(BaseFrame):
    """A label + listbox + entry + add/remove widget."""

    def __init__(self, master, title: str, items: list[str], **kwargs):
        super().__init__(master, **kwargs)
        self.items = list(items)
        self.title = title
        self._build()

    def _build(self):
        BaseLabel(self, text=self.title, font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 6))

        list_frame = BaseFrame(self)
        list_frame.pack(fill="both", expand=True)

        if ctk:
            self.listbox = tk.Listbox(
                list_frame, font=("Segoe UI", 12), selectmode="single",
                bg="#2b2b2b", fg="#ffffff", highlightthickness=0, borderwidth=0,
            )
        else:
            self.listbox = tk.Listbox(list_frame, font=("Segoe UI", 12), selectmode="single")
        self.listbox.pack(side="left", fill="both", expand=True, padx=(0, 6))

        scrollbar = tk.Scrollbar(list_frame, command=self.listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=scrollbar.set)

        controls = BaseFrame(self)
        controls.pack(fill="x", pady=(6, 0))

        self.entry = BaseEntry(controls, placeholder_text="输入后按添加" if ctk else "")
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.entry.bind("<Return>", lambda e: self.add())

        BaseButton(controls, text="添加", width=60, command=self.add).pack(side="left", padx=(0, 6))
        BaseButton(controls, text="删除", width=60, command=self.remove).pack(side="left")

        self._refresh()

    def _refresh(self):
        self.listbox.delete(0, "end")
        for item in self.items:
            self.listbox.insert("end", item)

    def add(self):
        text = self.entry.get().strip()
        if not text:
            return
        if text not in self.items:
            self.items.append(text)
            self._refresh()
        self.entry.delete(0, "end")

    def remove(self):
        selection = self.listbox.curselection()
        if not selection:
            return
        index = selection[0]
        self.items.pop(index)
        self._refresh()

    def get_items(self) -> list[str]:
        return list(self.items)

    def set_items(self, items: list[str]):
        self.items = list(items)
        self._refresh()


class FocusGuardApp:
    def __init__(self):
        self.config = ConfigManager()
        self.timer = FocusTimer(self.config.config.focus_duration)
        self.process_guard: Optional[ProcessGuard] = None
        self.web_guard: Optional[WebGuard] = None
        self._blocked_apps = 0
        self._blocked_websites = 0

        self._build_ui()
        self.timer.register_tick(self._on_tick)
        self.timer.register_finish(self._on_finish)

    def _build_ui(self):
        if ctk:
            self.root = ctk.CTk()
        else:
            self.root = tk.Tk()
        self.root.title("FocusGuard · 专注守卫")
        self.root.geometry("720x520")
        self.root.minsize(520, 420)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Header
        header = BaseFrame(self.root)
        header.pack(fill="x", padx=16, pady=(16, 8))
        BaseLabel(header, text="FocusGuard", font=("Segoe UI", 22, "bold")).pack(side="left")
        self.status_label = BaseLabel(header, text="准备就绪", font=("Segoe UI", 12))
        self.status_label.pack(side="right")

        # Tabs
        if ctk:
            self.tabs = BaseTabview(self.root)
            self.tabs.pack(fill="both", expand=True, padx=16, pady=8)
            self.tab_timer = self.tabs.add("⏱ 专注计时")
            self.tab_whitelist = self.tabs.add("📋 白名单")
            self.tab_stats = self.tabs.add("📊 统计")
            self.tab_settings = self.tabs.add("⚙️ 设置")
        else:
            self.tabs = BaseTabview(self.root)
            self.tabs.pack(fill="both", expand=True, padx=16, pady=8)
            self.tab_timer = tk.Frame(self.tabs)
            self.tab_whitelist = tk.Frame(self.tabs)
            self.tab_stats = tk.Frame(self.tabs)
            self.tab_settings = tk.Frame(self.tabs)
            self.tabs.add(self.tab_timer, text="专注计时")
            self.tabs.add(self.tab_whitelist, text="白名单")
            self.tabs.add(self.tab_stats, text="统计")
            self.tabs.add(self.tab_settings, text="设置")

        self._build_timer_tab()
        self._build_whitelist_tab()
        self._build_stats_tab()
        self._build_settings_tab()

    def _build_timer_tab(self):
        frame = BaseFrame(self.tab_timer)
        frame.pack(expand=True)

        self.timer_label = BaseLabel(
            frame, text="25:00", font=("Segoe UI", 64, "bold")
        )
        self.timer_label.pack(pady=(40, 20))

        self.progress = BaseProgress(frame, width=360)
        if ctk:
            self.progress.set(1.0)
        else:
            self.progress["value"] = 100
        self.progress.pack(pady=(0, 24))

        controls = BaseFrame(frame)
        controls.pack()

        self.start_btn = BaseButton(controls, text="开始专注", width=110, command=self._start)
        self.start_btn.pack(side="left", padx=6)

        self.pause_btn = BaseButton(controls, text="暂停", width=110, command=self._pause, state="disabled")
        self.pause_btn.pack(side="left", padx=6)

        self.stop_btn = BaseButton(controls, text="停止", width=110, command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)

        dur_frame = BaseFrame(frame)
        dur_frame.pack(pady=(24, 0))
        BaseLabel(dur_frame, text="专注时长（分钟）：").pack(side="left")
        self.duration_entry = BaseEntry(dur_frame, width=60)
        self.duration_entry.insert(0, str(self.config.config.focus_duration))
        self.duration_entry.pack(side="left", padx=6)
        BaseButton(dur_frame, text="应用", width=60, command=self._apply_duration).pack(side="left")

    def _build_whitelist_tab(self):
        container = BaseFrame(self.tab_whitelist)
        container.pack(fill="both", expand=True, padx=8, pady=8)

        left = EditableList(container, "允许运行的 App（进程名，如 chrome.exe）", self.config.config.whitelist_apps)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        self.app_list = left

        right = EditableList(container, "允许访问的网站（域名，如 google.com）", self.config.config.whitelist_websites)
        right.pack(side="right", fill="both", expand=True)
        self.web_list = right

        BaseLabel(
            self.tab_whitelist,
            text="提示：白名单为空时不会拦截任何程序或网站。",
            font=("Segoe UI", 11), text_color=("gray", "gray") if ctk else None,
        ).pack(anchor="w", padx=8, pady=(0, 8))

    def _build_stats_tab(self):
        self.stats_label = BaseLabel(
            self.tab_stats,
            text=self._stats_text(),
            font=("Segoe UI", 13),
            justify="left",
        )
        self.stats_label.pack(anchor="nw", padx=16, pady=16)

    def _build_settings_tab(self):
        frame = BaseFrame(self.tab_settings)
        frame.pack(fill="both", expand=True, padx=16, pady=16)

        self.strict_var = tk.BooleanVar(value=self.config.config.strict_mode)
        if ctk:
            self.strict_switch = BaseSwitch(
                frame, text="严格模式（专注中禁止暂停/停止）",
                variable=self.strict_var, onvalue=True, offvalue=False,
            )
        else:
            self.strict_switch = BaseSwitch(
                frame, text="严格模式（专注中禁止暂停/停止）",
                variable=self.strict_var,
            )
        self.strict_switch.pack(anchor="w", pady=6)

        self.autostart_var = tk.BooleanVar(value=self.config.config.autostart)
        if ctk:
            self.autostart_switch = BaseSwitch(
                frame, text="开机自动启动",
                variable=self.autostart_var, onvalue=True, offvalue=False,
            )
        else:
            self.autostart_switch = BaseSwitch(
                frame, text="开机自动启动",
                variable=self.autostart_var,
            )
        self.autostart_switch.pack(anchor="w", pady=6)

        port_frame = BaseFrame(frame)
        port_frame.pack(anchor="w", pady=(12, 0))
        BaseLabel(port_frame, text="本地代理端口：").pack(side="left")
        self.port_entry = BaseEntry(port_frame, width=80)
        self.port_entry.insert(0, str(self.config.config.proxy_port))
        self.port_entry.pack(side="left", padx=6)

        BaseButton(frame, text="保存设置", command=self._save_settings).pack(anchor="w", pady=(16, 0))

    def _stats_text(self) -> str:
        sessions = self.config.config.sessions
        total = len(sessions)
        completed = sum(1 for s in sessions if s.get("completed"))
        total_minutes = sum(s.get("duration_minutes", 0) for s in sessions)
        blocked_apps = sum(s.get("blocked_apps", 0) for s in sessions)
        blocked_web = sum(s.get("blocked_websites", 0) for s in sessions)
        return (
            f"总专注次数：{total}\n"
            f"完成次数：{completed}\n"
            f"总专注时长：{total_minutes} 分钟\n"
            f"累计拦截 App：{blocked_apps} 次\n"
            f"累计拦截网站：{blocked_web} 次"
        )

    def _on_tick(self, tick):
        minutes, seconds = divmod(tick.remaining_seconds, 60)
        self.timer_label.configure(text=f"{minutes:02d}:{seconds:02d}")
        progress = tick.remaining_seconds / tick.total_seconds if tick.total_seconds else 0
        if ctk:
            self.progress.set(progress)
        else:
            self.progress["value"] = progress * 100
        self.root.update_idletasks()

    def _on_finish(self):
        self._stop_guards(save_session=True, completed=True)
        messagebox.showinfo("FocusGuard", "专注时间结束！休息一下吧。")
        self._reset_ui()

    def _start(self):
        try:
            minutes = int(self.duration_entry.get())
        except ValueError:
            messagebox.showerror("输入错误", "请输入有效的专注时长")
            return
        if minutes <= 0:
            messagebox.showerror("输入错误", "专注时长必须大于 0")
            return

        self._save_whitelists()
        self.config.config.focus_duration = minutes
        self.timer.set_duration(minutes)

        self._blocked_apps = 0
        self._blocked_websites = 0

        self.process_guard = ProcessGuard(
            whitelist=set(self.config.config.whitelist_apps),
            protected=set(self.config.config.protected_apps),
            on_blocked=self._on_app_blocked,
        )
        self.process_guard.start()

        self.web_guard = WebGuard(
            host=self.config.config.proxy_host,
            port=self.config.config.proxy_port,
            whitelist=set(self.config.config.whitelist_websites),
            on_blocked=self._on_web_blocked,
        )
        try:
            self.web_guard.start()
        except Exception as e:
            messagebox.showwarning("网页拦截启动失败", str(e))
            self.web_guard = None

        self.timer.start()
        self._update_ui_state("running")
        self.status_label.configure(text="专注中 · App/网页白名单已启用")
        logger.info("Focus session started for %d minutes", minutes)

    def _pause(self):
        if self.config.config.strict_mode:
            messagebox.showwarning("严格模式", "当前处于严格模式，无法暂停")
            return
        self.timer.pause()
        if self.process_guard:
            self.process_guard.stop()
        if self.web_guard:
            self.web_guard.stop()
        self._update_ui_state("paused")
        self.status_label.configure(text="已暂停")

    def _resume(self):
        if self.web_guard:
            self.web_guard.start()
        if self.process_guard:
            self.process_guard.start()
        self.timer.resume()
        self._update_ui_state("running")
        self.status_label.configure(text="专注中")

    def _stop(self):
        if self.config.config.strict_mode and self.timer.get_tick().state == TimerState.RUNNING:
            messagebox.showwarning("严格模式", "当前处于严格模式，无法提前停止")
            return
        self._stop_guards(save_session=True, completed=False)
        self.timer.stop()
        self._reset_ui()
        self.status_label.configure(text="已停止")

    def _stop_guards(self, save_session: bool, completed: bool):
        if self.process_guard:
            self.process_guard.stop()
            self.process_guard = None
        if self.web_guard:
            self.web_guard.stop()
            self.web_guard = None
        if save_session:
            session = Session(
                started_at=datetime.now().isoformat(),
                duration_minutes=self.timer.duration_minutes,
                completed=completed,
                blocked_apps=self._blocked_apps,
                blocked_websites=self._blocked_websites,
            )
            self.config.add_session(session)
            self.stats_label.configure(text=self._stats_text())

    def _reset_ui(self):
        self._update_ui_state("idle")
        self.timer_label.configure(text=f"{self.config.config.focus_duration:02d}:00")
        if ctk:
            self.progress.set(1.0)
        else:
            self.progress["value"] = 100

    def _update_ui_state(self, state: str):
        if state == "running":
            self.start_btn.configure(state="disabled")
            self.pause_btn.configure(state="normal", text="暂停", command=self._pause)
            self.stop_btn.configure(state="normal")
            self.duration_entry.configure(state="disabled")
        elif state == "paused":
            self.start_btn.configure(state="disabled")
            self.pause_btn.configure(state="normal", text="继续", command=self._resume)
            self.stop_btn.configure(state="normal")
        else:
            self.start_btn.configure(state="normal")
            self.pause_btn.configure(state="disabled", text="暂停")
            self.stop_btn.configure(state="disabled")
            self.duration_entry.configure(state="normal")

    def _on_app_blocked(self, name: str, pid: int):
        self._blocked_apps += 1
        self.status_label.configure(text=f"已关闭：{name}")

    def _on_web_blocked(self, host: str):
        self._blocked_websites += 1
        self.status_label.configure(text=f"已拦截：{host}")

    def _save_whitelists(self):
        self.config.config.whitelist_apps = self.app_list.get_items()
        self.config.config.whitelist_websites = self.web_list.get_items()
        self.config.save()

    def _apply_duration(self):
        try:
            minutes = int(self.duration_entry.get())
            if minutes > 0:
                self.config.config.focus_duration = minutes
                self.timer.set_duration(minutes)
                self.config.save()
                self.timer_label.configure(text=f"{minutes:02d}:00")
        except ValueError:
            messagebox.showerror("输入错误", "请输入有效的数字")

    def _save_settings(self):
        self.config.config.strict_mode = self.strict_var.get()
        self.config.config.autostart = self.autostart_var.get()
        try:
            port = int(self.port_entry.get())
            if 1024 <= port <= 65535:
                self.config.config.proxy_port = port
            else:
                raise ValueError
        except ValueError:
            messagebox.showerror("输入错误", "代理端口必须是 1024-65535 之间的数字")
            return
        self.config.save()
        messagebox.showinfo("设置", "设置已保存")

    def _on_close(self):
        self._stop_guards(save_session=False, completed=False)
        self.timer.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    app = FocusGuardApp()
    app.run()


if __name__ == "__main__":
    main()
