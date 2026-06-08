from __future__ import annotations

import re
from collections import Counter

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.I | re.S),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}", re.I),
    re.compile(r"\b(api[_-]?key|token|password|passwd|pwd|secret)\s*[:=]\s*['\"]?[^'\"\s,;]{6,}", re.I),
    re.compile(r"\b(?:postgres|mysql|mongodb|redis)://[^\s'\"<>]+", re.I),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
]

SHA_RE = re.compile(r"\b[0-9a-f]{7,40}\b", re.I)
FILE_RE = re.compile(r"(?<![\w.-])(?:[A-Za-z]:)?(?:\.{1,2}[/\\])?(?:[\w.-]+[/\\])+[\w.-]+\.[A-Za-z0-9]{1,12}\b")
DECISION_RE = re.compile(r"\b(decided|decision|because|reason|rationale|chose|instead|therefore|so that|fix|root cause)\b", re.I)
COMMAND_RE = re.compile(r"(?:^|\s)(?:python|pytest|npm|yarn|pnpm|git|uvicorn|powershell|cmd|pip|ruff|mypy|eslint|webpack|uv|poetry|docker)\b[^\n\r]{0,240}", re.I)
TEST_RE = re.compile(r"\b(test|tests|pytest|unittest|jest|vitest|playwright|build|compiled|passed|failed)\b", re.I)
ERROR_RE = re.compile(r"\b(error|failed|failure|exception|traceback|warning|not found|denied|blocked|crash|broken)\b", re.I)
OUTCOME_RE = re.compile(r"\b(done|fixed|implemented|updated|completed|verified|passed|successful|compiled successfully|tests? passed)\b", re.I)
OPEN_QUESTION_RE = re.compile(r"\b(todo|follow[- ]?up|remaining|not able|could not|needs?|open question|next step|blocked)\b", re.I)


def redact_secrets(text: str | None) -> str:
    if not text:
        return ""
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def extract_commit_shas(text: str | None) -> list[str]:
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for match in SHA_RE.findall(text):
        sha = match.lower()
        if sha not in seen:
            seen.add(sha)
            out.append(sha)
    return out


def extract_file_refs(text: str | None) -> list[str]:
    if not text:
        return []
    seen: set[str] = set()
    refs: list[str] = []
    for match in FILE_RE.findall(text):
        ref = match.strip("`'\" .,;:")
        if ref and ref not in seen:
            seen.add(ref)
            refs.append(ref)
    return refs


def extract_decision_snippets(text: str | None, limit: int = 12) -> list[str]:
    if not text:
        return []
    snippets: list[str] = []
    for paragraph in re.split(r"\n{2,}|(?<=[.!?])\s+", text):
        clean = paragraph.strip()
        if len(clean) > 40 and DECISION_RE.search(clean):
            snippets.append(clean[:600])
        if len(snippets) >= limit:
            break
    return snippets


def extract_matching_snippets(text: str | None, pattern: re.Pattern[str], limit: int = 8) -> list[str]:
    if not text:
        return []
    snippets: list[str] = []
    seen: set[str] = set()
    for paragraph in re.split(r"\n{2,}|(?<=[.!?])\s+", text):
        clean = clean_codex_display_text(paragraph)
        if len(clean) > 12 and pattern.search(clean):
            snippet = clean[:600]
            if snippet not in seen:
                seen.add(snippet)
                snippets.append(snippet)
        if len(snippets) >= limit:
            break
    return snippets


def extract_commands(text: str | None, limit: int = 12) -> list[str]:
    if not text:
        return []
    commands: list[str] = []
    seen: set[str] = set()
    for match in COMMAND_RE.findall(text):
        command = clean_codex_display_text(match)
        if command and command not in seen:
            seen.add(command)
            commands.append(command[:260])
        if len(commands) >= limit:
            break
    return commands


def parse_exchanges(text: str | None) -> list[dict[str, str]]:
    if not text:
        return []
    exchanges: list[dict[str, str]] = []
    current_role = "unknown"
    buf: list[str] = []
    for line in text.splitlines():
        marker = re.match(r"^\s*(user|assistant|system|tool)\s*:\s*(.*)$", line, re.I)
        if marker:
            if buf:
                exchanges.append({"role": current_role, "text": "\n".join(buf).strip()})
            current_role = marker.group(1).lower()
            buf = [marker.group(2)]
        else:
            buf.append(line)
    if buf:
        exchanges.append({"role": current_role, "text": "\n".join(buf).strip()})
    return [item for item in exchanges if item["text"]]


def build_summary(text: str | None, title: str | None = None) -> str:
    clean = redact_secrets(text or "")
    decisions = extract_decision_snippets(clean, limit=3)
    files = extract_file_refs(clean)[:8]
    shas = extract_commit_shas(clean)[:8]
    parts: list[str] = []
    if title:
        parts.append(title.strip())
    if decisions:
        parts.append("Key reasoning: " + " ".join(decisions))
    elif clean:
        parts.append("Transcript preview: " + clean.strip().replace("\n", " ")[:800])
    if files:
        parts.append("Files: " + ", ".join(files))
    if shas:
        parts.append("Commits: " + ", ".join(shas))
    return "\n".join(parts)[:2500] if parts else "No transcript summary available."


