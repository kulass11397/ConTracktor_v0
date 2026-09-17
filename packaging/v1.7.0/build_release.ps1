param([string]$Python = "python")

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$Compiler = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path -LiteralPath $Compiler)) { throw "The Windows C# compiler was not found." }

Copy-Item -LiteralPath "app.py" -Destination "release_payload\app.py" -Force
Copy-Item -LiteralPath "app_clean.py" -Destination "release_payload\app_clean.py" -Force
Copy-Item -LiteralPath "README.md" -Destination "release_payload\README.md" -Force
Copy-Item -LiteralPath "UPDATE_GUIDE.txt" -Destination "release_payload\UPDATE_GUIDE.txt" -Force
$databaseFiles = Get-ChildItem -LiteralPath "release_payload" -Recurse -File | Where-Object {
    $_.Name -match '\.(db|sqlite|sqlite3)(-wal|-shm)?$' -or
    $_.Name -match '\.(db|sqlite|sqlite3)-(wal|shm)$'
}
if ($databaseFiles) {
    throw "Safety check failed: the update payload contains a database file: $($databaseFiles.FullName -join ', ')"
}
& $Compiler /nologo /target:winexe /platform:x64 /reference:System.Windows.Forms.dll `
    /out:"release_payload\ConTracktor_v1.exe" "launcher.cs"
if (Test-Path -LiteralPath "payload.zip") { Remove-Item -LiteralPath "payload.zip" -Force }
tar -a -cf "payload.zip" -C "release_payload" .
if ($LASTEXITCODE -ne 0) { throw "The installer payload could not be compressed." }
New-Item -ItemType Directory -Path "release" -Force | Out-Null
$Payload = (Resolve-Path "payload.zip").Path
$InstallerOutput = (Resolve-Path "release").Path + "\ConTracktor_v1_Update_1.7.0.exe"
& $Compiler /nologo /target:winexe /platform:x64 `
    /reference:System.Windows.Forms.dll /reference:System.IO.Compression.dll `
    /reference:System.IO.Compression.FileSystem.dll `
    "/resource:$Payload,payload.zip" "/out:$InstallerOutput" "installer.cs"

$hash = (Get-FileHash -LiteralPath $InstallerOutput -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  ConTracktor_v1_Update_1.7.0.exe" | Set-Content -LiteralPath "release\SHA256SUMS.txt" -Encoding ascii
Write-Host "Installer created: $InstallerOutput"
