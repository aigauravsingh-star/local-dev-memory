# Setup

## Windows Setup

```powershell
cd local-dev-memory
powershell -ExecutionPolicy Bypass -File .\scripts\setup-once.ps1
```

The script checks Python and `npm.cmd`, creates `.venv`, installs backend requirements, runs `npm install`, and copies `.env.example` to `.env` when needed.

## Manual Startup

Backend:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-backend.ps1
```

Frontend:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-frontend.ps1
```

Combined:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-local-dev-memory.ps1
```

## Preflight

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\preflight.ps1
```

This checks `.env`, `.venv`, `frontend/node_modules`, `LDM_DATABASE_URL`, the Codex sessions path, and whether ports `8176` or `8076` are already in use.

## Troubleshooting

### SQLite Path Issues

The default database URL is:

```text
sqlite+aiosqlite:///./backend/dev.db
```

Run startup scripts from the project root so the relative path resolves correctly. You can set an absolute SQLite path in `.env`.

### Missing Codex Sessions

Check `LDM_CODEX_SESSIONS_DIR` in `.env`. The importer also looks at `CODEX_HOME/sessions`, `%USERPROFILE%\.codex\sessions`, and `$HOME/.codex/sessions`.

### Port Conflicts

Run `scripts\preflight.ps1`. If a port is busy, stop the other process or edit the corresponding startup script and frontend API URL.

### Frontend CORS Errors

Ensure `.env` includes:

```text
LDM_CORS_ORIGINS=http://localhost:8076,http://127.0.0.1:8076
```

Restart the backend after changing `.env`.

### Optional MemPalace/Chroma Failures

MemPalace is optional. If a local fork or local indexing boundary fails, the import still completes using built-in normalization and records the message in `memory_error`.

## Backup and Restore

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\backup-local-memory.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\restore-local-memory.ps1 -BackupZip .\local-memory-backup-YYYYMMDD-HHMMSS.zip
```
