# local-dev-memory

A standalone, local-only developer memory dashboard for browsing, importing, searching, inspecting, and exporting local Codex coding sessions, then connecting them to local Git commits and changed files.

Product promise: searchable local memory for AI-assisted development. The app helps answer what the user asked for, what changed, why it changed, which files/commits prove it, what commands/tests ran, what errors appeared, and what remains unresolved.

## Safety Boundaries

- Runs locally on your machine.
- Does not modify product repositories.
- Does not install Git hooks.
- Does not change global Git config.
- Does not call hosted LLM APIs during normal runtime.
- Does not upload transcripts, repository metadata, local paths, commits, or exports.
- Keeps runtime state under `.local_data/` and the configured local database.
- Uses `git -c safe.directory=<repo> -C <repo>` for repository inspection.
- Delete controls remove the local index entry only; original Codex rollout files are left untouched.
- Clear local index removes all indexed session rows from the local database only; original Codex rollout files and repositories are left untouched.

## Ports

- Backend API: `http://127.0.0.1:8176`
- Frontend dashboard: `http://localhost:8076`

## Layout

- `backend/`: FastAPI, SQLAlchemy async ORM, Pydantic v2.
- `frontend/`: React, webpack, plain CSS.
- `scripts/`: Windows-first PowerShell setup, preflight, startup, backup, restore.
- `.local_data/`: runtime memory copies and normalized transcripts, gitignored.
- `mempalace_fork/`: optional local-only boundary for a MemPalace fork.

## Quick Start

```powershell
cd local-dev-memory
powershell -ExecutionPolicy Bypass -File .\scripts\setup-once.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start-local-dev-memory.ps1
```

Open `http://localhost:8076`.

## Session Flow

Use the dashboard to select a date/session, inspect the derived session intelligence, search by repo/file/commit/text, link a Git commit by SHA, and export a selected session as JSON or Markdown. Export all sessions from `/api/v1/export/sessions.jsonl`.

Codex imports copy the source JSONL into `.local_data/memory_sessions/<session_id>/ingest/` and write a normalized transcript to `.local_data/memory_sessions/<session_id>/transcript/normalized_transcript.txt`.

Each imported session derives:

- user goal and session title
- human-readable summary and outcome
- decision snippets and reasoning evidence
- changed or referenced files
- linked or referenced commits
- commands, test/build signals, errors, warnings, and open follow-ups
- recent conversation turns and raw transcript access behind expand/collapse UI

## First Run

If no Codex sessions are detected, use Settings to confirm the local Codex session source. The dashboard also includes a demo session action so a new user can explore Summary, Search, Timeline, Export, and local index controls without importing real data.

Use `Refresh local index` after adding a source or changing source files. Use `Clear local index` only when you want to rebuild the local database from the source files.

## Query Model

Search is local-only over `session_search_docs`. Queries are classified as `file`, `commit`, `reason`, or `generic`. SQLite uses `LIKE` matching. PostgreSQL URLs are accepted through `LDM_DATABASE_URL`; the schema is compatible with asyncpg.

Results include local evidence summaries with likely reason, supporting evidence, related files, and related commits. Obvious secrets such as API keys, bearer tokens, private keys, passwords, and connection strings are redacted before indexing and display.

Search scope can be set to all sessions or the currently selected session.

## Limitations

This app indexes local transcript evidence and Git metadata; it does not infer new facts with hosted models. MemPalace integration is intentionally optional and local. If that boundary is unavailable or fails, built-in transcript normalization keeps the app usable and records the error on the session.
