; ForensicBridge Windows Installer
; Created with Inno Setup 6.x

#define MyAppName "ForensicBridge"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "ForensicBridge Inc."
#define MyAppURL "https://forensicbridge.ca"
#define MyAppExeName "ForensicBridge.exe"

[Setup]
AppId={{A7B8C9D0-E1F2-3456-7890-ABCDEF123456}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/support
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=Output
OutputBaseFilename=ForensicBridge-Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Main executable and all dependencies from publish directory
Source: "publish\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// Check if QuickBooks is installed
function IsQuickBooksInstalled: Boolean;
begin
  Result := RegKeyExists(HKEY_LOCAL_MACHINE, 'SOFTWARE\Intuit\QuickBooks');
  if not Result then
    Result := RegKeyExists(HKEY_LOCAL_MACHINE, 'SOFTWARE\WOW6432Node\Intuit\QuickBooks');
end;

function InitializeSetup(): Boolean;
begin
  Result := True;

  // Warn if QuickBooks is not installed (but don't block)
  if not IsQuickBooksInstalled then
  begin
    MsgBox('Note: QuickBooks Desktop was not detected on this machine.' + #13#10#13#10 +
           'ForensicBridge will be installed, but you will need QuickBooks Desktop ' +
           'and the QuickBooks SDK to extract data.' + #13#10#13#10 +
           'You can still use ForensicBridge to view existing extractions.',
           mbInformation, MB_OK);
  end;
end;

[Messages]
WelcomeLabel1=Welcome to ForensicBridge
WelcomeLabel2=This will install ForensicBridge on your computer.%n%nForensicBridge securely migrates QuickBooks Desktop data to QuickBooks Online with forensic verification.%n%nRequirements:%n- QuickBooks Desktop 2015 or later%n- Windows 10 or later
