; The Windows installer. Compiled by packaging/build.py, which passes
; Version, Source (the folder to install), Out and Name.
;
; Installs for the current user only: no administrator needed, and nothing
; outside the user's own folders is touched. The data (listings, photos,
; settings) lives in the user's folder "Troedel" and is neither installed
; nor removed here.

[Setup]
AppId={{2ABEB194-1CE0-464E-91EC-4717D72B56C8}
AppName=Trödel
AppVersion={#Version}
AppPublisher=Trödel
AppPublisherURL=https://github.com/tk-void/troedel
DefaultDirName={autopf}\Troedel
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#Out}
OutputBaseFilename={#Name}
SetupIconFile={#Source}\troedel.ico
UninstallDisplayIcon={app}\troedel.ico
UninstallDisplayName=Trödel
LicenseFile={#Source}\LICENSE.txt
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; An update must not leave packages of the version before lying around.
Type: filesandordirs; Name: "{app}\python"

[Files]
Source: "{#Source}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Trödel"; Filename: "{app}\python\pythonw.exe"; Parameters: "-I -m troedel window"; WorkingDir: "{app}"; IconFilename: "{app}\troedel.ico"
Name: "{autodesktop}\Trödel"; Filename: "{app}\python\pythonw.exe"; Parameters: "-I -m troedel window"; WorkingDir: "{app}"; IconFilename: "{app}\troedel.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: "-I -m troedel window"; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,Trödel}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Python writes compiled files next to its sources while running.
Type: filesandordirs; Name: "{app}\python"
