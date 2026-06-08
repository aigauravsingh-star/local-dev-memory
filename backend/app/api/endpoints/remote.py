from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.text_utils import build_summary, concise_session_title, extract_commit_shas, extract_decision_snippets, extract_file_refs, redact_secrets, session_evidence_summary
from app.models.entities import RemoteDeveloper, RemoteProject, RemoteSessionIngest, Session, SessionEvent, SessionSearchDoc
from app.schemas.api import RemoteDebugBriefIn, RemoteDeveloperIn, RemoteFetchIn, RemoteProjectIn, RemoteSessionUploadIn

router = APIRouter(prefix="/remote", tags=["remote-debug"])


def _repo_name(path: str | None, explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    return Path(path).name if path else None


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _project_from_payload(db: AsyncSession, project_id: int | None, project_name: str | None) -> RemoteProject:
    project = await db.get(RemoteProject, project_id) if project_id else None
    if not project and project_name:
        project = await db.scalar(select(RemoteProject).where(RemoteProject.name == project_name))
    if not project and project_name:
        project = RemoteProject(name=project_name, description="Created from remote debug upload.", debug_mode_enabled=True)
        db.add(project)
        await db.flush()
    if not project:
        raise HTTPException(400, "project_id or project_name is required")
    if not project.debug_mode_enabled:
        raise HTTPException(400, "Debug mode is disabled for this project")
    return project


async def _developer_from_payload(db: AsyncSession, project: RemoteProject, payload: RemoteSessionUploadIn) -> RemoteDeveloper | None:
    email = (payload.developer_email or "").strip().lower()
    if not email:
        return None
    developer = await db.scalar(
        select(RemoteDeveloper).where(RemoteDeveloper.project_id == project.id, RemoteDeveloper.email == email)
    )
    if developer:
        developer.name = payload.developer_name or developer.name
        developer.tool_name = payload.tool_name or developer.tool_name
        developer.last_seen_at = _now()
        return developer
    developer = RemoteDeveloper(
        project_id=project.id,
        name=payload.developer_name or email,
        email=email,
        tool_name=payload.tool_name,
        active=True,
        last_seen_at=_now(),
    )
    db.add(developer)
    await db.flush()
    return developer


def _search_docs(session_id: str, title: str, text: str, source_ref: str | None) -> list[SessionSearchDoc]:
    clean = redact_secrets(text)
    docs = [SessionSearchDoc(session_id=session_id, result_type="summary", title=title, body_text=build_summary(clean, title), source_ref=source_ref)]
    for decision in extract_decision_snippets(clean, limit=10):
        docs.append(SessionSearchDoc(session_id=session_id, result_type="decision", title="Remote debug decision", body_text=decision, source_ref=source_ref))
    for file_path in extract_file_refs(clean)[:50]:
        docs.append(SessionSearchDoc(session_id=session_id, result_type="file", title=file_path, body_text=f"Remote session referenced {file_path}", file_path=file_path, source_ref=source_ref))
    for sha in extract_commit_shas(clean)[:30]:
        docs.append(SessionSearchDoc(session_id=session_id, result_type="commit", title=sha, body_text=f"Remote session referenced commit {sha}", commit_sha=sha, source_ref=source_ref))
    return docs


async def _ingest_remote_session(db: AsyncSession, payload: RemoteSessionUploadIn) -> dict[str, object]:
    project = await _project_from_payload(db, payload.project_id, payload.project_name)
    developer = await _developer_from_payload(db, project, payload)
    external_id = payload.external_session_id or uuid.uuid4().hex
    existing = await db.scalar(
        select(RemoteSessionIngest)
        .where(RemoteSessionIngest.project_id == project.id, RemoteSessionIngest.external_session_id == external_id)
    )
    if existing:
        return {"duplicate": True, "session_id": existing.session_id, "project_id": project.id, "remote_ingest_id": existing.id}

    text = "\n".join(filter(None, [payload.session_summary, payload.transcript_text, payload.raw_source_text]))
    title = concise_session_title(text, payload.title or f"{project.name} remote debug session")
    session_id = f"remote-{project.id}-{uuid.uuid4().hex}"
    started = payload.occurred_at or _now()
    session = Session(
        id=session_id,
        feature_title=title,
        repo_path=payload.repo_path,
        repo_name=_repo_name(payload.repo_path, payload.repo_name),
        branch_name=payload.branch_name,
        status="remote-debug",
        start_time=started,
        end_time=started,
        session_summary=build_summary(text, title),
        start_note=f"Remote debug upload for {project.name}",
        memory_ref=f"remote://project/{project.id}/session/{external_id}",
        memory_source_path=None,
        raw_source_text=redact_secrets(payload.raw_source_text or text),
        transcript_text=redact_secrets(payload.transcript_text or text),
    )
    db.add(session)
    await db.flush()
    db.add(
        RemoteSessionIngest(
            project_id=project.id,
            developer_id=developer.id if developer else None,
            session_id=session_id,
            external_session_id=external_id,
            tool_name=payload.tool_name,
            source_ref=payload.source_ref,
            ingest_status="received",
            issue_count=max(0, payload.issue_count),
        )
    )
    db.add(SessionEvent(session_id=session_id, event_type="remote_debug_upload", message=f"Remote session uploaded for {project.name}", event_time=started))
    for doc in _search_docs(session_id, title, text, payload.source_ref):
        db.add(doc)
    await db.commit()
    return {"duplicate": False, "session_id": session_id, "project_id": project.id, "external_session_id": external_id}


def _project_dict(project: RemoteProject, ingests: list[RemoteSessionIngest]) -> dict[str, object]:
    project_ingests = [item for item in ingests if item.project_id == project.id]
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "debug_mode_enabled": project.debug_mode_enabled,
        "developer_count": len(project.developers),
        "session_count": len(project_ingests),
        "issue_count": sum(item.issue_count for item in project_ingests),
        "last_upload_at": max((item.uploaded_at for item in project_ingests), default=None),
    }


