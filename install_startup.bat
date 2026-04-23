@echo off
setlocal

set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set EXE=%~dp0dist\checkout_reminder.exe
set LNK=%STARTUP%\checkout_reminder.lnk

if not exist "%EXE%" (
    echo ERROR: dist\checkout_reminder.exe not found.
    echo Run build.bat first.
    pause
    exit /b 1
)

powershell -NoProfile -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%LNK%'); $s.TargetPath = '%EXE%'; $s.Save()"

echo Startup shortcut created at:
echo   %LNK%
echo The app will launch automatically on next Windows login.
pause
