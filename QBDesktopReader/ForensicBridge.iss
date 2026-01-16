; ForensicBridge Windows Installer
; Created with Inno Setup 6.x

#define MyAppName "ForensicBridge"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "ForensicBridge Inc."
#define MyAppURL "https://forensicbridge.io"
#define MyAppExeName "ForensicBridge.exe"

[Setup]
AppId={{12345678-1234-1234-1234-123456789012}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/support
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=installer
OutputBaseFilename=ForensicBridge_Setup_{#MyAppVersion}
SetupIconFile=assets\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin

; Signing (uncomment when you have a certificate)
; SignTool=signtool sign /tr http://timestamp.digicert.com /td sha256 /fd sha256 /a $f

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Main executable
Source: "publish\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; Configuration
Source: "config.json"; DestDir: "{app}"; Flags: ignoreversion

; Runtime dependencies (if not self-contained)
; Source: "publish\*.dll"; DestDir: "{app}"; Flags: ignoreversion

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

// Check for QBFC16 SDK
function IsQBFC16Installed: Boolean;
begin
  Result := FileExists(ExpandConstant('{commonpf32}\Intuit\IDN\QBFC16\Interop.QBFC16.dll'));
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  
  // Warn if QuickBooks is not installed
  if not IsQuickBooksInstalled then
  begin
    if MsgBox('QuickBooks Desktop does not appear to be installed.' + #13#10 +
              'ForensicBridge requires QuickBooks Desktop to extract data.' + #13#10#13#10 +
              'Do you want to continue anyway?', mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
      Exit;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    // Create config with server URL
    SaveStringToFile(ExpandConstant('{app}\config.json'),
      '{' + #13#10 +
      '  "serverUrl": "https://api.forensicbridge.io",' + #13#10 +
      '  "version": "1.0.0"' + #13#10 +
      '}', False);
  end;
end;

[Messages]
WelcomeLabel1=Welcome to ForensicBridge
WelcomeLabel2=This will install ForensicBridge on your computer.%n%nForensicBridge securely migrates QuickBooks Desktop data to QuickBooks Online with forensic verification.%n%nRequirements:%n- QuickBooks Desktop 2015 or later%n- Windows 10 or later
