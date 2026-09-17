; Inno Setup script for Blueprint Trial Balance (formerly ATBWorkup).
; Wraps the already-built dist\BlueprintTB folder (from build_windows.ps1) into
; a normal Windows installer: double-click, click Next a few times, get a
; Start Menu / Desktop shortcut. No zip, no manual extraction, no "am I
; running it from inside the zip" confusion.
;
; Build with (after running scripts\build_windows.ps1 first):
;   "C:\Users\AustinMalone\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer\blueprinttb.iss
;
; Output: installer\Output\BlueprintTBSetup-v<version>.exe

#define MyAppName "Blueprint Trial Balance"
#define MyAppVersion GetEnv("BTA_VERSION")
#if MyAppVersion == ""
  #define MyAppVersion "2.0.0"
#endif
#define MyAppPublisher "zbcpa"
#define MyAppExeName "BlueprintTB.exe"

[Setup]
; New AppId for the rebrand (was ATBWorkup) -- an existing ATBWorkup install
; won't be recognized as an upgrade target by this installer on AppId alone,
; so [Code] below explicitly finds and silently removes any ATBWorkup
; install before this one proceeds (see InitializeSetup).
AppId={{6F2B8A2E-6E7B-4E7B-9C3E-BLUEPRINTTB1}}
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
OutputBaseFilename=BlueprintTBSetup-v{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\blueprinttb\assets\app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "..\dist\BlueprintTB\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
// The product was previously named ATBWorkup and shipped under a different
// AppId, so Windows has no way to associate that install with this one.
// Find it via its own old AppId's uninstall registry key and run its
// uninstaller silently before this install proceeds, so upgrading is a
// clean one-step swap instead of leaving a stale ATBWorkup entry behind.
const
  OldAppId = '{6F2B8A2E-6E7B-4E7B-9C3E-ATBWORKUP001}';

function GetOldUninstallString(): String;
var
  sUnInstPath: String;
  sUnInstallString: String;
begin
  sUnInstPath := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' + OldAppId + '_is1';
  sUnInstallString := '';
  if not RegQueryStringValue(HKLM, sUnInstPath, 'UninstallString', sUnInstallString) then
    RegQueryStringValue(HKCU, sUnInstPath, 'UninstallString', sUnInstallString);
  Result := sUnInstallString;
end;

function InitializeSetup(): Boolean;
var
  sUnInstallString: String;
  iResultCode: Integer;
begin
  Result := True;
  sUnInstallString := GetOldUninstallString();
  if sUnInstallString <> '' then
  begin
    sUnInstallString := RemoveQuotes(sUnInstallString);
    Exec(sUnInstallString, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '',
        SW_HIDE, ewWaitUntilTerminated, iResultCode);
  end;
end;
