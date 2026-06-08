$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Python) { $Python = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $Python) { throw "Python 3.12 or the Windows py launcher is required." }
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw "npm.cmd is required." }

if (-not (Test-Path ".venv")) {
  if ($Python.EndsWith("py.exe")) { & $Python -3.12 -m venv .venv } else { & $Python -m venv .venv }
}
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
Push-Location frontend
& npm.cmd install
Pop-Location
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
Write-Host "Setup complete."
