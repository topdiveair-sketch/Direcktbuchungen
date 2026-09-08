#define MyAppName "WachauEtappe Zentrale"
#define MyAppVersion "1.0.0"
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

[Tasks]
Name: "desktopicon"; Description: "Desktop-Verknüpfung erstellen"; GroupDescription: "Zusätzliche Verknüpfungen:"; Flags: unchecked

[Files]
Source: "..\..\..\artifacts\WachauEtappe-Zentrale\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\WachauEtappe.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\WachauEtappe.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "WachauEtappe Zentrale starten"; Flags: nowait postinstall skipifsilent
