; Paperdesk per-user installer (Inno Setup 6). scripts/build_windows.py passes the defines below.
; No administrator rights: installs to %LOCALAPPDATA%\Programs\Paperdesk. The library in
; %LOCALAPPDATA%\Paperdesk is user data; setup, updates and uninstall never touch it.
#ifndef AppVersion
  #error Build with scripts/build_windows.py
#endif

[Setup]
; Never change AppId: Windows uses it to recognise updates and the uninstall entry.
AppId={{E7E585E1-095C-4B44-87E8-325060F5F6BA}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Paperdesk contributors
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
VersionInfoVersion={#FileVersion}
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}
VersionInfoCopyright=Copyright 2026 Paperdesk contributors
PrivilegesRequired=lowest
DefaultDirName={userpf}\{#AppName}
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#OutputDir}
OutputBaseFilename={#OutputBaseFilename}
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\{#AppName}.exe
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
LZMAUseSeparateProcess=yes
LZMANumBlockThreads=4
; An update (also a silent one started by the updater) closes the running app first.
CloseApplications=force
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[CustomMessages]
english.WebView2Failed=Paperdesk needs the Microsoft Edge WebView2 Runtime, which could not be installed. Connect to the internet and run setup again, or install it from https://developer.microsoft.com/microsoft-edge/webview2/.
korean.WebView2Failed=Paperdesk에는 Microsoft Edge WebView2 런타임이 필요한데 설치하지 못했어요. 인터넷에 연결한 뒤 설치를 다시 실행하거나 https://developer.microsoft.com/microsoft-edge/webview2/ 에서 설치해 주세요.
japanese.WebView2Failed=Paperdesk には Microsoft Edge WebView2 ランタイムが必要ですが、インストールできませんでした。インターネットに接続してセットアップを再実行するか、https://developer.microsoft.com/microsoft-edge/webview2/ からインストールしてください。

[InstallDelete]
; Replace the previous version's program files completely so stale modules are never loaded.
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\analysis-runtime"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppName}.exe"

[Run]
Filename: "{app}\{#AppName}.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
const
  WebView2Client = 'Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  // Microsoft's Evergreen bootstrapper. It is downloaded only when missing and never bundled.
  WebView2Bootstrapper = 'https://go.microsoft.com/fwlink/p/?LinkId=2124703';

var
  DownloadPage: TDownloadWizardPage;

function WebView2Installed: Boolean;
var
  Version: String;
begin
  Result := (RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\' + WebView2Client, 'pv', Version) or
             RegQueryStringValue(HKCU, 'Software\' + WebView2Client, 'pv', Version)) and
            (Version <> '') and (Version <> '0.0.0.0');
end;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage(SetupMessage(msgWizardPreparing), SetupMessage(msgPreparingDesc), nil);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  if WebView2Installed then
    Exit;
  DownloadPage.Clear;
  DownloadPage.Add(WebView2Bootstrapper, 'MicrosoftEdgeWebview2Setup.exe', '');
  DownloadPage.Show;
  try
    try
      DownloadPage.Download;
      Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    except
      Log(GetExceptionMessage);
    end;
  finally
    DownloadPage.Hide;
  end;
  if not WebView2Installed then
    Result := CustomMessage('WebView2Failed');
end;
