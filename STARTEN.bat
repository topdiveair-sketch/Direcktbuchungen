@echo off
title Zuhause am Bach - Direktbuchung V5
cd /d "%~dp0"
echo ============================================
echo Zuhause am Bach - Direktbuchung V5
echo ============================================
where python >nul 2>nul
if errorlevel 1 (
  echo Python wurde nicht gefunden.
  echo Bitte Python von https://www.python.org/downloads/ installieren.
  echo Dabei "Add Python to PATH" anklicken.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Erstelle lokale Programmumgebung...
  python -m venv .venv
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Installation fehlgeschlagen.
  pause
  exit /b 1
)
start "" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:5000"
python app.py
pause
