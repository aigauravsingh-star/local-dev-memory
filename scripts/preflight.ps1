$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Check-Port($Port) {
  $inUse = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
  if ($inUse) { Write-Warning "Port $Port is already in use. Stop that process or edit the startup script port." }
  else { Write-Host "Port $Port is available." }
}

if (-not (Test-Path ".env")) { Write-Warning ".env is missing. Run scripts\setup-once.ps1 or copy .env.example to .env." }
if (-not (Test-Path ".venv")) { Write-Warning ".venv is missing. Run scripts\setup-once.ps1." }
if (-not (Test-Path "frontend\node_modules")) { Write-Warning "frontend\node_modules is missing. Run scripts\setup-once.ps1." }

$envFile = if (Test-Path ".env") { Get-Content ".env" } else { Get-Content ".env.example" }
$db = ($envFile | Where-Object { $_ -like "LDM_DATABASE_URL=*" }) -replace "LDM_DATABASE_URL=", ""
Write-Host "LDM_DATABASE_URL=$db"

$codex = ($envFile | Where-Object { $_ -like "LDM_CODEX_SESSIONS_DIR=*" }) -replace "LDM_CODEX_SESSIONS_DIR=", ""
$codex = [Environment]::ExpandEnvironmentVariables($codex)
if (-not (Test-Path $codex)) { Write-Warning "Codex sessions directory not found: $codex" } else { Write-Host "Codex sessions directory exists: $codex" }

Check-Port 8176
Check-Port 8076
