; Version is written by build_windows.py into _version.iss before this
; file is compiled.  The fallback is only used if someone runs iscc by
; hand without the build script.
#define VersionFile AddBackslash(SourcePath) + "_version.iss"
#define AppVersion FileExists(VersionFile) ? \
    Trim(ReadIni(VersionFile, "build", "version", "1.2.3")) : "1.2.3"

#define AppName "AuthorBoard"
#define AppPublisher "Vibrantic"
#define AppExeName "AuthorBoard.exe"

[Setup]
AppId={{8E4B2C1A-7F3D-4A9E-B5C6-1D2E3F4A5B6C}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Per-user install: no admin prompt, and the updater can replace the folder.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=Output
OutputBaseFilename=AuthorBoard-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExeName}
; Windows 10+ only (Qt 6 requirement).
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The whole PyInstaller onedir folder, including AuthorBoardUpdater\.
Source: "..\dist\AuthorBoard\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\AuthorBoardUpdater\*"; DestDir: "{app}\updater"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Stop the app before uninstalling, otherwise the uninstaller can't delete the exe.
Filename: "taskkill"; Parameters: "/F /IM {#AppExeName}"; Flags: runhidden; RunOnceId: "StopAuthorBoard"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;