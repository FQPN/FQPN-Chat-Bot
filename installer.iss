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

[InstallDelete]
; The first release was called "FQPN's Chat Bot.exe". An update never removes files by itself, so take that old program
; away: otherwise two programs sit in the folder and the old one can be started by mistake.
Type: files; Name: "{app}\FQPN's Chat Bot.exe"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "dist\TwitchChatBot\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\FQPN's Chat Bot"; Filename: "{app}\FQPN'sChatBot.exe"
Name: "{autodesktop}\FQPN's Chat Bot"; Filename: "{app}\FQPN'sChatBot.exe"; Tasks: desktopicon
; A desktop shortcut that already exists is pointed at the current program (an old one would lead to the deleted file).
Name: "{autodesktop}\FQPN's Chat Bot"; Filename: "{app}\FQPN'sChatBot.exe"; Check: DesktopShortcutExists

[Run]
Filename: "{app}\FQPN'sChatBot.exe"; Description: "Start FQPN's Chat Bot now"; Flags: nowait postinstall skipifsilent
; After "Restart and update" inside the app, the update runs silently and the app opens again by itself.
Filename: "{app}\FQPN'sChatBot.exe"; Flags: nowait; Check: StartAfterUpdate

; Your commands, timers and Twitch login live in %APPDATA%\TwitchChatBot, outside the install folder,
; so uninstalling or upgrading never deletes them.

; Pascal code below: only code and // comments are allowed in this last section, so keep it at the end of the file.
[Code]
function DesktopShortcutExists: Boolean;
begin
  Result := FileExists(ExpandConstant('{autodesktop}\FQPN''s Chat Bot.lnk'));
end;

function StartAfterUpdate: Boolean;
begin
  Result := WizardSilent and (ExpandConstant('{param:RELAUNCH|0}') = '1');
end;