def _remote_session_row(
    ingest: RemoteSessionIngest,
    session: Session | None,
    project: RemoteProject | None,
    developer: RemoteDeveloper | None,
) -> dict[str, object]:
    text = "\n".join(filter(None, [session.session_summary if session else None, session.transcript_text if session else None]))
    evidence = session_evidence_summary(text, session.feature_title if session else ingest.external_session_id)
    return {
        "id": ingest.id,
        "project_id": ingest.project_id,
        "project_name": project.name if project else None,
        "developer_id": ingest.developer_id,
        "developer_name": developer.name if developer else "Unknown developer",
        "developer_email": developer.email if developer else None,
        "tool_name": ingest.tool_name or (developer.tool_name if developer else None),
        "session_id": ingest.session_id,
        "external_session_id": ingest.external_session_id,
        "session_title": concise_session_title(text, session.feature_title if session else ingest.external_session_id),
        "repo_name": session.repo_name if session else None,
        "branch_name": session.branch_name if session else None,
        "status": session.status if session else ingest.ingest_status,
        "summary": session.session_summary if session else "",
        "issue_count": ingest.issue_count,
        "uploaded_at": ingest.uploaded_at,
        "source_ref": ingest.source_ref,
        "files": evidence.get("file_changes", [])[:10],
        "commits": evidence.get("commit_refs", [])[:10],
        "decisions": evidence.get("decision_snippets", [])[:3],
        "outcome": evidence.get("outcome"),
    }


