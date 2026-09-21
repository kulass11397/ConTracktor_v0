param(
    [string]$Repository = "kulass11397/ConTracktor_v0",
    [string]$Tag = "v1.7.5",
    [switch]$ReplaceExisting
)

$ErrorActionPreference = "Stop"
$credentialProcess = New-Object System.Diagnostics.Process
$credentialProcess.StartInfo = New-Object System.Diagnostics.ProcessStartInfo
$credentialProcess.StartInfo.FileName = "git"
$credentialProcess.StartInfo.Arguments = "credential fill"
$credentialProcess.StartInfo.UseShellExecute = $false
$credentialProcess.StartInfo.RedirectStandardInput = $true
$credentialProcess.StartInfo.RedirectStandardOutput = $true
$credentialProcess.StartInfo.RedirectStandardError = $true
[void]$credentialProcess.Start()
$credentialProcess.StandardInput.WriteLine("protocol=https")
$credentialProcess.StandardInput.WriteLine("host=github.com")
$credentialProcess.StandardInput.WriteLine("username=kulass11397")
$credentialProcess.StandardInput.WriteLine("")
$credentialProcess.StandardInput.Close()
$credentialText = $credentialProcess.StandardOutput.ReadToEnd()
$credentialError = $credentialProcess.StandardError.ReadToEnd()
$credentialProcess.WaitForExit()
if ($credentialProcess.ExitCode -ne 0) {
    throw "GitHub credentials were not available from Windows Credential Manager. $credentialError"
}
$credentials = @{}
foreach ($line in ($credentialText -split "`r?`n")) {
    $separator = $line.IndexOf("=")
    if ($separator -gt 0) {
        $credentials[$line.Substring(0, $separator)] = $line.Substring($separator + 1)
    }
}
$token = $credentials["password"]
if ([string]::IsNullOrWhiteSpace($token)) {
    throw "GitHub authentication is missing. Push the branch once from this computer, then retry."
}
$headers = @{
    Authorization = "Bearer $token"
    Accept = "application/vnd.github+json"
    "X-GitHub-Api-Version" = "2022-11-28"
    "User-Agent" = "ConTracktor-Release-Publisher"
}

$apiRoot = "https://api.github.com/repos/$Repository"
$notes = [System.IO.File]::ReadAllText((Join-Path $PSScriptRoot "RELEASE_NOTES.md"))
$releasePayload = @{
    tag_name = $Tag
    target_commitish = "ConTracktor_v1"
    name = "ConTracktor $Tag"
    body = $notes
    draft = $false
    prerelease = $true
    make_latest = 'false'
    generate_release_notes = $false
} | ConvertTo-Json
$releasePayloadBytes = [System.Text.Encoding]::UTF8.GetBytes($releasePayload)

try {
    $release = Invoke-RestMethod -Method Get -Uri "$apiRoot/releases/tags/$Tag" -Headers $headers
} catch {
    if ($_.Exception.Response.StatusCode.value__ -ne 404) { throw }
    $release = Invoke-RestMethod -Method Post -Uri "$apiRoot/releases" -Headers $headers `
        -ContentType "application/json; charset=utf-8" -Body $releasePayloadBytes
}

$assetPaths = @(
    (Join-Path $PSScriptRoot "release\ConTracktor_v1_Update_1.7.5.exe"),
    (Join-Path $PSScriptRoot "release\SHA256SUMS.txt")
)
foreach ($assetPath in $assetPaths) {
    if (-not (Test-Path -LiteralPath $assetPath)) { throw "Release asset missing: $assetPath" }
    $assetName = [System.IO.Path]::GetFileName($assetPath)
    $existing = @($release.assets | Where-Object { $_.name -eq $assetName })
    if ($existing.Count -gt 0) {
        if (-not $ReplaceExisting) {
            throw "Release asset already exists and was not overwritten: $assetName"
        }
        foreach ($asset in $existing) {
            Invoke-RestMethod -Method Delete -Uri "$apiRoot/releases/assets/$($asset.id)" `
                -Headers $headers
        }
    }
    $encodedName = [System.Uri]::EscapeDataString($assetName)
    $uploadUri = "https://uploads.github.com/repos/$Repository/releases/$($release.id)/assets?name=$encodedName"
    $bytes = [System.IO.File]::ReadAllBytes($assetPath)
    [void](Invoke-RestMethod -Method Post -Uri $uploadUri -Headers $headers `
        -ContentType "application/octet-stream" -Body $bytes)
}

Write-Output ("RELEASE_URL=" + $release.html_url)
Write-Output ("RELEASE_ID=" + $release.id)
Write-Output ("ASSETS_UPLOADED=" + $assetPaths.Count)
