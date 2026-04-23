import sys
import os
import json
import datetime
import threading
import winreg

import win32api
import win32con
import win32event
import win32gui
import winerror
import pywintypes
import tkinter as tk
from tkinter import messagebox, simpledialog

# ── constants ────────────────────────────────────────────────────────────────
APP_NAME       = "Checkout Reminder"
MUTEX_NAME     = "CheckoutReminderMutex_v1"
REG_KEY        = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
REG_VALUE      = "CheckoutReminder"
WM_TRAY        = win32con.WM_USER + 20
WM_NOTIFY      = win32con.WM_USER + 21   # posted by timer → show reminder
WM_TOOLTIP_UPD = win32con.WM_USER + 22   # posted by 60-s ticker → update tip
DEFAULT_HOURS  = 9.0

APPDATA_DIR    = os.path.join(os.environ.get("APPDATA", ""), "CheckoutReminder")
CONFIG_FILE    = os.path.join(APPDATA_DIR, "config.json")
START_FILE     = os.path.join(APPDATA_DIR, "start_time.txt")

# ── persistence helpers ───────────────────────────────────────────────────────

def _ensure_dir():
    os.makedirs(APPDATA_DIR, exist_ok=True)


def load_config() -> float:
    try:
        with open(CONFIG_FILE) as f:
            return float(json.load(f).get("work_hours", DEFAULT_HOURS))
    except Exception:
        return DEFAULT_HOURS


def save_config(hours: float):
    _ensure_dir()
    with open(CONFIG_FILE, "w") as f:
        json.dump({"work_hours": hours}, f)


def load_start_time(work_hours: float) -> datetime.datetime:
    """Return saved start time if it was recorded today and < work_hours ago, else now."""
    try:
        with open(START_FILE) as f:
            saved = datetime.datetime.fromisoformat(f.read().strip())
        now = datetime.datetime.now()
        if saved.date() == now.date() and (now - saved).total_seconds() < work_hours * 3600:
            return saved
    except Exception:
        pass
    return _record_start_time()


def _record_start_time() -> datetime.datetime:
    now = datetime.datetime.now()
    _ensure_dir()
    with open(START_FILE, "w") as f:
        f.write(now.isoformat())
    return now


# ── single-instance guard ─────────────────────────────────────────────────────

def ensure_single_instance():
    mutex = win32event.CreateMutex(None, False, MUTEX_NAME)
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        win32api.CloseHandle(mutex)
        sys.exit(0)
    return mutex  # keep alive for process lifetime


# ── tray application ──────────────────────────────────────────────────────────

