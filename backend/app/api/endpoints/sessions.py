from __future__ import annotations

import json
import uuid
from datetime import date, datetime, time, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.database import get_db
from app.core.git_tools import find_commits_in_window, inspect_commit, resolve_repo
from app.core.text_utils import clean_codex_display_text, concise_session_title, parse_exchanges, session_evidence_summary
from app.models.entities import Session, SessionCommit, SessionEvent, SessionFile, SessionSearchDoc
from app.schemas.api import LinkCommitIn, SessionOut, SessionStart

router = APIRouter(prefix="/sessions", tags=["sessions"])


def repo_name(path: str | None) -> str | None:
    return Path(path).name if path else None


def count_rollout_files(root: Path, limit: int = 5000) -> int:
    count = 0
    for _ in root.rglob("rollout-*.jsonl"):
        count += 1
        if count >= limit:
            break
    return count


def recent_session_turns(text: str | None, limit: int = 12) -> list[dict[str, str]]:
    turns = []
    for item in parse_exchanges(text):
        cleaned = clean_codex_display_text(item["text"])
        if cleaned:
            turns.append({"role": item["role"], "text": cleaned[:1200]})
    return turns[-limit:]


def session_to_dict(session: Session) -> dict[str, object]:
    text = "\n".join(filter(None, [session.session_summary, session.transcript_text, session.raw_source_text]))
    return {
        "id": session.id,
        "feature_title": session.feature_title,
        "display_title": concise_session_title(text, session.feature_title),
        "repo_path": session.repo_path,
        "repo_name": session.repo_name,
        "branch_name": session.branch_name,
        "status": session.status,
        "start_time": session.start_time,
        "end_time": session.end_time,
        "session_summary": session.session_summary,
        "start_note": session.start_note,
        "memory_ref": session.memory_ref,
        "memory_source_path": session.memory_source_path,
        "memory_error": session.memory_error,
        "raw_source_text": session.raw_source_text,
        "transcript_text": session.transcript_text,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


def build_evidence_payload(session: Session, include_commit_suggestions: bool = True) -> dict[str, object]:
    text = "\n".join(filter(None, [session.session_summary, session.transcript_text, session.raw_source_text]))
    evidence = session_evidence_summary(text, session.feature_title)
    docs_by_type: dict[str, int] = {}
    for doc in session.search_docs:
        docs_by_type[doc.result_type] = docs_by_type.get(doc.result_type, 0) + 1
    linked_commits = [
        {
            "sha": commit.commit_sha,
            "message": commit.commit_message,
            "author": commit.author_name,
            "time": commit.author_time,
            "diff_summary": commit.diff_summary,
            "files": [file.file_path for file in session.files if file.session_commit_id == commit.id],
        }
        for commit in session.commits
    ]
    files = [file.file_path for file in session.files]
    suggested_commits = []
    suggestion_error = None
    if include_commit_suggestions and session.repo_path:
        try:
            suggested_commits = [
                {
                    "sha": commit.commit_sha,
                    "message": commit.commit_message,
                    "author": commit.author_name,
                    "time": commit.author_time,
                    "diff_summary": commit.diff_summary,
                    "files": commit.changed_files,
                }
                for commit in find_commits_in_window(session.repo_path, session.branch_name or "HEAD", session.start_time, session.end_time, limit=5)
                if commit.commit_sha not in {item["sha"] for item in linked_commits}
            ]
        except Exception as exc:
            suggestion_error = str(exc)
    quality_signals = {
        "has_user_goal": bool(evidence.get("user_goal")),
        "has_summary": bool(evidence.get("summary")),
        "has_files": bool(files or evidence.get("file_changes")),
        "has_decisions": bool(evidence.get("decision_snippets")),
        "has_commands": bool(evidence.get("commands_run")),
        "has_tests": bool(evidence.get("tests_run")),
        "has_commits": bool(linked_commits or evidence.get("commit_refs") or suggested_commits),
        "has_recent_turns": bool(recent_session_turns(session.transcript_text or session.raw_source_text, limit=1)),
    }
    quality_score = round((sum(1 for present in quality_signals.values() if present) / len(quality_signals)) * 100)
    what_changed = {
        "title": concise_session_title(text, session.feature_title),
        "goal": evidence.get("user_goal"),
        "summary": evidence.get("summary"),
        "outcome": evidence.get("outcome"),
        "files": files or evidence.get("file_changes", []),
        "linked_commits": linked_commits,
        "suggested_commits": suggested_commits,
        "decisions": evidence.get("decision_snippets", []),
        "commands": evidence.get("commands_run", []),
        "tests": evidence.get("tests_run", []),
        "errors": evidence.get("errors", []),
    }
    return {
        **evidence,
        "recent_turns": recent_session_turns(session.transcript_text or session.raw_source_text),
        "counts": {
            "events": len(session.events),
            "commits": len(session.commits),
            "files": len(session.files),
            "search_docs": len(session.search_docs),
            "docs_by_type": docs_by_type,
        },
        "linked_commits": linked_commits,
        "files": files,
        "quality_score": quality_score,
        "quality_signals": quality_signals,
        "what_changed": what_changed,
        "commit_suggestions": suggested_commits,
        "commit_suggestion_error": suggestion_error,
    }


@router.post("/start", response_model=SessionOut)
async def start_session(payload: SessionStart, db: AsyncSession = Depends(get_db)):
    branch = payload.branch_name
    repo = payload.repo_path
    if repo and not branch:
        try:
            branch = resolve_repo(repo)["branch"]
        except Exception:
            branch = None
    session = Session(
        id=uuid.uuid4().hex,
        feature_title=payload.feature_title or "Manual session",
        repo_path=repo,
        repo_name=repo_name(repo),
        branch_name=branch,
        status="open",
        start_time=datetime.now(timezone.utc),
        start_note=payload.start_note,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.post("/demo")
async def create_demo_session(db: AsyncSession = Depends(get_db)):
    session_id = f"demo-{uuid.uuid4().hex}"
    now = datetime.now(timezone.utc)
    transcript = "\n".join(
        [
            "user: Add local-only session search and make the Summary tab explain what changed.",
            "assistant: Decision: keep search local because private developer memory should not upload transcripts.",
            "assistant: Ran pytest backend/tests and npm run build. Both passed.",
            "assistant: Updated frontend/src/App.js and backend/app/api/endpoints/sessions.py.",
            "assistant: Outcome: local session intelligence is visible with files, decisions, commands, and export evidence.",
        ]
    )
    session = Session(
        id=session_id,
        feature_title="Demo: local session intelligence",
        repo_path="C:\\demo\\local-dev-memory",
        repo_name="local-dev-memory",
        branch_name="demo/local-mode",
        status="closed",
        start_time=now,
        end_time=now,
        start_note="Show how Local Dev Memory explains a Codex session.",
        session_summary="Feature session for local-only searchable Codex memory.",
        transcript_text=transcript,
        raw_source_text=transcript,
        memory_ref=".local_data/memory_sessions/demo/transcript/normalized_transcript.txt",
        memory_source_path=None,
    )
    db.add(session)
    await db.flush()
    db.add(SessionFile(session_id=session_id, file_path="frontend/src/App.js"))
    db.add(SessionFile(session_id=session_id, file_path="backend/app/api/endpoints/sessions.py"))
    db.add(SessionSearchDoc(session_id=session_id, result_type="summary", title=session.feature_title, body_text=session.session_summary or ""))
    db.add(SessionSearchDoc(session_id=session_id, result_type="decision", title="Local-only decision", body_text="Decision: keep search local because private developer memory should not upload transcripts."))
    db.add(SessionSearchDoc(session_id=session_id, result_type="file", title="frontend/src/App.js", body_text="Changed frontend/src/App.js to show session intelligence.", file_path="frontend/src/App.js"))
    await db.commit()
    return {"session_id": session_id}


@router.delete("")
async def clear_session_index(db: AsyncSession = Depends(get_db)):
    sessions = (await db.scalars(select(Session))).all()
    count = len(sessions)
    for session in sessions:
        await db.delete(session)
    await db.commit()
    return {"cleared": True, "sessions_deleted": count}


@router.post("/{session_id}/end", response_model=SessionOut)
async def end_session(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    session.status = "closed"
    session.end_time = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(session)
    return session


@router.post("/{session_id}/link-commit")
async def link_commit(session_id: str, payload: LinkCommitIn, db: AsyncSession = Depends(get_db)):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    repo = payload.repo_path or session.repo_path
    if not repo:
        raise HTTPException(400, "repo_path is required")
    try:
        info = inspect_commit(repo, payload.commit_sha)
    except Exception as exc:
        raise HTTPException(400, f"Could not inspect commit: {exc}") from exc
    existing = await db.scalar(
        select(SessionCommit).where(SessionCommit.session_id == session_id, SessionCommit.commit_sha == info.commit_sha)
    )
    if existing:
        return {
            "commit": {
                "commit_sha": existing.commit_sha,
                "commit_message": existing.commit_message,
                "author_name": existing.author_name,
                "author_email": existing.author_email,
                "author_time": existing.author_time,
                "diff_summary": existing.diff_summary,
                "changed_files": [file.file_path for file in session.files if file.session_commit_id == existing.id],
            },
            "duplicate": True,
        }
    linked = SessionCommit(
        session_id=session_id,
        commit_sha=info.commit_sha,
        commit_message=info.commit_message,
        author_name=info.author_name,
        author_email=info.author_email,
        author_time=info.author_time,
        diff_summary=info.diff_summary,
    )
    db.add(linked)
    await db.flush()
    for file_path in info.changed_files:
        db.add(SessionFile(session_id=session_id, session_commit_id=linked.id, file_path=file_path))
        db.add(SessionSearchDoc(session_id=session_id, result_type="file", title=file_path, body_text=f"Changed by {info.commit_sha}: {file_path}", commit_sha=info.commit_sha, file_path=file_path))
    db.add(SessionSearchDoc(session_id=session_id, result_type="commit", title=info.commit_sha, body_text=info.commit_message or info.diff_summary, commit_sha=info.commit_sha))
    await db.commit()
    return {"commit": info.__dict__}


@router.get("", response_model=list[SessionOut])
async def list_sessions(
    status: str | None = None,
    repo: str | None = None,
    branch: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Session).order_by(Session.updated_at.desc())
    if status:
        stmt = stmt.where(Session.status == status)
    if repo:
        stmt = stmt.where(Session.repo_name == repo)
    if branch:
        stmt = stmt.where(Session.branch_name == branch)
    if date_from:
        start = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
        stmt = stmt.where(or_(Session.start_time >= start, Session.start_time.is_(None) & (Session.created_at >= start)))
    if date_to:
        end = datetime.combine(date_to, time.max, tzinfo=timezone.utc)
        stmt = stmt.where(or_(Session.start_time <= end, Session.start_time.is_(None) & (Session.created_at <= end)))
    return (await db.scalars(stmt)).all()


@router.get("/diagnostics")
async def diagnostics(db: AsyncSession = Depends(get_db)):
    settings = get_settings()
    sessions = (await db.scalars(select(Session))).all()
    search_doc_count = len((await db.scalars(select(SessionSearchDoc.id))).all())
    file_ref_count = len((await db.scalars(select(SessionFile.id))).all())
    codex_roots = []
    for root in settings.codex_session_roots():
        exists = root.exists()
        rollout_count = count_rollout_files(root) if exists else 0
        codex_roots.append({"path": str(root), "exists": exists, "rollout_files": rollout_count})
    missing_sources = [
        session.memory_source_path
        for session in sessions
        if session.memory_source_path and not Path(session.memory_source_path).exists()
    ][:25]
    return {
        "database_url": settings.database_url,
        "data_root": str(settings.data_root),
        "data_root_exists": settings.data_root.exists(),
        "palace_path": str(settings.palace_path),
        "codex_roots": codex_roots,
        "session_count": len(sessions),
        "search_doc_count": search_doc_count,
        "file_ref_count": file_ref_count,
        "missing_source_count": len(missing_sources),
        "missing_sources": missing_sources,
        "local_mode": {
            "enabled": True,
            "network_required": False,
            "storage": str(settings.data_root),
            "index": "SQLite/local database evidence index",
            "privacy": "Sessions, transcripts, commit metadata, and exports stay on this machine.",
        },
    }


@router.get("/facets")
async def session_facets(db: AsyncSession = Depends(get_db)):
    sessions = (await db.scalars(select(Session))).all()
    return {
        "statuses": sorted({session.status for session in sessions if session.status}),
        "repositories": sorted({session.repo_name for session in sessions if session.repo_name}),
        "branches": sorted({session.branch_name for session in sessions if session.branch_name}),
        "counts": {
            "total": len(sessions),
            "open": sum(1 for session in sessions if session.status == "open"),
            "closed": sum(1 for session in sessions if session.status == "closed"),
            "with_transcripts": sum(1 for session in sessions if session.transcript_text),
            "with_commits": sum(1 for session in sessions if session.commits),
        },
    }


@router.get("/{session_id}/evidence")
async def session_evidence(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await db.scalar(
        select(Session)
        .where(Session.id == session_id)
        .options(selectinload(Session.events), selectinload(Session.commits), selectinload(Session.files), selectinload(Session.search_docs))
    )
    if not session:
        raise HTTPException(404, "Session not found")
    return build_evidence_payload(session)


@router.get("/{session_id}/view")
async def session_view(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await db.scalar(
        select(Session)
        .where(Session.id == session_id)
        .options(selectinload(Session.events), selectinload(Session.commits), selectinload(Session.files), selectinload(Session.search_docs))
    )
    if not session:
        raise HTTPException(404, "Session not found")
    return {"session": session_to_dict(session), "evidence": build_evidence_payload(session, include_commit_suggestions=False)}


@router.get("/{session_id}", response_model=SessionOut)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return session


@router.delete("/{session_id}")
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    await db.delete(session)
    await db.commit()
    return {"deleted": True, "session_id": session_id}


@router.get("/{session_id}/timeline")
async def timeline(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await db.scalar(
        select(Session)
        .where(Session.id == session_id)
        .options(selectinload(Session.events), selectinload(Session.commits), selectinload(Session.files))
    )
    if not session:
        raise HTTPException(404, "Session not found")
    items = []
    for event in session.events:
        items.append({"kind": "event", "time": event.event_time, "type": event.event_type, "message": event.message, "payload": event.payload_json})
    for commit in session.commits:
        items.append({"kind": "commit", "time": commit.author_time, "sha": commit.commit_sha, "message": commit.commit_message})
    return sorted(items, key=lambda item: str(item.get("time") or ""))


@router.get("/{session_id}/export.json")
async def export_session_json(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await db.scalar(
        select(Session)
        .where(Session.id == session_id)
        .options(selectinload(Session.events), selectinload(Session.commits), selectinload(Session.files), selectinload(Session.search_docs))
    )
    if not session:
        raise HTTPException(404, "Session not found")
    return {"session": session_to_dict(session), "evidence": build_evidence_payload(session)}


@router.get("/{session_id}/export.md")
async def export_session_markdown(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await db.scalar(
        select(Session)
        .where(Session.id == session_id)
        .options(selectinload(Session.events), selectinload(Session.commits), selectinload(Session.files), selectinload(Session.search_docs))
    )
    if not session:
        raise HTTPException(404, "Session not found")
    evidence = build_evidence_payload(session)
    body = "\n".join(
        [
            f"# {session.feature_title or session.id}",
            "",
            f"Status: {session.status}",
            f"Repo: {session.repo_path or ''}",
            f"Branch: {session.branch_name or ''}",
            "",
            "## User Goal",
            str(evidence.get("user_goal") or ""),
            "",
            "## Summary",
            str(evidence.get("summary") or session.session_summary or ""),
            "",
            "## Outcome",
            str(evidence.get("outcome") or ""),
            "",
            "## Decisions",
            *[f"- {item}" for item in evidence.get("decision_snippets", [])],
            "",
            "## Files",
            *[f"- {item}" for item in evidence.get("files", [])],
            "",
            "## Commits",
            *[f"- {item.get('sha')}: {item.get('message') or ''}" for item in evidence.get("linked_commits", [])],
            "",
            "## Commands",
            *[f"- `{item}`" for item in evidence.get("commands_run", [])],
            "",
            "## Errors / Warnings",
            *[f"- {item}" for item in evidence.get("errors", [])],
            "",
            "## Transcript",
            session.transcript_text or "",
            "",
        ]
    )
    return Response(body, media_type="text/markdown")


@router.get("/../export/sessions.jsonl", include_in_schema=False)
async def bad_export_alias():
    raise HTTPException(404, "Use /api/v1/export/sessions.jsonl")
