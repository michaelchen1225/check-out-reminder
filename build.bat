@echo off
setlocal

python.exe -m PyInstaller ^
    --onefile ^
    --windowed ^
    --icon=icon.ico ^
    --name=checkout_reminder ^
    --add-data "icon.ico;." ^
    --hidden-import pywintypes ^
    --hidden-import win32timezone ^
    checkout_reminder.py

echo.
echo Build complete: dist\checkout_reminder.exe
pause
