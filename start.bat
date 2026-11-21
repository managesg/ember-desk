@echo off
rem Double-click to install checks + start Ember Council (Windows). Needs Python 3.10+.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
if errorlevel 1 pause
