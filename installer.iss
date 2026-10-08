; Inno Setup recipe for qwhip-setup.exe. Built by `python build.py` (needs Inno Setup 6).
;
; What a user gets:
;   * qwhip installed for just them (no admin prompt) in %LOCALAPPDATA%\Programs\qwhip
;   * Start menu entry, optional desktop shortcut, optional "start with Windows"
;   * A normal uninstaller (Settings -> Apps). Their screenshots are kept.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "dist\qwhip"
#endif
#ifndef OutputDir
  #define OutputDir "release"
#endif

[Setup]
AppId={{8C1B2F4E-5A7D-4C3B-9E21-6F0A9D3C7B11}
AppName=qwhip
AppVersion={#AppVersion}
AppPublisher=qwhip
AppComments=Screenshot sessions for AI
DefaultDirName={localappdata}\Programs\qwhip
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir={#OutputDir}
OutputBaseFilename=qwhip-setup
SetupIconFile=assets\qwhip.ico
UninstallDisplayIcon={app}\qwhip.exe
UninstallDisplayName=qwhip
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=force

[Tasks]
Name: "startup"; Description: "Start qwhip when Windows starts"; Flags: unchecked
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{userprograms}\qwhip"; Filename: "{app}\qwhip.exe"
Name: "{userdesktop}\qwhip"; Filename: "{app}\qwhip.exe"; Tasks: desktopicon

[Registry]
; Same value qwhip's own Settings checkbox writes, so the two stay in agreement.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
  ValueName: "qwhip"; ValueData: """{app}\qwhip.exe"""; Tasks: startup

[Run]
Filename: "{app}\qwhip.exe"; Description: "Start qwhip now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Close qwhip, and remove "start with Windows" even if it was turned on from qwhip's Settings.
Filename: "{sys}\taskkill.exe"; Parameters: "/im qwhip.exe /f"; Flags: runhidden; RunOnceId: "StopQwhip"
Filename: "{sys}\reg.exe"; Parameters: "delete HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v qwhip /f"; \
  Flags: runhidden; RunOnceId: "RemoveStartup"
