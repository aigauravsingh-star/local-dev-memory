from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_prefix="LDM_",
        extra="ignore",
    )

    database_url: str = "sqlite+aiosqlite:///./backend/dev.db"
    data_root: Path = Path("./.local_data")
    palace_path: Path = Path("./.local_data/palace")
    codex_sessions_dir: str | None = Field(default=None)
    allow_mock_memory: bool = True
    cors_origins: str = "http://localhost:8076,http://127.0.0.1:8076"

    @property
    def cors_origin_list(self) -> list[str]:
        return [part.strip() for part in self.cors_origins.split(",") if part.strip()]

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parents[3]

    @property
    def resolved_database_url(self) -> str:
        prefix = "sqlite+aiosqlite:///"
        if not self.database_url.startswith(prefix):
            return self.database_url
        raw_path = self.database_url[len(prefix) :]
        if raw_path in {":memory:", "/:memory:"}:
            return self.database_url
        db_path = Path(raw_path)
        if not db_path.is_absolute():
            db_path = (self.project_root / db_path).resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return prefix + quote(str(db_path).replace("\\", "/"), safe="/:")

    def codex_session_roots(self) -> list[Path]:
        roots: list[Path] = []
        candidates: list[str | None] = [
            self.codex_sessions_dir,
            str(Path(os.environ["CODEX_HOME"]) / "sessions") if os.environ.get("CODEX_HOME") else None,
            str(Path(os.environ["USERPROFILE"]) / ".codex" / "sessions") if os.environ.get("USERPROFILE") else None,
            str(Path(os.environ["HOME"]) / ".codex" / "sessions") if os.environ.get("HOME") else None,
        ]
        for raw in candidates:
            if not raw:
                continue
            expanded = Path(os.path.expandvars(os.path.expanduser(raw))).resolve()
            if expanded not in roots:
                roots.append(expanded)
        return roots


@lru_cache
def get_settings() -> Settings:
    return Settings()
