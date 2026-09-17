[Setup]
AppId={{2D69DEAF-5B45-48D8-9B1E-85AFA48C154D}
AppName=Zuhause am Bach - Rang & Preis
AppVersion=1.0.0
AppPublisher=Zuhause am Bach - Wachau
DefaultDirName={autopf}\Zuhause am Bach\RangPreis
DefaultGroupName=Zuhause am Bach
OutputDir=dist-installer
OutputBaseFilename=ZuhauseAmBach-RangPreis-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
WizardStyle=modern
UninstallDisplayName=Zuhause am Bach - Rang & Preis

[Files]
Source: "dist\ZuhauseAmBach-RangPreis.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Zuhause am Bach - Rang & Preis"; Filename: "{app}\ZuhauseAmBach-RangPreis.exe"
Name: "{autodesktop}\Zuhause am Bach - Rang & Preis"; Filename: "{app}\ZuhauseAmBach-RangPreis.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Desktop-Verknüpfung erstellen"; GroupDescription: "Zusätzliche Symbole:"; Flags: unchecked

[Run]
Filename: "{app}\ZuhauseAmBach-RangPreis.exe"; Description: "Programm starten"; Flags: nowait postinstall skipifsilent
