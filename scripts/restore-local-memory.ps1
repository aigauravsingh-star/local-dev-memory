param([Parameter(Mandatory=$true)][string]$BackupZip)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
if (-not (Test-Path $BackupZip)) { throw "Backup not found: $BackupZip" }
$answer = Read-Host "Restore will replace backend\dev.db and .local_data if present. Type RESTORE to continue"
if ($answer -ne "RESTORE") { Write-Host "Restore cancelled."; exit 0 }
$tmp = Join-Path $Root ".restore_tmp"
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
Expand-Archive -Path $BackupZip -DestinationPath $tmp -Force
if (Test-Path "$tmp\dev.db") { Copy-Item "$tmp\dev.db" "backend\dev.db" -Force }
if (Test-Path "$tmp\.local_data") {
  if (Test-Path ".local_data") { Remove-Item ".local_data" -Recurse -Force }
  Copy-Item "$tmp\.local_data" ".local_data" -Recurse -Force
}
Remove-Item $tmp -Recurse -Force
Write-Host "Restore complete."
