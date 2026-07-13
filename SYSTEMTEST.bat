@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
 echo Python nicht gefunden.
 pause
 exit /b 1
)
python SYSTEMTEST.py
pause