def clean_codex_display_text(text: str | None) -> str:
    if not text:
        return ""
    cleaned = redact_secrets(text)
    cleaned = re.sub(r"<environment_context>.*?</environment_context>", " ", cleaned, flags=re.I | re.S)
    cleaned = re.sub(r"# Context from my IDE setup:.*?(?=(# My request for Codex:|user:|assistant:|$))", " ", cleaned, flags=re.I | re.S)
    cleaned = re.sub(r"## Active file:.*?(?=(##|# My request for Codex:|user:|assistant:|$))", " ", cleaned, flags=re.I | re.S)
    cleaned = re.sub(r"## Open tabs:.*?(?=(##|# My request for Codex:|user:|assistant:|$))", " ", cleaned, flags=re.I | re.S)
    cleaned = re.sub(r"\b(cwd|shell|current_date|timezone)\s*[:=]\s*[^\n<>]+", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" -:\t\r\n")


def extract_user_intention(text: str | None, fallback: str | None = None) -> str:
    for exchange in parse_exchanges(text):
        if exchange["role"] != "user":
            continue
        candidate = exchange["text"]
        if "My request for Codex:" in candidate:
            candidate = candidate.split("My request for Codex:", 1)[1]
        cleaned = clean_codex_display_text(candidate)
        if len(cleaned) >= 8 and not cleaned.lower().startswith("context from my ide"):
            return cleaned[:500]
    return clean_codex_display_text(fallback)[:500] or "No user intention found."


def concise_session_title(text: str | None, fallback: str | None = None) -> str:
    candidate = extract_user_intention(text, fallback)
    candidate = re.sub(
        r"^(my request for codex:|fix required:|update required:|task:|requirement\s*[-:]?)\s*",
        "",
        candidate,
        flags=re.I,
    )
    candidate = re.sub(r"^\d+\.\s*", "", candidate).strip()
    candidate = re.split(r"(?<=[.!?])\s+", candidate)[0]
    candidate = candidate.strip(" -:\t\r\n")
    if re.search(r"^rollout-\d{4}-\d{2}-\d{2}", candidate, re.I):
        candidate = ""
    if not candidate or candidate.lower() in {"manual", "new", "no user intention found"}:
        candidate = clean_codex_display_text(fallback)
    return (candidate[:90].strip(" -:") or "Codex session")


def session_evidence_summary(text: str | None, title: str | None = None) -> dict[str, object]:
    clean = clean_codex_display_text(text)
    files = extract_file_refs(text)[:20]
    commits = extract_commit_shas(text)[:20]
    decisions = [clean_codex_display_text(item) for item in extract_decision_snippets(clean, limit=8)]
    decisions = [item for item in decisions if item]
    commands = extract_commands(text)
    tests = extract_matching_snippets(clean, TEST_RE)
    errors = extract_matching_snippets(clean, ERROR_RE)
    outcomes = extract_matching_snippets(clean, OUTCOME_RE, limit=5)
    open_questions = extract_matching_snippets(clean, OPEN_QUESTION_RE, limit=5)
    intention = extract_user_intention(text, title)
    cleaned_title = clean_codex_display_text(title) or intention
    context = {
        "session_title": cleaned_title[:300],
        "user_intention": intention,
        "activity_summary": build_summary(clean, cleaned_title),
        "decision_count": len(decisions),
        "file_reference_count": len(files),
        "commit_reference_count": len(commits),
        "command_count": len(commands),
        "test_signal_count": len(tests),
        "error_count": len(errors),
    }
    return {
        "what_tried_to_change": intention,
        "intention": intention,
        "user_goal": intention,
        "decision_snippets": decisions,
        "file_changes": files,
        "commit_refs": commits,
        "commands_run": commands,
        "tests_run": tests,
        "errors": errors,
        "outcome": outcomes[0] if outcomes else "Outcome not detected from local transcript evidence.",
        "open_questions": open_questions,
        "summary": build_summary(clean, title),
        "session_context": context,
    }


def classify_query(query: str) -> str:
    q = query.strip()
    if SHA_RE.fullmatch(q) or re.search(r"\bcommit\b|[0-9a-f]{7,40}", q, re.I):
        return "commit"
    if extract_file_refs(q) or re.search(r"\b(file|path|component|module|\.py|\.js|\.tsx|\.css)\b", q, re.I):
        return "file"
    if re.search(r"\b(why|reason|rationale|decision|because|chose|root cause)\b", q, re.I):
        return "decision"
    return "generic"


def keyword_score(query: str, text: str) -> int:
    terms = [t.lower() for t in re.findall(r"[\w.-]{2,}", query)]
    hay = text.lower()
    counts = Counter(term for term in terms if term in hay)
    return sum(counts.values())
