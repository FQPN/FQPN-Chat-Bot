@echo off
rem Double-click this to install the newest fqpn_update zip from your Downloads folder.
rem Nothing of yours is lost: the data and authentication folders are never in the zip.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0apply_update.ps1"
echo.
pause
