from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.text_utils import classify_query, extract_commit_shas, extract_file_refs, keyword_score, redact_secrets
from app.models.entities import Session, SessionSearchDoc
from app.api.endpoints.sessions import build_evidence_payload, session_to_dict

router = APIRouter(prefix="", tags=["search"])


def like_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@router.get("/search")
async def search(q: str = Query(min_length=1), session_id: str | None = None, db: AsyncSession = Depends(get_db)):
    kind = classify_query(q)
    terms = [term for term in re.findall(r"[\w.-]{3,}", q)[:8]]
    if not terms and not re.search(r"[\w.-]", q):
        return []
    likes = [like_pattern(q)] + [like_pattern(term) for term in terms]
    clauses = []
    for like in likes:
        clauses.extend(
            [
                SessionSearchDoc.title.ilike(like, escape="\\"),
                SessionSearchDoc.body_text.ilike(like, escape="\\"),
                SessionSearchDoc.file_path.ilike(like, escape="\\"),
                SessionSearchDoc.commit_sha.ilike(like, escape="\\"),
                Session.feature_title.ilike(like, escape="\\"),
                Session.repo_name.ilike(like, escape="\\"),
                Session.repo_path.ilike(like, escape="\\"),
                Session.branch_name.ilike(like, escape="\\"),
            ]
        )
    if kind == "decision":
        clauses.append(SessionSearchDoc.result_type == "decision")
    stmt = select(SessionSearchDoc, Session).join(Session, Session.id == SessionSearchDoc.session_id).where(or_(*clauses))
    if session_id:
        stmt = stmt.where(Session.id == session_id)
    rows = (await db.execute(stmt)).all()
    results = []
    seen = set()
    for row, session in rows:
        key = row.id
        if key in seen:
            continue
        seen.add(key)
        session_text = "\n".join(filter(None, [session.feature_title, session.repo_name, session.repo_path, session.branch_name]))
        text = f"{row.title}\n{row.body_text}\n{session_text}"
        score = keyword_score(q, text) + (5 if row.result_type == kind else 0)
        results.append(
            {
                "session_id": row.session_id,
                "session_title": session.feature_title,
                "repo_name": session.repo_name,
                "branch_name": session.branch_name,
                "session_start_time": session.start_time,
                "result_type": row.result_type,
                "title": row.title,
                "body_text": redact_secrets(row.body_text),
                "commit_sha": row.commit_sha,
                "file_path": row.file_path,
                "source_ref": row.source_ref,
                "score": score,
                "evidence_summary": {
                    "likely_reason": "Matched local indexed evidence only.",
                    "supporting_evidence": redact_secrets(row.body_text[:500]),
                    "related_files": extract_file_refs(text),
                    "related_commits": extract_commit_shas(text),
                    "query_type": kind,
                },
            }
        )
    session_clauses = []
    for like in likes:
        session_clauses.extend(
            [
                Session.id.ilike(like, escape="\\"),
                Session.feature_title.ilike(like, escape="\\"),
                Session.repo_name.ilike(like, escape="\\"),
                Session.repo_path.ilike(like, escape="\\"),
                Session.branch_name.ilike(like, escape="\\"),
                Session.session_summary.ilike(like, escape="\\"),
                Session.transcript_text.ilike(like, escape="\\"),
            ]
        )
    session_stmt = select(Session).where(or_(*session_clauses))
    if session_id:
        session_stmt = session_stmt.where(Session.id == session_id)
    sessions = (await db.scalars(session_stmt)).all()
    seen_sessions = {item["session_id"] for item in results}
    for session in sessions:
        if session.id in seen_sessions:
            continue
        text = "\n".join(
            filter(
                None,
                [
                    session.feature_title,
                    session.repo_name,
                    session.repo_path,
                    session.branch_name,
                    session.session_summary,
                    (session.transcript_text or "")[:1000],
                ],
            )
        )
        results.append(
            {
                "session_id": session.id,
                "session_title": session.feature_title,
                "repo_name": session.repo_name,
                "branch_name": session.branch_name,
                "session_start_time": session.start_time,
                "result_type": "session",
                "title": session.feature_title or session.id,
                "body_text": redact_secrets(text or session.id),
                "commit_sha": None,
                "file_path": None,
                "source_ref": session.memory_source_path,
                "score": keyword_score(q, text),
                "evidence_summary": {
                    "likely_reason": "Matched session metadata or transcript text.",
                    "supporting_evidence": redact_secrets(text[:500]),
                    "related_files": extract_file_refs(text),
                    "related_commits": extract_commit_shas(text),
                    "query_type": kind,
                },
            }
        )
    return sorted(results, key=lambda item: item["score"], reverse=True)[:50]


@router.get("/search/commits/{commit_sha}")
async def commit_search(commit_sha: str, db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(SessionSearchDoc).where(SessionSearchDoc.commit_sha.ilike(f"%{commit_sha}%")))).all()
    return rows


@router.get("/export/sessions.jsonl")
async def export_sessions_jsonl(db: AsyncSession = Depends(get_db)):
    sessions = (
        await db.scalars(
            select(Session)
            .options(
                selectinload(Session.events),
                selectinload(Session.commits),
                selectinload(Session.files),
                selectinload(Session.search_docs),
            )
            .order_by(Session.created_at)
        )
    ).all()
    lines = []
    for session in sessions:
        lines.append(json.dumps({"session": session_to_dict(session), "evidence": build_evidence_payload(session)}, default=str))
    return Response("\n".join(lines) + ("\n" if lines else ""), media_type="application/x-ndjson")
