#define AppVersion "1.7.6"

[Setup]
AppId=ConTracktor_v1
AppName=ConTracktor_v1
AppVersion={#AppVersion}
AppPublisher=ConTracktor
AppPublisherURL=https://github.com/kulass11397/ConTracktor_v0
AppSupportURL=https://github.com/kulass11397/ConTracktor_v0/issues
DefaultDirName={localappdata}\Programs\ConTracktor_v1
DefaultGroupName=ConTracktor_v1
DisableProgramGroupPage=yes
DisableDirPage=yes
UsePreviousAppDir=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=release
OutputBaseFilename=ConTracktor_v1_Update_{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
Uninstallable=no
CreateUninstallRegKey=no
CloseApplications=yes
RestartApplications=no
InfoBeforeFile=UPDATE_GUIDE.txt
SetupLogging=yes

[Files]
Source: "release_payload\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "*.db,*.db-wal,*.db-shm,*.db-journal,*.sqlite,*.sqlite3,*.sqlite-wal,*.sqlite-shm,*.sqlite3-wal,*.sqlite3-shm,__pycache__\*"

[Icons]
Name: "{userdesktop}\ConTracktor_v1"; Filename: "{app}\ConTracktor_v1.exe"; WorkingDir: "{app}"; Check: not IsTestInstall
Name: "{userprograms}\ConTracktor_v1\ConTracktor_v1"; Filename: "{app}\ConTracktor_v1.exe"; WorkingDir: "{app}"; Check: not IsTestInstall

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConTracktor_v1"; ValueType: string; ValueName: "DisplayVersion"; ValueData: "{#AppVersion}"; Check: not IsTestInstall
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConTracktor_v1"; ValueType: string; ValueName: "InstallLocation"; ValueData: "{app}"; Check: not IsTestInstall

[Code]
function CreateFileW(lpFileName: String; dwDesiredAccess, dwShareMode: Cardinal;
  lpSecurityAttributes: Cardinal; dwCreationDisposition, dwFlagsAndAttributes: Cardinal;
  hTemplateFile: THandle): THandle;
  external 'CreateFileW@kernel32.dll stdcall';
function CloseHandle(hObject: THandle): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

function IsTestInstall: Boolean;
begin
  Result := GetEnv('CONTRACTOR_INSTALL_TEST_DIR') <> '';
end;

function DataDirectory: String;
var Requested: String;
begin
  Requested := GetEnv('CONTRACTOR_INSTALL_TEST_DATA_DIR');
  if Requested <> '' then begin Result := Requested; exit; end;
  Requested := GetEnv('CONTRACTOR_DB_PATH');
  if Requested <> '' then begin Result := ExtractFileDir(ExpandFileName(Requested)); exit; end;
  Result := ExpandConstant('{localappdata}\ConTracktor_v1\Data');
end;

function DatabaseFile: String;
begin
  if (GetEnv('CONTRACTOR_DB_PATH') <> '') and
     (GetEnv('CONTRACTOR_INSTALL_TEST_DATA_DIR') = '') then
    Result := ExpandFileName(GetEnv('CONTRACTOR_DB_PATH'))
  else Result := AddBackslash(DataDirectory) + 'contractor_tracker.db';
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var Handle: THandle;
begin
  Result := '';
  if FileExists(DatabaseFile) then begin
    Handle := CreateFileW(DatabaseFile, $80000000, 0, 0, 3, $80, 0);
    if Handle = THandle(-1) then begin
      Result := 'Close ConTracktor completely before updating. Its database is in use or cannot be backed up safely.';
      exit;
    end;
    CloseHandle(Handle);
  end;
end;

procedure CopyTree(Source, Destination: String);
var Entry: TFindRec; FromPath, ToPath: String;
begin
  if not ForceDirectories(Destination) then RaiseException('Cannot create safety backup folder: ' + Destination);
  if FindFirst(AddBackslash(Source) + '*', Entry) then begin
    try
      repeat
        if (Entry.Name <> '.') and (Entry.Name <> '..') then begin
          FromPath := AddBackslash(Source) + Entry.Name;
          ToPath := AddBackslash(Destination) + Entry.Name;
          if (Entry.Attributes and $400) <> 0 then
            RaiseException('An application folder link cannot be safely backed up: ' + FromPath);
          if (Entry.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then CopyTree(FromPath, ToPath)
          else if not FileCopy(FromPath, ToPath, True) then
            RaiseException('Cannot back up application file: ' + FromPath);
        end;
      until not FindNext(Entry);
    finally FindClose(Entry); end;
  end;
end;

procedure SafetyBackups;
var Stamp, AppBackup, DataBackup, SourceFile: String; Suffixes: TArrayOfString; I: Integer;
begin
  Stamp := GetDateTimeString('yyyymmdd_hhnnss_zzz', '-', ':');
  AppBackup := AddBackslash(ExtractFileDir(DataDirectory)) + 'AppBackups\Before_v{#AppVersion}_' + Stamp;
  if Pos(Lowercase(AddBackslash(ExpandConstant('{app}'))), Lowercase(AddBackslash(AppBackup))) = 1 then
    RaiseException('Backup folder must not be inside the application folder.');
  if DirExists(ExpandConstant('{app}')) then CopyTree(ExpandConstant('{app}'), AppBackup);
  if FileExists(DatabaseFile) then begin
    DataBackup := AddBackslash(DataDirectory) + 'Backups\Before_v{#AppVersion}_' + Stamp;
    if not ForceDirectories(DataBackup) then RaiseException('Cannot create database safety backup.');
    Suffixes := ['', '-wal', '-shm', '-journal'];
    for I := 0 to GetArrayLength(Suffixes) - 1 do begin
      SourceFile := DatabaseFile + Suffixes[I];
      if FileExists(SourceFile) and not FileCopy(SourceFile,
        AddBackslash(DataBackup) + ExtractFileName(SourceFile), True) then
        RaiseException('Cannot back up database file: ' + SourceFile);
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then SafetyBackups;
  if CurStep = ssPostInstall then begin
    if not ForceDirectories(DataDirectory) then RaiseException('Cannot create data directory.');
    if not SaveStringToFile(AddBackslash(DataDirectory) + 'LAST_INSTALLED_UPDATE.txt',
      'Version={#AppVersion}' + #13#10 + 'DatabasePreserved=True' + #13#10, False) then
      RaiseException('Cannot write installation receipt.');
  end;
end;
