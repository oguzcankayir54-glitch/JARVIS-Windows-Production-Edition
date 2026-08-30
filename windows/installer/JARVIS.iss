#define JarvisVersion "2.0.1"
#define ProjectRoot "..\.."

[Setup]
AppId={{D878AC75-C44E-4EF7-A610-0551780D795A}
AppName=J.A.R.V.I.S.
AppVersion={#JarvisVersion}
AppPublisher=J.A.R.V.I.S.
DefaultDirName={localappdata}\Programs\JARVIS
DefaultGroupName=J.A.R.V.I.S.
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\release
OutputBaseFilename=JARVIS-Setup-{#JarvisVersion}
SetupIconFile=..\jarvis.ico
UninstallDisplayIcon={app}\JARVIS.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ChangesEnvironment=no

; Kaynaklar gecici bir klasore acilir. Mevcut PowerShell kurucusu bunlari
; %LOCALAPPDATA%\Programs\JARVIS altina yerlestirir ve kurulumdan sonra bu
; gecici kopya Inno Setup tarafindan otomatik silinir.
[Files]
Source: "{#ProjectRoot}\pyproject.toml"; DestDir: "{tmp}\jarvis-kaynak"; Flags: ignoreversion deleteafterinstall
Source: "{#ProjectRoot}\kimlik.json"; DestDir: "{tmp}\jarvis-kaynak"; Flags: ignoreversion deleteafterinstall
Source: "{#ProjectRoot}\README.md"; DestDir: "{tmp}\jarvis-kaynak"; Flags: ignoreversion deleteafterinstall
Source: "{#ProjectRoot}\jarvis\*"; DestDir: "{tmp}\jarvis-kaynak\jarvis"; Flags: ignoreversion recursesubdirs createallsubdirs deleteafterinstall; Excludes: "__pycache__\*,*.pyc"
; Panel HTML'i sunucu tarafında çalışma zamanında docs/mockups altından okunur.
; Kaynak listesine eklenmezse kurulum başarılı görünür ancak / paneli 500 döner.
Source: "{#ProjectRoot}\docs\mockups\jarvis-panel.html"; DestDir: "{tmp}\jarvis-kaynak\docs\mockups"; Flags: ignoreversion deleteafterinstall
Source: "{#ProjectRoot}\windows\JARVIS.exe"; DestDir: "{tmp}\jarvis-kaynak\windows"; Flags: ignoreversion deleteafterinstall
Source: "{#ProjectRoot}\windows\jarvis.ico"; DestDir: "{tmp}\jarvis-kaynak\windows"; Flags: ignoreversion deleteafterinstall
Source: "{#ProjectRoot}\windows\jarvis.ini"; DestDir: "{tmp}\jarvis-kaynak\windows"; Flags: ignoreversion deleteafterinstall
Source: "{#ProjectRoot}\windows\src\kur-windows.ps1"; DestDir: "{tmp}\jarvis-kaynak\windows\src"; Flags: ignoreversion deleteafterinstall
Source: "{#ProjectRoot}\windows\src\watchdog.ps1"; DestDir: "{tmp}\jarvis-kaynak\windows\src"; Flags: ignoreversion deleteafterinstall

[Run]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{tmp}\jarvis-kaynak\windows\src\kur-windows.ps1"" -Sessiz"; WorkingDir: "{tmp}\jarvis-kaynak"; Description: "J.A.R.V.I.S. dosyalarini ve Python ortamını kuruyor"; StatusMsg: "J.A.R.V.I.S. kuruluyor; Python paketleri indiriliyor..."; Flags: waituntilterminated

; PowerShell kurucusu da ayni adlarla kisayol olusturuyor. Bunlari burada
; bildirmek Inno Setup kaldiricisinin kisayollari guvenle temizlemesini saglar.
[Icons]
Name: "{autodesktop}\J.A.R.V.I.S."; Filename: "{app}\JARVIS.exe"; WorkingDir: "{app}"; IconFilename: "{app}\jarvis.ico"; Comment: "J.A.R.V.I.S. — kisisel teknik asistan"
Name: "{group}\J.A.R.V.I.S."; Filename: "{app}\JARVIS.exe"; WorkingDir: "{app}"; IconFilename: "{app}\jarvis.ico"; Comment: "J.A.R.V.I.S. — kisisel teknik asistan"

[UninstallDelete]
; Hafiza ve kullanici verileri {userprofile}\.jarvis altinda tutulur ve
; bilerek bu listenin disindadir.
Type: files; Name: "{userstartup}\J.A.R.V.I.S. Watchdog.lnk"
Type: filesandordirs; Name: "{app}\app"
Type: files; Name: "{app}\JARVIS.exe"
Type: files; Name: "{app}\jarvis.ico"
Type: files; Name: "{app}\jarvis.ini"
