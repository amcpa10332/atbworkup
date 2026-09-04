; Inno Setup script for ATBWorkup.
; Wraps the already-built dist\ATBWorkup folder (from build_windows.ps1) into
; a normal Windows installer: double-click, click Next a few times, get a
; Start Menu / Desktop shortcut. No zip, no manual extraction, no "am I
; running it from inside the zip" confusion.
;
; Build with (after running scripts\build_windows.ps1 first):
;   "C:\Users\AustinMalone\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer\atbworkup.iss
;
; Output: installer\Output\ATBWorkupSetup-v<version>.exe

#define MyAppName "ATBWorkup"
#define MyAppVersion GetEnv("ATBW_VERSION")
#if MyAppVersion == ""
  #define MyAppVersion "0.1.0"
#endif
#define MyAppPublisher "zbcpa"
#define MyAppExeName "ATBWorkup.exe"

[Setup]
AppId={{6F2B8A2E-6E7B-4E7B-9C3E-ATBWORKUP001}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Per-user install by default (no admin prompt needed) -- students on
; school-managed laptops without admin rights can still install this way.
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=ATBWorkupSetup-v{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\atbworkup\assets\app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "..\dist\ATBWorkup\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
