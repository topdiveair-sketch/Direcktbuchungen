@echo off
title Zuhause am Bach - Programm beenden
echo Beende den lokalen Python-Server...
taskkill /F /IM python.exe >nul 2>nul
echo Fertig.
pause
