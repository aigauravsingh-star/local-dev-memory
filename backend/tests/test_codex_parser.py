import json

from app.core.memory import parse_codex_jsonl


def test_codex_jsonl_parser_handles_core_events(tmp_path):
    path = tmp_path / "rollout-test.jsonl"
    rows = [
        {"type": "session_meta", "session_id": "s1", "cwd": str(tmp_path), "branch": "main", "timestamp": "2026-01-01T00:00:00Z"},
        {"type": "turn_context", "cwd": str(tmp_path), "branch": "feature"},
        {"type": "event_msg", "role": "user", "message": "Please edit backend/app/main.py"},
        {"type": "response_item", "role": "assistant", "content": "Decision: use local search because no hosted LLMs. Commit abcdef1234567"},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    parsed = parse_codex_jsonl(path)
    assert parsed.session_id == "s1"
    assert parsed.branch_name == "feature"
    assert "backend/app/main.py" in parsed.file_refs
    assert "abcdef1234567" in parsed.commit_shas
    assert parsed.decisions


def test_codex_jsonl_parser_skips_environment_context_prompt(tmp_path):
    path = tmp_path / "rollout-env.jsonl"
    rows = [
        {"type": "event_msg", "role": "user", "message": "<environment_context><cwd>c:\\repo</cwd><shell>powershell</shell><current_date>2026-05-23</current_date></environment_context>"},
        {"type": "event_msg", "role": "user", "message": "Implement searchable session summaries"},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    parsed = parse_codex_jsonl(path)
    assert parsed.prompt_preview == "Implement searchable session summaries"
