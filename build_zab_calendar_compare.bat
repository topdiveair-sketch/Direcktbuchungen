@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 zab_os_calendar_compare_gui.py
) else (
    python zab_os_calendar_compare_gui.py
)
if errorlevel 1 (
    echo.
    echo Fehler beim Start. Python 3 mit Tkinter wird benoetigt.
    pause
)
endlocal
