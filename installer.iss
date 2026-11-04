; Inno Setup recipe: wraps the TwitchChatBot folder into one Setup.exe.
; AppVersion is passed in on the command line (/DAppVersion=1.2.3) by the build.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
; AppNumber: the same version as four plain numbers (1.16.0 -> 1.16.0.0), for Setup.exe's own Properties > Details.
#ifndef AppNumber
  #define AppNumber "0.0.0.0"
#endif
; 1.16.0: the program is FQPNsChatBot.exe (no apostrophe). Before 1.16.0 it was FQPN'sChatBot.exe.
#define AppExe "FQPNsChatBot.exe"

[Setup]
; Keep this id the same forever: it is how a newer installer recognises and upgrades an older install.
AppId={{4E70C50A-4FE4-495F-A476-F76952B1DFB1}}
AppName=FQPN's Chat Bot
AppVersion={#AppVersion}
AppPublisher=FQPN
AppCopyright=Copyright (c) FQPN
VersionInfoVersion={#AppNumber}
VersionInfoCompany=FQPN
VersionInfoProductName=FQPN's Chat Bot
VersionInfoDescription=FQPN's Chat Bot Setup
VersionInfoProductTextVersion={#AppVersion}
DefaultDirName={autopf}\TwitchChatBot
DefaultGroupName=FQPN's Chat Bot
OutputDir=Output
OutputBaseFilename=FQPN-Chat-Bot-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExe}
SetupIconFile=icon.ico
WizardStyle=modern

[InstallDelete]
; The first release was called "FQPN's Chat Bot.exe". An update never removes files by itself, so take that old program
; away: otherwise two programs sit in the folder and the old one can be started by mistake.
Type: files; Name: "{app}\FQPN's Chat Bot.exe"
; 1.16.0: the program was renamed from FQPN'sChatBot.exe to FQPNsChatBot.exe (an apostrophe in a program's name can trip up
; scripts and shortcuts). The old one is removed; the shortcuts below are made again for the new name.
Type: files; Name: "{app}\FQPN'sChatBot.exe"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "dist\TwitchChatBot\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\FQPN's Chat Bot"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\FQPN's Chat Bot"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
; A desktop shortcut that already exists is pointed at the current program (an old one would lead to the deleted file).
Name: "{autodesktop}\FQPN's Chat Bot"; Filename: "{app}\{#AppExe}"; Check: DesktopShortcutExists

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start FQPN's Chat Bot now"; Flags: nowait postinstall skipifsilent
; After "Restart and update" inside the app, the update runs silently and the app opens again by itself.
Filename: "{app}\{#AppExe}"; Flags: nowait; Check: StartAfterUpdate

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

// 1.16.0: "Start with Windows" (Settings > App) is a value in the registry that names the program. Point an old one at the
// renamed program now, so Windows still starts the app even before it is opened once after this update (the app also
// repairs this value itself every time it starts). "--minimized" and anything else in the value stay as they were.
procedure CurStepChanged(CurStep: TSetupStep);
var
  Cmd: String;
begin
  if CurStep = ssPostInstall then
    if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'FQPNsChatBot', Cmd) then
      if Pos('FQPN''sChatBot.exe', Cmd) > 0 then
      begin
        StringChangeEx(Cmd, 'FQPN''sChatBot.exe', '{#AppExe}', True);
        RegWriteStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'FQPNsChatBot', Cmd);
      end;
end;
