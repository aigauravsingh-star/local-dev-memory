from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings


def source_status() -> list[dict[str, str | bool]]:
    settings = get_settings()
    return [
        {
            "name": "Codex sessions",
            "source_path": str(path),
            "exists": path.exists(),
            "kind": "codex",
        }
        for path in settings.codex_session_roots()
    ]
