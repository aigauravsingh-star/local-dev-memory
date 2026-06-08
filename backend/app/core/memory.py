from __future__ import annotations

import json
import re
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.text_utils import (
    build_summary,
    clean_codex_display_text,
    extract_commit_shas,
    extract_decision_snippets,
    extract_file_refs,
    parse_exchanges,
    redact_secrets,
)


@dataclass
class ParsedCodexSession:
    session_id: str
    source_path: str
    modified_time: datetime | None
    prompt_preview: str | None = None
    repo_path: str | None = None
    branch_name: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    raw_source_text: str = ""
    transcript_text: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)
    commit_shas: list[str] = field(default_factory=list)
    file_refs: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)


def parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _text_from_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or item.get("message") or ""))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        return str(value.get("text") or value.get("content") or value.get("message") or "")
    return ""


def _walk_strings(obj: Any) -> list[str]:
    found: list[str] = []
    if isinstance(obj, str):
        found.append(obj)
    elif isinstance(obj, dict):
        for value in obj.values():
            found.extend(_walk_strings(value))
    elif isinstance(obj, list):
        for value in obj:
            found.extend(_walk_strings(value))
    return found


def clean_prompt_preview(text: str | None) -> str:
    if not text:
        return ""
    cleaned = text
    if "My request for Codex:" in cleaned:
        cleaned = cleaned.split("My request for Codex:", 1)[1]
    cleaned = clean_codex_display_text(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:\t\r\n")
    return cleaned


def parse_codex_jsonl(path: str | Path) -> ParsedCodexSession:
    p = Path(path)
    raw = p.read_text(encoding="utf-8", errors="replace")
    session_id = p.stem.replace("rollout-", "") or uuid.uuid4().hex
    stat = p.stat()
    parsed = ParsedCodexSession(
        session_id=session_id,
        source_path=str(p.resolve()),
        modified_time=datetime.fromtimestamp(stat.st_mtime, timezone.utc),
        raw_source_text=raw,
    )
    transcript_lines: list[str] = []
    all_text: list[str] = []
    times: list[datetime] = []

    for line_no, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            parsed.events.append({"type": "parse_error", "line": line_no, "message": line[:500]})
            continue

        item_type = str(item.get("type") or item.get("event_type") or item.get("name") or "event")
        ts = parse_timestamp(item.get("timestamp") or item.get("time") or item.get("created_at"))
        if ts:
            times.append(ts)
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else item

        if item_type == "session_meta" or "session_meta" in item:
            meta = item.get("session_meta") or payload
            parsed.session_id = str(meta.get("id") or meta.get("session_id") or parsed.session_id)
            parsed.repo_path = meta.get("cwd") or meta.get("repo_path") or meta.get("repository") or parsed.repo_path
            parsed.branch_name = meta.get("branch") or meta.get("branch_name") or parsed.branch_name
        if item_type == "turn_context" or "turn_context" in item:
            ctx = item.get("turn_context") or payload
            parsed.repo_path = ctx.get("cwd") or ctx.get("repo_path") or parsed.repo_path
            parsed.branch_name = ctx.get("branch") or ctx.get("branch_name") or parsed.branch_name
        role = payload.get("role") or item.get("role")
        content = _text_from_content(payload.get("content") or payload.get("message") or payload.get("text") or item.get("message"))
        if item_type in {"event_msg", "response_item"} or role or content:
            label = role or item_type
            if content:
                transcript_lines.append(f"{label}: {content}")
                all_text.append(content)
                if label == "user" and not parsed.prompt_preview:
                    preview = clean_prompt_preview(content)
                    if preview:
                        parsed.prompt_preview = preview[:300]
        for text in _walk_strings(item):
            all_text.append(text)
        parsed.events.append({"type": item_type, "role": role, "timestamp": ts.isoformat() if ts else None, "payload": item})

    if times:
        parsed.start_time = min(times)
        parsed.end_time = max(times)
    parsed.transcript_text = redact_secrets("\n\n".join(transcript_lines))
    joined = redact_secrets("\n".join(all_text))
    parsed.commit_shas = extract_commit_shas(joined)
    parsed.file_refs = extract_file_refs(joined)
    parsed.decisions = extract_decision_snippets(joined)
    return parsed


def discover_codex_sessions(limit: int = 20, extra_roots: list[str | Path] | None = None) -> list[ParsedCodexSession]:
    settings = get_settings()
    candidates: list[Path] = []
    roots = [*settings.codex_session_roots()]
    for raw in extra_roots or []:
        root = Path(raw).expanduser().resolve()
        if root not in roots:
            roots.append(root)
    for root in roots:
        if root.exists():
            candidates.extend(root.rglob("rollout-*.jsonl"))
    seen: set[Path] = set()
    unique = []
    for path in candidates:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    unique.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    parsed: list[ParsedCodexSession] = []
    for path in unique[:limit]:
        try:
            parsed.append(parse_codex_jsonl(path))
        except OSError:
            continue
    return parsed


def normalize_to_local_memory(parsed: ParsedCodexSession) -> dict[str, str | None]:
    settings = get_settings()
    root = settings.data_root / "memory_sessions" / parsed.session_id
    ingest = root / "ingest"
    transcript = root / "transcript"
    ingest.mkdir(parents=True, exist_ok=True)
    transcript.mkdir(parents=True, exist_ok=True)
    source = Path(parsed.source_path)
    copied = ingest / source.name
    if source.exists() and source.resolve() != copied.resolve():
        shutil.copy2(source, copied)
    normalized = transcript / "normalized_transcript.txt"
    text = parsed.transcript_text or ""
    if not text and settings.allow_mock_memory:
        text = "system: Placeholder transcript created because no transcript text was available."
    normalized.write_text(redact_secrets(text), encoding="utf-8")
    memory_error = None
    mempalace = Path("mempalace_fork")
    if mempalace.exists():
        memory_error = "MemPalace fork detected; local boundary reserved. Native normalize/mine_convos adapter is not installed, so built-in normalization was used."
    return {"memory_ref": str(normalized), "memory_source_path": str(copied), "memory_error": memory_error}


def parsed_to_docs(parsed: ParsedCodexSession) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    summary = build_summary(parsed.transcript_text, parsed.prompt_preview)
    docs.append({"result_type": "summary", "title": parsed.prompt_preview or "Session summary", "body_text": summary, "source_ref": parsed.source_path})
    for snippet in parsed.decisions:
        docs.append({"result_type": "decision", "title": "Decision evidence", "body_text": snippet, "source_ref": parsed.source_path})
    for ref in parsed.file_refs:
        docs.append({"result_type": "file", "title": ref, "body_text": f"File referenced in transcript: {ref}", "file_path": ref, "source_ref": parsed.source_path})
    for sha in parsed.commit_shas:
        docs.append({"result_type": "commit", "title": sha, "body_text": f"Commit referenced in transcript: {sha}", "commit_sha": sha, "source_ref": parsed.source_path})
    for i, ex in enumerate(parse_exchanges(parsed.transcript_text)[:100]):
        docs.append({"result_type": "turn", "title": f"{ex['role']} turn {i + 1}", "body_text": ex["text"], "source_ref": parsed.source_path})
    return docs
