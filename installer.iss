; Inno Setup recipe: wraps the TwitchChatBot folder into one Setup.exe.
; AppVersion is passed in on the command line (/DAppVersion=1.2.3) by the build.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; Keep this id the same forever: it is how a newer installer recognises and upgrades an older install.
AppId={{4E70C50A-4FE4-495F-A476-F76952B1DFB1}}
AppName=FQPN's Chat Bot
AppVersion={#AppVersion}
DefaultDirName={autopf}\TwitchChatBot
DefaultGroupName=FQPN's Chat Bot
OutputDir=Output
OutputBaseFilename=FQPN-Chat-Bot-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\FQPN'sChatBot.exe
SetupIconFile=icon.ico
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "dist\TwitchChatBot\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\FQPN's Chat Bot"; Filename: "{app}\FQPN'sChatBot.exe"
Name: "{autodesktop}\FQPN's Chat Bot"; Filename: "{app}\FQPN'sChatBot.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\FQPN'sChatBot.exe"; Description: "Start FQPN's Chat Bot now"; Flags: nowait postinstall skipifsilent
; After "Restart and update" inside the app, the update runs silently and the app opens again by itself.
Filename: "{app}\FQPN'sChatBot.exe"; Flags: nowait; Check: StartAfterUpdate

[Code]
function StartAfterUpdate: Boolean;
begin
  Result := WizardSilent and (ExpandConstant('{param:RELAUNCH|0}') = '1');
end;

; Your commands, timers and Twitch login live in %APPDATA%\TwitchChatBot, outside the install folder,
; so uninstalling or upgrading never deletes them.
