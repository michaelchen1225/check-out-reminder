# Checkout Reminder

A lightweight Windows background utility that reminds you to check out when your work hours are up.

When your computer starts, the app records the time as your work start. After your configured work hours (default 9h), it pops up a notification and dialog telling you to leave.

---

## How It Works

1. App launches at Windows login and records the current time as **work start**
2. **Work end = start time + work hours** (default 9h, configurable)
3. At end time: a Windows balloon notification appears + a modal dialog you must click OK to dismiss
4. If you restart the app mid-day, it restores the original start time — your 9-hour clock keeps running

---

## Requirements

- Windows 10 / 11
- Python 3.11 with `pywin32` installed (`pip install pywin32`)
- `pyinstaller` for building the `.exe` (`pip install pyinstaller`)

---

## First-Time Setup

### 1. Build the executable

```bat
.\build.bat
```

This produces `dist\checkout_reminder.exe`.

### 2. Install to Windows Startup

```bat
.\install_startup.bat
```

This creates a shortcut in your Windows Startup folder so the app launches automatically on every login.

### 3. Reboot

After rebooting, the app runs silently in the background. You'll see its icon in the system tray (click the `^` arrow in the taskbar bottom-right if you don't see it).

---

## Tray Icon

Right-click the tray icon for options:

| Menu item | What it does |
|---|---|
| Status | Shows start time, end time, and time remaining |
| Snooze 15 min | Delays the reminder by 15 minutes |
| Settings | Change your work hours (saved persistently) |
| Auto-start: On/Off | Toggle auto-launch at Windows login via Registry |
| Exit | Quit the app |

Double-click the tray icon to open Status directly.

---

## Settings

Work hours are saved to:
```
%APPDATA%\CheckoutReminder\config.json
```

Example:
```json
{ "work_hours": 9.0 }
```

Change via right-click → **Settings** — takes effect immediately without restarting.

---

## Dev / Testing

Run directly (with console, shows errors):
```
python.exe .\checkout_reminder.py
```

Run as background process (no console):
```
pythonw.exe .\checkout_reminder.py
```

**To test the notification quickly**, temporarily change `DEFAULT_HOURS = 9.0` to `DEFAULT_HOURS = 0.03` in `checkout_reminder.py` (~108 seconds), then revert and rebuild.

---

## Uninstall

Remove from startup:
```bat
.\uninstall_startup.bat
```

To fully remove, also delete:
- `dist\checkout_reminder.exe`
- `%APPDATA%\CheckoutReminder\` (saved config and start time)

---

## Files

| File | Purpose |
|---|---|
| `checkout_reminder.py` | Main application source |
| `icon.ico` | System tray icon |
| `build.bat` | Builds `dist\checkout_reminder.exe` via PyInstaller |
| `install_startup.bat` | Adds exe to Windows Startup folder |
| `uninstall_startup.bat` | Removes from Windows Startup folder |
| `requirements.txt` | Python dependencies |
