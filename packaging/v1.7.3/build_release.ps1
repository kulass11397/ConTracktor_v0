param([string]$Compiler = (Join-Path $PSScriptRoot 'tools\InnoSetup\ISCC.exe'))
$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath $Compiler)) { throw 'Verified official Inno Setup compiler required.' }
foreach ($name in @('app.py','app_clean.py','README.md','UPDATE_GUIDE.txt')) {
    Copy-Item -LiteralPath $name -Destination (Join-Path 'release_payload' $name) -Force
}
$databases=Get-ChildItem -LiteralPath 'release_payload' -Recurse -File | Where-Object {
    $_.Name -match '\.(db|sqlite|sqlite3)(-(wal|shm|journal))?$'
}
if ($databases) { throw 'Safety check: database files cannot be packaged.' }
& $Compiler 'installer.iss'
if ($LASTEXITCODE -ne 0) { throw 'Standard installer compilation failed.' }
$output=Join-Path $PSScriptRoot 'release\ConTracktor_v1_Update_1.7.3.exe'
$hash=(Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  ConTracktor_v1_Update_1.7.3.exe" | Set-Content -LiteralPath 'release\SHA256SUMS.txt' -Encoding ascii
Write-Output ('INSTALLER='+$output)
