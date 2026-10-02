; Inno Setup recipe: wraps the TwitchChatBot folder into one Setup.exe.
; AppVersion is passed in on the command line (/DAppVersion=1.2.3) by the build.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; Keep this id the same forever: it is how a newer installer recognises and upgrades an older install.
AppId={{4E70C50A-4FE4-495F-A476-F76952B1DFB1}}
AppName=Twitch Chat Bot
AppVersion={#AppVersion}
DefaultDirName={autopf}\TwitchChatBot
DefaultGroupName=Twitch Chat Bot
OutputDir=Output
OutputBaseFilename=TwitchChatBot-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\TwitchChatBot.exe
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "dist\TwitchChatBot\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Twitch Chat Bot"; Filename: "{app}\TwitchChatBot.exe"
Name: "{autodesktop}\Twitch Chat Bot"; Filename: "{app}\TwitchChatBot.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\TwitchChatBot.exe"; Description: "Start Twitch Chat Bot now"; Flags: nowait postinstall skipifsilent

; Your commands, timers and Twitch login live in %APPDATA%\TwitchChatBot, outside the install folder,
; so uninstalling or upgrading never deletes them.
