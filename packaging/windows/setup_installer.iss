; FRIDAY native Windows installation wizard. Publisher: techobux.
#define MyAppName "FRIDAY"
#define MyAppVersion "56.0.0"
#define MyAppPublisher "techobux"
#define MyAppExeName "FRIDAY.exe"
#ifndef AppSourceDir
  #define AppSourceDir "..\..\dist\windows\FRIDAY"
#endif
#ifndef OutputDir
  #define OutputDir "..\..\dist\windows"
#endif
[Setup]
AppId={{E581A12F-468B-4A42-9907-D8A8A1E7F14D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoCompany={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}
VersionInfoCopyright=Copyright (c) 2026 techobux
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=FRIDAY_Setup_{#MyAppVersion}_x64
SetupIconFile=..\..\config\friday.ico
LicenseFile=..\..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.19041
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=yes
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupicon"; Description: "Launch FRIDAY when I sign in to Windows"; Flags: unchecked
[Files]
Source: "{#AppSourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startupicon
[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
; Private settings and memories live outside {app}; uninstallation preserves them.
