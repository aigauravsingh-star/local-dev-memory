import json
import subprocess
import uuid

from fastapi.testclient import TestClient

from app.main import app


def test_api_smoke_health_sessions_imports_search(tmp_path):
    source_root = tmp_path / "codex"
    source_root.mkdir()
    source = source_root / "rollout-api.jsonl"
    session_id = f"api-test-{uuid.uuid4().hex}"
    source.write_text(
        "\n".join(
            [
                json.dumps({"type": "session_meta", "session_id": session_id, "cwd": str(tmp_path), "branch": "main"}),
                json.dumps({"type": "event_msg", "role": "user", "message": "Fix frontend/src/App.js"}),
                json.dumps({"type": "response_item", "role": "assistant", "content": "Decision: changed App.js because layout needed wrapping. Commit abcdef1234567"}),
            ]
        ),
        encoding="utf-8",
    )
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        client.post("/api/v1/agents", json={"name": "test codex", "source_path": str(source_root)}).raise_for_status()
        started = client.post("/api/v1/sessions/start", json={"feature_title": "Manual"}).json()
        assert started["status"] == "open"
        imported = client.post("/api/v1/imports/codex-sessions", json={"source_path": str(source)}).json()
        assert imported["duplicate"] is False
        evidence = client.get(f"/api/v1/sessions/{session_id}/evidence").json()
        assert evidence["user_goal"]
        assert "commands_run" in evidence
        assert "errors" in evidence
        assert "what_changed" in evidence
        assert "quality_score" in evidence
        assert "commit_suggestions" in evidence
        view = client.get(f"/api/v1/sessions/{session_id}/view").json()
        assert view["session"]["id"] == session_id
        assert view["session"]["display_title"]
        assert view["session"]["transcript_text"]
        assert view["session"]["raw_source_text"]
        assert view["evidence"]["user_goal"]
        duplicate = client.post("/api/v1/imports/codex-sessions", json={"source_path": str(source)}).json()
        assert duplicate["duplicate"] is True
        results = client.get("/api/v1/search?q=App.js").json()
        assert results
        assert client.get(f"/api/v1/search?q=App.js&session_id={session_id}").json()
        assert client.get(f"/api/v1/search?q=App.js&session_id={started['id']}").json() == []
        exported = client.get(f"/api/v1/sessions/{session_id}/export.json").json()
        assert exported["evidence"]["user_goal"]
        assert "## User Goal" in client.get(f"/api/v1/sessions/{session_id}/export.md").text
        exported_all = client.get("/api/v1/export/sessions.jsonl").text
        assert '"evidence"' in exported_all
        demo = client.post("/api/v1/sessions/demo").json()
        assert demo["session_id"].startswith("demo-")
        assert client.get("/api/v1/sessions").json()
        assert client.delete(f"/api/v1/sessions/{started['id']}").json()["deleted"] is True
        cleared = client.delete("/api/v1/sessions").json()
        assert cleared["sessions_deleted"] >= 1


def test_import_redacts_timestamps_and_reindex_preserves_evidence(tmp_path):
    source_root = tmp_path / "codex"
    source_root.mkdir()
    source = source_root / "rollout-rich.jsonl"
    session_id = f"rich-{uuid.uuid4().hex}"
    source.write_text(
        "\n".join(
            [
                json.dumps({"type": "session_meta", "session_id": session_id, "cwd": str(tmp_path), "branch": "main", "timestamp": "2026-01-01T00:00:00Z"}),
                json.dumps({"type": "event_msg", "role": "user", "message": "Fix backend/app/main.py api_key=supersecret", "timestamp": "2026-01-01T00:01:00Z"}),
                json.dumps({"type": "response_item", "role": "assistant", "content": "Decision: changed backend/app/main.py because startup failed. Commit abcdef1234567 Bearer secretbearertoken123456", "timestamp": "2026-01-01T00:02:00Z"}),
            ]
        ),
        encoding="utf-8",
    )
    with TestClient(app) as client:
        client.post("/api/v1/agents", json={"name": "rich codex", "source_path": str(source_root)}).raise_for_status()
        imported = client.post("/api/v1/imports/codex-sessions", json={"source_path": str(source)}).json()
        assert imported["duplicate"] is False
        timeline = client.get(f"/api/v1/sessions/{session_id}/timeline").json()
        assert timeline[0]["time"]
        assert "supersecret" not in json.dumps(timeline)
        assert client.get("/api/v1/search?q=backend/app/main.py").json()
        assert client.get("/api/v1/search?q=abcdef1234567").json()
        assert client.get("/api/v1/search?q=why").json()[0]["result_type"] == "decision"
        source.write_text(
            "\n".join(
                [
                    json.dumps({"type": "session_meta", "session_id": session_id, "cwd": str(tmp_path), "branch": "main", "timestamp": "2026-01-01T00:00:00Z"}),
                    json.dumps({"type": "event_msg", "role": "user", "message": "Fix backend/app/local_mode.py", "timestamp": "2026-01-01T00:03:00Z"}),
                    json.dumps({"type": "response_item", "role": "assistant", "content": "Decision: changed backend/app/local_mode.py because local mode diagnostics were incomplete. Commit abcdef1234567", "timestamp": "2026-01-01T00:04:00Z"}),
                ]
            ),
            encoding="utf-8",
        )
        client.post("/api/v1/imports/codex-sessions/reindex").raise_for_status()
        assert any(r["result_type"] == "file" for r in client.get("/api/v1/search?q=backend/app/local_mode.py").json())
        assert any(r["result_type"] == "commit" for r in client.get("/api/v1/search?q=abcdef1234567").json())
        assert client.get("/api/v1/search?q=%").json() == []


