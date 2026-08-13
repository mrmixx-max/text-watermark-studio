; Inno Setup script — Text Watermark Studio (Windows desktop app)
; Compile after the PyInstaller build (expects dist\tws-desktop.exe):
;   iscc packaging\tws-setup.iss          -> dist\TWS-Setup.exe
; Inno Setup 6 (choco install innosetup). No icon asset yet -> default icon.

#define MyAppName "Text Watermark Studio"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "Erik Gieske"
#define MyAppExeName "tws-desktop.exe"

[Setup]
AppId={{9F6E4C21-7D8B-4A3E-B5C2-0F1D9E8A7C33}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\TextWatermarkStudio
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=TWS-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; 64-bit-only client (x64compatible = Inno 6.3+; rejects 32-bit Windows)
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Uninstaller keeps the registry/keys the user placed next to the app
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
