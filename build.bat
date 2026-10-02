@echo off
rem Builds the installer on your own PC (optional: GitHub can do this for you, see the workflow).
cd /d "%~dp0"
py -3 -m venv build-venv
"build-venv\Scripts\python.exe" -m pip install -r requirements.txt pyinstaller
"build-venv\Scripts\pyinstaller.exe" TwitchChatBot.spec --noconfirm
echo.
echo The program folder is ready in dist\TwitchChatBot
echo To make Setup.exe: install Inno Setup from https://jrsoftware.org/isdl.php,
echo open installer.iss in it, and click Build then Compile. The result is in the Output folder.
pause