def run(cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def test_link_commit_is_idempotent(tmp_path):
    run(["git", "init"], tmp_path)
    run(["git", "config", "user.email", "dev@example.com"], tmp_path)
    run(["git", "config", "user.name", "Dev"], tmp_path)
    (tmp_path / "file.txt").write_text("hello", encoding="utf-8")
    run(["git", "add", "file.txt"], tmp_path)
    run(["git", "commit", "-m", "initial"], tmp_path)
    with TestClient(app) as client:
        session = client.post("/api/v1/sessions/start", json={"feature_title": "Commit test", "repo_path": str(tmp_path)}).json()
        first = client.post(f"/api/v1/sessions/{session['id']}/link-commit", json={"commit_sha": "HEAD"}).json()
        second = client.post(f"/api/v1/sessions/{session['id']}/link-commit", json={"commit_sha": "HEAD"}).json()
        assert first["commit"]["commit_sha"] == second["commit"]["commit_sha"]
        assert second["duplicate"] is True


def test_remote_debug_upload_indexes_team_session():
    with TestClient(app) as client:
        project = client.post(
            "/api/v1/remote/projects",
            json={"name": f"Remote Project {uuid.uuid4().hex}", "description": "Team debug mode"},
        ).json()
        project_id = project["project_id"]
        developer = client.post(
            f"/api/v1/remote/projects/{project_id}/developers",
            json={"name": "Dev One", "email": "dev1@example.com", "tool_name": "Codex"},
        ).json()
        assert developer["developer_id"]
        uploaded = client.post(
            "/api/v1/remote/sessions/upload",
            json={
                "project_id": project_id,
                "developer_email": "dev1@example.com",
                "developer_name": "Dev One",
                "tool_name": "Codex",
                "external_session_id": f"remote-session-{uuid.uuid4().hex}",
                "title": "Fix remote checkout issue",
                "repo_name": "checkout-service",
                "branch_name": "debug/retry",
                "session_summary": "Debugged checkout retry failure.",
                "transcript_text": "user: Fix checkout retry\nassistant: Decision: changed checkout_service.py because retries duplicated charges.",
                "issue_count": 1,
            },
        ).json()
        assert uploaded["duplicate"] is False
        view = client.get(f"/api/v1/sessions/{uploaded['session_id']}/view").json()
        assert view["session"]["status"] == "remote-debug"
        assert view["evidence"]["user_goal"]
        overview = client.get("/api/v1/remote/overview").json()
        assert overview["remote_session_count"] >= 1
        assert any(item["session_id"] == uploaded["session_id"] for item in overview["recent_uploads"])
        assert client.get("/api/v1/search?q=checkout_service.py").json()


def test_remote_demo_mode_seeds_dummy_team_data():
    with TestClient(app) as client:
        demo = client.post("/api/v1/remote/demo").json()
        assert demo["developers"] == 10
        assert demo["sessions"] >= 1
        assert demo["session_id"]
        overview = client.get("/api/v1/remote/overview").json()
        assert overview["developer_count"] >= 10
        assert overview["remote_session_count"] >= demo["sessions"]
        assert overview["developers"]
        assert overview["hotspots"]["files"]
        board = client.get(f"/api/v1/remote/debug-board?project_id={demo['project_id']}&q=retry").json()
        assert board["sessions"]
        assert board["stats"]["llm_status"]
        brief = client.post(
            "/api/v1/remote/debug-brief",
            json={"project_id": demo["project_id"], "query": "What should the team debug first?", "llm_mode": "local"},
        ).json()
        assert brief["llm_ready"] is True
        assert brief["answer"]["next_actions"]
        view = client.get(f"/api/v1/sessions/{demo['session_id']}/view").json()
        assert view["session"]["status"] == "remote-debug"
        assert client.get("/api/v1/search?q=retry_policy.py").json()