async def _remote_board_payload(
    db: AsyncSession,
    project_id: int | None = None,
    developer_id: int | None = None,
    q: str | None = None,
) -> dict[str, object]:
    projects = (await db.scalars(select(RemoteProject).options(selectinload(RemoteProject.developers)))).all()
    developers = (await db.scalars(select(RemoteDeveloper))).all()
    ingests = (await db.scalars(select(RemoteSessionIngest).order_by(RemoteSessionIngest.uploaded_at.desc()))).all()
    sessions = (await db.scalars(select(Session).where(Session.status == "remote-debug"))).all()
    project_map = {project.id: project for project in projects}
    developer_map = {developer.id: developer for developer in developers}
    session_map = {session.id: session for session in sessions}
    rows = [
        _remote_session_row(ingest, session_map.get(ingest.session_id), project_map.get(ingest.project_id), developer_map.get(ingest.developer_id))
        for ingest in ingests
    ]
    if project_id:
        rows = [row for row in rows if row["project_id"] == project_id]
    if developer_id:
        rows = [row for row in rows if row["developer_id"] == developer_id]
    if q:
        needle = q.lower()
        rows = [
            row for row in rows
            if needle in "\n".join(str(row.get(key) or "") for key in ["session_title", "summary", "repo_name", "branch_name", "developer_name", "developer_email", "tool_name"]).lower()
            or any(needle in str(item).lower() for item in row.get("files", []))
            or any(needle in str(item).lower() for item in row.get("decisions", []))
        ]
    developer_stats = []
    for developer in developers:
        dev_rows = [row for row in rows if row["developer_id"] == developer.id]
        developer_stats.append({
            "id": developer.id,
            "project_id": developer.project_id,
            "name": developer.name,
            "email": developer.email,
            "tool_name": developer.tool_name,
            "active": developer.active,
            "last_seen_at": developer.last_seen_at,
            "session_count": len(dev_rows),
            "issue_count": sum(int(row["issue_count"] or 0) for row in dev_rows),
        })
    file_counts: dict[str, int] = {}
    repo_counts: dict[str, int] = {}
    for row in rows:
        if row.get("repo_name"):
            repo_counts[str(row["repo_name"])] = repo_counts.get(str(row["repo_name"]), 0) + 1
        for file_path in row.get("files", []):
            file_counts[str(file_path)] = file_counts.get(str(file_path), 0) + 1
    return {
        "projects": [_project_dict(project, ingests) for project in projects],
        "developers": sorted(developer_stats, key=lambda item: (-item["issue_count"], item["name"])),
        "sessions": rows,
        "stats": {
            "project_count": len(projects),
            "developer_count": len(developers),
            "remote_session_count": len(rows),
            "issue_count": sum(int(row["issue_count"] or 0) for row in rows),
            "repo_count": len(repo_counts),
            "llm_status": "local-first debug brief available; external LLM connector not configured",
        },
        "hotspots": {
            "files": sorted([{"file": key, "count": value} for key, value in file_counts.items()], key=lambda item: -item["count"])[:8],
            "repositories": sorted([{"repo": key, "count": value} for key, value in repo_counts.items()], key=lambda item: -item["count"])[:8],
            "high_issue_sessions": sorted(rows, key=lambda item: -int(item["issue_count"] or 0))[:5],
        },
    }


@router.get("/overview")
async def overview(db: AsyncSession = Depends(get_db)):
    board = await _remote_board_payload(db)
    recent = board["sessions"][:12]
    return {
        "mode": "remote-debug",
        "description": "Team sessions uploaded or fetched into a central private debug index.",
        "project_count": board["stats"]["project_count"],
        "developer_count": board["stats"]["developer_count"],
        "remote_session_count": board["stats"]["remote_session_count"],
        "issue_count": board["stats"]["issue_count"],
        "projects": board["projects"],
        "developers": board["developers"],
        "hotspots": board["hotspots"],
        "recent_uploads": recent,
    }


