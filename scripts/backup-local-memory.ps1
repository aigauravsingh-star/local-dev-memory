$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dest = Join-Path $Root "local-memory-backup-$stamp"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
if (Test-Path "backend\dev.db") { Copy-Item "backend\dev.db" $dest }
if (Test-Path ".local_data") { Copy-Item ".local_data" (Join-Path $dest ".local_data") -Recurse -Force }
Compress-Archive -Path "$dest\*" -DestinationPath "$dest.zip" -Force
Remove-Item $dest -Recurse -Force
Write-Host "Backup written to $dest.zip"
