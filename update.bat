@echo off
rem Downloads the latest version from GitHub (needs Git) and updates what the bot needs.
rem Your commands, timers and Twitch login are kept: they live in the data and authentication folders.
cd /d "%~dp0"
git pull
"venv\Scripts\python.exe" -m pip install -q -U -r requirements.txt
echo.
echo Updated. Start the bot with run.bat
pause