@router.get("/debug-board")
async def debug_board(
    project_id: int | None = None,
    developer_id: int | None = None,
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await _remote_board_payload(db, project_id=project_id, developer_id=developer_id, q=q)


@router.post("/debug-brief")
async def debug_brief(payload: RemoteDebugBriefIn, db: AsyncSession = Depends(get_db)):
    board = await _remote_board_payload(db, project_id=payload.project_id, developer_id=payload.developer_id, q=payload.query)
    sessions = board["sessions"]
    hotspots = board["hotspots"]
    top_sessions = hotspots["high_issue_sessions"][:3]
    root_causes = []
    for row in top_sessions:
        root_causes.extend(row.get("decisions", [])[:2])
    next_actions = [
        "Open the highest-issue remote sessions and compare decisions, files, and validation evidence.",
        "Filter by the developer or repository with the most issue signals before assigning follow-up.",
        "Use the normal session Summary, What changed, Timeline, Transcript, Search, and Export tabs for each remote session.",
    ]
    if hotspots["files"]:
        next_actions.insert(0, f"Start with hotspot file {hotspots['files'][0]['file']} because it appears across {hotspots['files'][0]['count']} remote session(s).")
    return {
        "mode": payload.llm_mode,
        "llm_ready": True,
        "llm_status": "Generated locally. A hosted/private LLM connector can use the same project/session evidence payload later.",
        "question": payload.query or "What should the team debug first?",
        "answer": {
            "summary": f"{len(sessions)} remote session(s), {board['stats']['issue_count']} issue signal(s), {len(board['developers'])} developer(s) in scope.",
            "likely_root_causes": root_causes[:6] or ["No explicit decision/root-cause snippets were found in the selected remote scope."],
            "hotspot_files": hotspots["files"][:5],
            "hotspot_repositories": hotspots["repositories"][:5],
            "highest_risk_sessions": top_sessions,
            "next_actions": next_actions,
        },
    }


@router.post("/projects")
async def create_project(payload: RemoteProjectIn, db: AsyncSession = Depends(get_db)):
    existing = await db.scalar(select(RemoteProject).where(RemoteProject.name == payload.name))
    if existing:
        existing.description = payload.description
        existing.debug_mode_enabled = payload.debug_mode_enabled
        await db.commit()
        await db.refresh(existing)
        return {"project_id": existing.id, "updated": True}
    project = RemoteProject(name=payload.name, description=payload.description, debug_mode_enabled=payload.debug_mode_enabled)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return {"project_id": project.id, "created": True}


@router.post("/projects/{project_id}/developers")
async def add_developer(project_id: int, payload: RemoteDeveloperIn, db: AsyncSession = Depends(get_db)):
    project = await db.get(RemoteProject, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    email = payload.email.strip().lower()
    existing = await db.scalar(select(RemoteDeveloper).where(RemoteDeveloper.project_id == project_id, RemoteDeveloper.email == email))
    if existing:
        existing.name = payload.name
        existing.tool_name = payload.tool_name
        existing.fetch_url = payload.fetch_url
        existing.active = payload.active
        await db.commit()
        await db.refresh(existing)
        return {"developer_id": existing.id, "updated": True}
    developer = RemoteDeveloper(project_id=project_id, name=payload.name, email=email, tool_name=payload.tool_name, fetch_url=payload.fetch_url, active=payload.active)
    db.add(developer)
    await db.commit()
    await db.refresh(developer)
    return {"developer_id": developer.id, "created": True}


@router.post("/sessions/upload")
async def upload_session(payload: RemoteSessionUploadIn, db: AsyncSession = Depends(get_db)):
    return await _ingest_remote_session(db, payload)


@router.post("/demo")
async def create_remote_demo(db: AsyncSession = Depends(get_db)):
    project_name = "Demo Project - Checkout Platform"
    project = await db.scalar(select(RemoteProject).where(RemoteProject.name == project_name))
    if not project:
        project = RemoteProject(
            name=project_name,
            description="Demo remote debug mode for a 10 developer team using Codex and other coding agents.",
            debug_mode_enabled=True,
        )
        db.add(project)
        await db.flush()

    developers = [
        ("Asha Rao", "asha.rao@example.com", "Codex"),
        ("Ben Carter", "ben.carter@example.com", "Cursor"),
        ("Chen Li", "chen.li@example.com", "Codex"),
        ("Diego Silva", "diego.silva@example.com", "Claude Code"),
        ("Elena Novak", "elena.novak@example.com", "Codex"),
        ("Fatima Khan", "fatima.khan@example.com", "Cursor"),
        ("Grace Lee", "grace.lee@example.com", "Codex"),
        ("Hari Menon", "hari.menon@example.com", "JetBrains AI"),
        ("Iris Stone", "iris.stone@example.com", "Codex"),
        ("Jon Miller", "jon.miller@example.com", "Claude Code"),
    ]
    for name, email, tool in developers:
        existing = await db.scalar(select(RemoteDeveloper).where(RemoteDeveloper.project_id == project.id, RemoteDeveloper.email == email))
        if existing:
            existing.name = name
            existing.tool_name = tool
            existing.active = True
            continue
        db.add(RemoteDeveloper(project_id=project.id, name=name, email=email, tool_name=tool, active=True, last_seen_at=_now()))
    await db.flush()

    demo_sessions = [
        {
            "developer_email": "asha.rao@example.com",
            "developer_name": "Asha Rao",
            "tool_name": "Codex",
            "external_session_id": "demo-remote-checkout-retry",
            "title": "Fix checkout retry duplicate charge",
            "repo_name": "checkout-service",
            "branch_name": "fix/retry-idempotency",
            "session_summary": "Investigated duplicate charge reports and added idempotency checks around retry handling.",
            "transcript_text": "user: Debug duplicate checkout charges after timeout\nassistant: Decision: changed services/checkout/retry_policy.py because retry attempts reused the same payment request without idempotency guard. Ran pytest tests/test_retry_policy.py and verified duplicate charge scenario. Commit a1b2c3d4e5f6",
            "issue_count": 3,
        },
        {
            "developer_email": "chen.li@example.com",
            "developer_name": "Chen Li",
            "tool_name": "Codex",
            "external_session_id": "demo-remote-auth-refresh",
            "title": "Repair token refresh failure",
            "repo_name": "identity-api",
            "branch_name": "bugfix/token-refresh",
            "session_summary": "Fixed refresh-token validation so expired access tokens can renew safely.",
            "transcript_text": "user: Users are logged out during token refresh\nassistant: Decision: updated src/auth/token_refresh.py because refresh tokens were checked against the wrong audience. Ran pytest tests/auth/test_token_refresh.py. Commit b2c3d4e5f6a7",
            "issue_count": 2,
        },
        {
            "developer_email": "diego.silva@example.com",
            "developer_name": "Diego Silva",
            "tool_name": "Claude Code",
            "external_session_id": "demo-remote-inventory-cache",
            "title": "Fix stale inventory cache",
            "repo_name": "inventory-worker",
            "branch_name": "hotfix/cache-ttl",
            "session_summary": "Debugged stale inventory counts and reduced cache TTL for high-demand SKUs.",
            "transcript_text": "user: Inventory page shows stale stock after purchase\nassistant: Decision: changed workers/inventory/cache.py because cache invalidation did not run after reservation events. Ran npm run build and pytest tests/test_cache_invalidation.py. Commit c3d4e5f6a7b8",
            "issue_count": 4,
        },
        {
            "developer_email": "fatima.khan@example.com",
            "developer_name": "Fatima Khan",
            "tool_name": "Cursor",
            "external_session_id": "demo-remote-order-search",
            "title": "Improve order search diagnostics",
            "repo_name": "ops-dashboard",
            "branch_name": "feature/order-debug-search",
            "session_summary": "Added searchable failure context for order support workflows.",
            "transcript_text": "user: Support team cannot find failed orders by gateway reference\nassistant: Decision: updated frontend/src/order/SearchPanel.js and backend/app/search/orders.py because gateway_reference was not indexed. Ran npm run build. Commit d4e5f6a7b8c9",
            "issue_count": 1,
        },
        {
            "developer_email": "iris.stone@example.com",
            "developer_name": "Iris Stone",
            "tool_name": "Codex",
            "external_session_id": "demo-remote-notification-timeout",
            "title": "Debug notification timeout",
            "repo_name": "notification-service",
            "branch_name": "fix/provider-timeout",
            "session_summary": "Traced provider timeout failures and added retry/backoff logging.",
            "transcript_text": "user: Notification delivery fails silently for SMS provider\nassistant: Decision: changed app/providers/sms_client.py because timeout exceptions were swallowed before metrics were recorded. Ran pytest tests/providers/test_sms_client.py. Commit e5f6a7b8c9d0",
            "issue_count": 2,
        },
    ]
    results = []
    for item in demo_sessions:
        item["project_id"] = project.id
        item["source_ref"] = "remote-demo://checkout-platform"
        results.append(await _ingest_remote_session(db, RemoteSessionUploadIn(**item)))
    return {
        "project_id": project.id,
        "session_id": results[0]["session_id"] if results else None,
        "developers": len(developers),
        "sessions": len(results),
        "results": results,
    }


@router.post("/fetch")
async def fetch_remote_sessions(payload: RemoteFetchIn, db: AsyncSession = Depends(get_db)):
    project = await _project_from_payload(db, payload.project_id, payload.project_name)
    req = Request(payload.source_url, headers={"User-Agent": "LocalDevMemory/remote-debug"})
    try:
        with urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise HTTPException(400, f"Could not fetch remote sessions: {exc}") from exc
    items = data if isinstance(data, list) else data.get("sessions", [data])
    results = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item.setdefault("project_id", project.id)
        item.setdefault("developer_email", payload.developer_email)
        item.setdefault("tool_name", payload.tool_name)
        item.setdefault("source_ref", payload.source_url)
        results.append(await _ingest_remote_session(db, RemoteSessionUploadIn(**item)))
    return {"fetched": len(results), "project_id": project.id, "results": results}
