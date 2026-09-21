$ErrorActionPreference='Stop'
$root=Join-Path $PSScriptRoot 'installer_test'
$appDir=Join-Path $root 'App'
$dataDir=Join-Path $root 'Data'
New-Item -ItemType Directory -Path $appDir,$dataDir -Force | Out-Null
$db=Join-Path $dataDir 'contractor_tracker.db'
Copy-Item -LiteralPath 'C:\Users\Kyle\Downloads\contractor_tracker_backup_20260918_134324.db' -Destination $db
$hash=(Get-FileHash -LiteralPath $db).Hash
$env:CONTRACTOR_INSTALL_TEST_DIR=$appDir
$env:CONTRACTOR_INSTALL_TEST_DATA_DIR=$dataDir
$env:CONTRACTOR_DB_PATH=$db
$env:CONTRACTOR_SMOKE_TEST='1'
$setup=Join-Path $PSScriptRoot 'release\ConTracktor_v1_Update_1.7.5.exe'
$args=@('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',('/DIR="'+$appDir+'"'),('/LOG="'+(Join-Path $root 'setup.log')+'"'))
$process=Start-Process -FilePath $setup -ArgumentList $args -WindowStyle Hidden -Wait -PassThru
if ($process.ExitCode -ne 0) { throw ('Installer failed: '+$process.ExitCode) }
if ((Get-FileHash -LiteralPath $db).Hash -ne $hash) { throw 'Installer altered the database.' }
$backup=Get-ChildItem -LiteralPath (Join-Path $dataDir 'Backups') -Recurse -File -Filter contractor_tracker.db | Select-Object -Last 1
if (-not $backup -or (Get-FileHash -LiteralPath $backup.FullName).Hash -ne $hash) { throw 'Database backup mismatch.' }
if (-not (Get-ChildItem -LiteralPath (Join-Path $root 'AppBackups') -Recurse -Filter sentinel.txt)) { throw 'Application backup missing.' }
if ((Get-FileHash -LiteralPath (Join-Path $appDir 'app.py')).Hash -ne (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'app.py')).Hash) { throw 'Installed source mismatch.' }
$launch=Start-Process -FilePath (Join-Path $appDir 'ConTracktor_v1.exe') -WindowStyle Hidden -Wait -PassThru
if ($launch.ExitCode -ne 0) { throw 'First app launch failed.' }
Write-Output 'Standard installer preserved the database byte-for-byte, created app/data backups and launched the app with its bundled runtime.'
