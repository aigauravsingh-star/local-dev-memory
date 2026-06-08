from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import get_settings
from app.core.memory import discover_codex_sessions, normalize_to_local_memory, parse_codex_jsonl, parsed_to_docs, parse_timestamp
from app.core.text_utils import build_summary, redact_secrets
from app.models.entities import AgentSource, Session, SessionEvent, SessionFile, SessionSearchDoc
from app.schemas.api import ImportCodexIn

router = APIRouter(prefix="/imports", tags=["imports"])


async def configured_source_roots(db: AsyncSession) -> list[str]:
    return list((await db.scalars(select(AgentSource.source_path).where(AgentSource.enabled.is_(True)))).all())


async def import_roots(db: AsyncSession) -> list[Path]:
    roots = [path.resolve() for path in get_settings().codex_session_roots()]
    for raw in await configured_source_roots(db):
        root = Path(raw).expanduser().resolve()
        if root not in roots:
            roots.append(root)
    return roots


def is_under(path: Path, roots: list[Path]) -> bool:
    return any(path == root or root in path.parents for root in roots)


@router.get("/codex-sessions")
async def list_codex_sessions(limit: int = 20, db: AsyncSession = Depends(get_db)):
    imported = set((await db.scalars(select(Session.memory_source_path))).all())
    existing_sources = set((await db.scalars(select(Session.memory_source_path))).all())
    items = []
    for parsed in discover_codex_sessions(limit, await configured_source_roots(db)):
        items.append(
            {
                "session_id": parsed.session_id,
                "source_path": parsed.source_path,
                "file_name": Path(parsed.source_path).name,
                "prompt_preview": parsed.prompt_preview,
                "repo_path": parsed.repo_path,
                "branch_name": parsed.branch_name,
                "modified_time": parsed.modified_time,
                "imported": parsed.source_path in imported or parsed.source_path in existing_sources,
            }
        )
    return items


@router.post("/codex-sessions")
async def import_codex_session(payload: ImportCodexIn, db: AsyncSession = Depends(get_db)):
    source = str(Path(payload.source_path).resolve())
    source_path = Path(source)
    roots = await import_roots(db)
    if not source_path.exists() or not source_path.is_file() or source_path.suffix.lower() != ".jsonl":
        raise HTTPException(400, "source_path must be an existing .jsonl file")
    if roots and not is_under(source_path, roots):
        raise HTTPException(400, "source_path must be under a detected or configured coding-agent source")
    existing = await db.scalar(select(Session).where(Session.memory_source_path == source))
    if existing:
        return {"duplicate": True, "session_id": existing.id}
    parsed = parse_codex_jsonl(source)
    existing_by_id = await db.get(Session, parsed.session_id)
    if existing_by_id:
        return {"duplicate": True, "session_id": existing_by_id.id}
    memory = normalize_to_local_memory(parsed)
    session = Session(
        id=parsed.session_id,
        feature_title=parsed.prompt_preview or Path(source).name,
        repo_path=parsed.repo_path,
        repo_name=Path(parsed.repo_path).name if parsed.repo_path else None,
        branch_name=parsed.branch_name,
        status="closed",
        start_time=parsed.start_time,
        end_time=parsed.end_time,
        session_summary=build_summary(parsed.transcript_text, parsed.prompt_preview),
        memory_ref=memory["memory_ref"],
        memory_source_path=source,
        memory_error=memory["memory_error"],
        raw_source_text=redact_secrets(parsed.raw_source_text),
        transcript_text=redact_secrets(parsed.transcript_text),
    )
    db.add(session)
    await db.flush()
    for event in parsed.events[:1000]:
        redacted_event = json.loads(redact_secrets(json.dumps(event, default=str)))
        db.add(
            SessionEvent(
                session_id=session.id,
                event_type=str(event.get("type") or "event"),
                message=None,
                payload_json=json.dumps(redacted_event, default=str),
                event_time=parse_timestamp(event.get("timestamp")),
            )
        )
    for ref in parsed.file_refs:
        db.add(SessionFile(session_id=session.id, file_path=ref))
    for doc in parsed_to_docs(parsed):
        db.add(SessionSearchDoc(session_id=session.id, **doc))
    await db.commit()
    return {"duplicate": False, "session_id": session.id}


@router.post("/codex-sessions/reindex")
async def reindex_codex_sessions(db: AsyncSession = Depends(get_db)):
    sessions = (await db.scalars(select(Session).where(Session.raw_source_text.is_not(None)))).all()
    total = 0
    refreshed = 0
    for session in sessions:
        await db.execute(delete(SessionSearchDoc).where(SessionSearchDoc.session_id == session.id))
        await db.execute(delete(SessionEvent).where(SessionEvent.session_id == session.id))
        await db.execute(
            delete(SessionFile).where(SessionFile.session_id == session.id, SessionFile.session_commit_id.is_(None))
        )
        docs = []
        if session.memory_source_path:
            try:
                parsed = parse_codex_jsonl(session.memory_source_path)
                memory = normalize_to_local_memory(parsed)
                session.feature_title = parsed.prompt_preview or session.feature_title
                session.repo_path = parsed.repo_path or session.repo_path
                session.repo_name = Path(parsed.repo_path).name if parsed.repo_path else session.repo_name
                session.branch_name = parsed.branch_name or session.branch_name
                session.start_time = parsed.start_time or session.start_time
                session.end_time = parsed.end_time or session.end_time
                session.session_summary = build_summary(parsed.transcript_text, parsed.prompt_preview or session.feature_title)
                session.memory_ref = memory["memory_ref"]
                session.memory_error = memory["memory_error"]
                session.raw_source_text = redact_secrets(parsed.raw_source_text)
                session.transcript_text = redact_secrets(parsed.transcript_text)
                for event in parsed.events[:1000]:
                    redacted_event = json.loads(redact_secrets(json.dumps(event, default=str)))
                    db.add(
                        SessionEvent(
                            session_id=session.id,
                            event_type=str(event.get("type") or "event"),
                            message=None,
                            payload_json=json.dumps(redacted_event, default=str),
                            event_time=parse_timestamp(event.get("timestamp")),
                        )
                    )
                for ref in parsed.file_refs:
                    db.add(SessionFile(session_id=session.id, file_path=ref))
                docs = parsed_to_docs(parsed)
                refreshed += 1
            except OSError:
                docs = []
        if not docs:
            body = session.transcript_text or session.raw_source_text or ""
            docs = [
                {"result_type": "summary", "title": session.feature_title or session.id, "body_text": build_summary(body, session.feature_title), "source_ref": session.memory_source_path}
            ]
        for doc in docs:
            db.add(SessionSearchDoc(session_id=session.id, **doc))
            total += 1
    await db.commit()
    return {"reindexed_sessions": len(sessions), "refreshed_sources": refreshed, "documents": total}
