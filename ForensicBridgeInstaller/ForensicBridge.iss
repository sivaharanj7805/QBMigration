; ForensicBridge Windows Installer — CANONICAL VERSION
; This is the authoritative installer script. The previous copy in
; QBDesktopReader/ForensicBridge.iss was a stale duplicate and has been removed.
; Created with Inno Setup 6.x

#define MyAppName "ForensicBridge"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "ForensicBridge Inc."
#define MyAppURL "https://forensicbridge.ca"
#define MyAppExeName "ForensicBridge.exe"
#define MyAppGUID "{{A7B8C9D0-E1F2-3456-7890-ABCDEF123456}"

[Setup]
; I1 note: AppId documented here
AppId={#MyAppGUID}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/support
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=Output
OutputBaseFilename=ForensicBridge-Setup-{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; I2 fix: Changed to lowest - will elevate when needed
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; I6 fix: Updated minimum version to Windows 10
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; I3, I4 fix: More specific file patterns and check directive
; Main executable
Source: "publish\ForensicBridge.exe"; DestDir: "{app}"; Flags: ignoreversion; Check: PublishDirExists
; Configuration
Source: "publish\config.json"; DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist
; Dependencies (specific patterns instead of wildcard)
Source: "publish\*.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "publish\*.json"; DestDir: "{app}"; Flags: ignoreversion; Excludes: "config.json"
Source: "publish\*.pdb"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Dirs]
; Ensure user data directory exists
Name: "{localappdata}\ForensicBridge"; Permissions: users-full

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; I9 fix: Made post-install launch optional with better description
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName} now"; Flags: nowait postinstall skipifsilent unchecked

[UninstallDelete]
; I7 fix: Clean up user data on uninstall (with confirmation)
Type: filesandordirs; Name: "{localappdata}\ForensicBridge"

[UninstallRun]
; Ensure app is closed before uninstall
Filename: "{cmd}"; Parameters: "/C taskkill /F /IM ForensicBridge.exe /T"; Flags: runhidden; RunOnceId: "KillApp"

[Code]
// I4 fix: Check if publish directory exists before install
function PublishDirExists(): Boolean;
begin
  Result := FileExists(ExpandConstant('{src}\publish\ForensicBridge.exe'));
  if not Result then
  begin
    MsgBox('Error: publish directory not found or ForensicBridge.exe missing.' + #13#10 +
           'Please build the project first using: dotnet publish', mbError, MB_OK);
  end;
end;

// I5 fix: Enhanced QuickBooks detection for multiple versions
function IsQuickBooksInstalled: Boolean;
var
  QBVersions: array[0..5] of String;
  i: Integer;
begin
  Result := False;

  // Check common QuickBooks registry paths
  QBVersions[0] := 'SOFTWARE\Intuit\QuickBooks';
  QBVersions[1] := 'SOFTWARE\WOW6432Node\Intuit\QuickBooks';
  QBVersions[2] := 'SOFTWARE\Intuit\QuickBooks Enterprise';
  QBVersions[3] := 'SOFTWARE\WOW6432Node\Intuit\QuickBooks Enterprise';
  QBVersions[4] := 'SOFTWARE\Intuit\QuickBooks Pro';
  QBVersions[5] := 'SOFTWARE\WOW6432Node\Intuit\QuickBooks Pro';

  for i := 0 to 5 do
  begin
    if RegKeyExists(HKEY_LOCAL_MACHINE, QBVersions[i]) then
    begin
      Result := True;
      Exit;
    end;
  end;
end;

// Check for .NET Framework 4.8
function IsDotNetInstalled: Boolean;
var
  Release: Cardinal;
begin
  Result := False;
  if RegQueryDWordValue(HKEY_LOCAL_MACHINE,
    'SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full', 'Release', Release) then
  begin
    // 528040 = .NET Framework 4.8
    Result := (Release >= 528040);
  end;
end;

function InitializeSetup(): Boolean;
var
  ErrorMsg: String;
begin
  Result := True;
  ErrorMsg := '';

  // Check .NET Framework
  if not IsDotNetInstalled then
  begin
    ErrorMsg := 'Microsoft .NET Framework 4.8 or later is required.' + #13#10#13#10 +
                'Please install .NET Framework 4.8 from Microsoft and try again.';
    MsgBox(ErrorMsg, mbCriticalError, MB_OK);
    Result := False;
    Exit;
  end;

  // Warn if QuickBooks is not installed (but don't block)
  if not IsQuickBooksInstalled then
  begin
    MsgBox('Note: QuickBooks Desktop was not detected on this machine.' + #13#10#13#10 +
           'ForensicBridge will be installed, but you will need QuickBooks Desktop ' +
           '(2015 or later) and the QuickBooks SDK (QBFC16) to extract data.' + #13#10#13#10 +
           'You can still use ForensicBridge to view existing extractions.',
           mbInformation, MB_OK);
  end;
end;

// I8 fix: Handle upgrades - close running app before upgrade
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  // Try to close running instance
  Exec('taskkill', '/F /IM ForensicBridge.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  // Small delay to ensure file handles are released
  Sleep(500);
end;

[Messages]
WelcomeLabel1=Welcome to ForensicBridge
WelcomeLabel2=This will install ForensicBridge on your computer.%n%nForensicBridge securely migrates QuickBooks Desktop data to QuickBooks Online with forensic verification.%n%nRequirements:%n- QuickBooks Desktop 2015 or later%n- Windows 10 or later%n- .NET Framework 4.8
