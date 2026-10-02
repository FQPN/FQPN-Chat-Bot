@echo off
rem Starts the bot. The first run creates the Python environment and installs what the bot needs.
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
  echo Setting things up for the first time...
  where py >nul 2>nul && (py -3 -m venv venv) || (python -m venv venv)
)
"venv\Scripts\python.exe" -m pip install -q -r requirements.txt
"venv\Scripts\python.exe" main.py
pause
