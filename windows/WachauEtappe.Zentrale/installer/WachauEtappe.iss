#define MyAppName "WachauEtappe Zentrale"
#define MyAppVersion "1.0.1"
#define MyAppPublisher "WachauEtappe"
#define MyAppExeName "WachauEtappe.Zentrale.exe"

[Setup]
AppId={{B19AAB23-9E4E-4DCE-B0D6-2A21E70F50BE}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\WachauEtappe Zentrale
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\..\artifacts\installer
OutputBaseFilename=WachauEtappe-Zentrale-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#MyAppName}
SetupLogging=yes
SetupIconFile=..\Assets\WachauEtappe.ico
UninstallDisplayIcon={app}\WachauEtappe.ico

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Files]
Source: "..\..\..\artifacts\WachauEtappe-Zentrale\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\Assets\WachauEtappe.ico"; DestDir: "{app}"; DestName: "WachauEtappe.ico"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\WachauEtappe.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\WachauEtappe.ico"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "WachauEtappe Zentrale starten"; Flags: nowait postinstall skipifsilent
