@echo off
set LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\checkout_reminder.lnk

if exist "%LNK%" (
    del "%LNK%"
    echo Startup shortcut removed.
) else (
    echo Startup shortcut not found — nothing to remove.
)
pause
