#ifndef AppVersion
  #error AppVersion must be supplied by the build script
#endif

[Setup]
AppId={{B72C4133-68D8-45D8-9357-6168C979583C}
AppName=StockSwitch
AppVersion={#AppVersion}
AppVerName=StockSwitch {#AppVersion}
AppPublisher=StockSwitch Project
DefaultDirName={autopf}\StockSwitch
DefaultGroupName=StockSwitch
PrivilegesRequired=admin
OutputDir=..\release
OutputBaseFilename=StockSwitch-Setup-{#AppVersion}
SetupIconFile=..\assets\StockSwitch.ico
Compression=lzma
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\StockSwitch.exe

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\StockSwitch\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\StockSwitch"; Filename: "{app}\StockSwitch.exe"
Name: "{autodesktop}\StockSwitch"; Filename: "{app}\StockSwitch.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\StockSwitch.exe"; Description: "Launch StockSwitch"; Flags: nowait postinstall skipifsilent