class TrayApp:
    def __init__(self, start_time: datetime.datetime, work_hours: float):
        self.start_time  = start_time
        self.work_hours  = work_hours
        self.end_time    = start_time + datetime.timedelta(hours=work_hours)
        self.hwnd        = None
        self.hicon       = None
        self._notify_timer   = None
        self._tooltip_timer  = None
        self._snoozed        = False

        self._setup_window()
        self._setup_tray_icon()
        self._schedule_notify()
        self._schedule_tooltip_update()

    # ── window setup ──────────────────────────────────────────────────────────

    def _setup_window(self):
        wc = win32gui.WNDCLASS()
        wc.hInstance     = win32api.GetModuleHandle(None)
        wc.lpszClassName = "CheckoutReminderWnd"
        wc.lpfnWndProc   = self._wnd_proc
        win32gui.RegisterClass(wc)
        self.hwnd = win32gui.CreateWindow(
            wc.lpszClassName, APP_NAME,
            0, 0, 0, 0, 0, 0, 0, wc.hInstance, None
        )

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAY:
            if lparam == win32con.WM_RBUTTONUP:
                self._show_context_menu()
            elif lparam == win32con.WM_LBUTTONDBLCLK:
                self._show_status()
        elif msg == WM_NOTIFY:
            self._on_time_reached()
        elif msg == WM_TOOLTIP_UPD:
            self._update_tooltip()
        elif msg == win32con.WM_DESTROY:
            win32gui.PostQuitMessage(0)
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    # ── tray icon ─────────────────────────────────────────────────────────────

    def _load_icon(self):
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(base, "icon.ico")
        if os.path.isfile(path):
            return win32gui.LoadImage(
                win32api.GetModuleHandle(None), path,
                win32con.IMAGE_ICON, 0, 0,
                win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE
            )
        return win32gui.LoadIcon(0, win32con.IDI_APPLICATION)

    def _setup_tray_icon(self):
        self.hicon = self._load_icon()
        nid = (
            self.hwnd, 0,
            win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP,
            WM_TRAY, self.hicon,
            self._tooltip_text()
        )
        win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, nid)

    def _tooltip_text(self) -> str:
        now  = datetime.datetime.now()
        diff = self.end_time - now
        secs = int(diff.total_seconds())
        if secs <= 0:
            return f"{APP_NAME} — time to check out!"
        h, rem = divmod(secs, 3600)
        m = rem // 60
        return f"{APP_NAME}\nEnds at {self.end_time:%H:%M} ({h}h {m}m left)"

    def _update_tooltip(self):
        nid = (
            self.hwnd, 0,
            win32gui.NIF_TIP,
            WM_TRAY, self.hicon,
            self._tooltip_text()
        )
        win32gui.Shell_NotifyIcon(win32gui.NIM_MODIFY, nid)

    # ── timers ────────────────────────────────────────────────────────────────

    def _schedule_notify(self):
        delay = (self.end_time - datetime.datetime.now()).total_seconds()
        if self._notify_timer:
            self._notify_timer.cancel()
        if delay > 0:
            self._notify_timer = threading.Timer(delay, self._post_notify)
            self._notify_timer.daemon = True
            self._notify_timer.start()
        else:
            self._post_notify()

    def _post_notify(self):
        win32gui.PostMessage(self.hwnd, WM_NOTIFY, 0, 0)

    def _schedule_tooltip_update(self):
        def tick():
            while True:
                threading.Event().wait(60)
                if self.hwnd:
                    win32gui.PostMessage(self.hwnd, WM_TOOLTIP_UPD, 0, 0)
        t = threading.Thread(target=tick, daemon=True)
        t.start()

    # ── notification ──────────────────────────────────────────────────────────

    def _on_time_reached(self):
        self._show_balloon(
            "Time to check out!",
            f"Started: {self.start_time:%H:%M}  |  "
            f"{self.work_hours:g}h elapsed at {self.end_time:%H:%M}"
        )
        self._show_dialog()

    def _show_balloon(self, title: str, text: str):
        try:
            nid = (
                self.hwnd, 0,
                win32gui.NIF_INFO,
                WM_TRAY, self.hicon,
                "",          # tooltip (unused when NIF_INFO set)
                text, 10000, title,
                win32gui.NIIF_INFO
            )
            win32gui.Shell_NotifyIcon(win32gui.NIM_MODIFY, nid)
        except Exception:
            pass

    def _show_dialog(self):
        def run():
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            messagebox.showwarning(
                APP_NAME,
                f"Time to check out!\n\n"
                f"Work started:  {self.start_time:%H:%M}\n"
                f"Work hours:    {self.work_hours:g} h\n"
                f"End of work:   {self.end_time:%H:%M}\n\n"
                f"Please log your time and leave.",
                parent=root
            )
            root.destroy()
        threading.Thread(target=run, daemon=True).start()

    # ── context menu ─────────────────────────────────────────────────────────

    def _show_context_menu(self):
        menu = win32gui.CreatePopupMenu()
        win32gui.AppendMenu(menu, win32con.MF_STRING, 1, "Status")
        win32gui.AppendMenu(menu, win32con.MF_STRING, 2, "Snooze 15 min")
        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
        win32gui.AppendMenu(menu, win32con.MF_STRING, 3, "Settings…")
        autostart_label = "Auto-start: On  ✓" if self._autostart_enabled() else "Auto-start: Off"
        win32gui.AppendMenu(menu, win32con.MF_STRING, 4, autostart_label)
        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
        win32gui.AppendMenu(menu, win32con.MF_STRING, 5, "Exit")

        win32gui.SetForegroundWindow(self.hwnd)
        pos = win32gui.GetCursorPos()
        cmd = win32gui.TrackPopupMenu(
            menu, win32con.TPM_LEFTALIGN | win32con.TPM_RETURNCMD,
            pos[0], pos[1], 0, self.hwnd, None
        )
        win32gui.PostMessage(self.hwnd, win32con.WM_NULL, 0, 0)
        win32gui.DestroyMenu(menu)

        if cmd == 1:
            self._show_status()
        elif cmd == 2:
            self._snooze()
        elif cmd == 3:
            self._open_settings()
        elif cmd == 4:
            self._toggle_autostart()
        elif cmd == 5:
            self._quit()

    # ── status window ─────────────────────────────────────────────────────────

    def _show_status(self):
        now   = datetime.datetime.now()
        diff  = self.end_time - now
        secs  = int(diff.total_seconds())
        if secs > 0:
            h, rem = divmod(secs, 3600)
            m = rem // 60
            remaining = f"{h}h {m}m remaining"
        else:
            remaining = "Past end time"

        def run():
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo(
                f"{APP_NAME} — Status",
                f"Work started:   {self.start_time:%H:%M}\n"
                f"Work hours:     {self.work_hours:g} h\n"
                f"End of work:    {self.end_time:%H:%M}\n"
                f"Now:            {now:%H:%M}\n"
                f"Remaining:      {remaining}",
                parent=root
            )
            root.destroy()
        threading.Thread(target=run, daemon=True).start()

    # ── snooze ────────────────────────────────────────────────────────────────

    def _snooze(self):
        self.end_time = datetime.datetime.now() + datetime.timedelta(minutes=15)
        self._schedule_notify()
        self._update_tooltip()

    # ── settings ──────────────────────────────────────────────────────────────

    def _open_settings(self):
        def run():
            root = tk.Tk()
            root.title(f"{APP_NAME} — Settings")
            root.resizable(False, False)
            root.attributes("-topmost", True)

            tk.Label(root, text="Work hours per day:", padx=12, pady=8).grid(row=0, column=0, sticky="w")
            var = tk.DoubleVar(value=self.work_hours)
            spin = tk.Spinbox(root, from_=0.5, to=24.0, increment=0.5,
                              textvariable=var, width=6, format="%.1f")
            spin.grid(row=0, column=1, padx=8, pady=8)

            def on_save():
                try:
                    hours = float(var.get())
                    if not (0.5 <= hours <= 24):
                        raise ValueError
                except ValueError:
                    messagebox.showerror("Invalid", "Enter a value between 0.5 and 24.", parent=root)
                    return
                self.work_hours = hours
                self.end_time   = self.start_time + datetime.timedelta(hours=hours)
                save_config(hours)
                self._schedule_notify()
                self._update_tooltip()
                root.destroy()

            btn_frame = tk.Frame(root)
            btn_frame.grid(row=1, column=0, columnspan=2, pady=(0, 8))
            tk.Button(btn_frame, text="Save", width=8, command=on_save).pack(side="left", padx=4)
            tk.Button(btn_frame, text="Cancel", width=8, command=root.destroy).pack(side="left", padx=4)

            root.mainloop()

        threading.Thread(target=run, daemon=True).start()

    # ── auto-start ────────────────────────────────────────────────────────────

    def _autostart_enabled(self) -> bool:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY)
            winreg.QueryValueEx(key, REG_VALUE)
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            return False

    def _toggle_autostart(self):
        if self._autostart_enabled():
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE)
            winreg.DeleteValue(key, REG_VALUE)
            winreg.CloseKey(key)
        else:
            exe = sys.executable if not getattr(sys, "frozen", False) else sys.executable
            # When frozen by PyInstaller, sys.executable is the .exe itself
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, REG_VALUE, 0, winreg.REG_SZ, f'"{exe}"')
            winreg.CloseKey(key)

    # ── quit ─────────────────────────────────────────────────────────────────

    def _quit(self):
        if self._notify_timer:
            self._notify_timer.cancel()
        win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (self.hwnd, 0))
        win32gui.PostQuitMessage(0)

    # ── run ───────────────────────────────────────────────────────────────────

    def run(self):
        win32gui.PumpMessages()


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    mutex      = ensure_single_instance()   # noqa: F841 — must stay alive
    work_hours = load_config()
    start_time = load_start_time(work_hours)
    app        = TrayApp(start_time, work_hours)
    app.run()


if __name__ == "__main__":
    main()
