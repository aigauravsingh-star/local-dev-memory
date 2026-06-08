import subprocess

from app.core.git_tools import inspect_commit, resolve_repo


def run(cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def test_git_commit_inspection_with_temp_repo(tmp_path):
    run(["git", "init"], tmp_path)
    run(["git", "config", "user.email", "dev@example.com"], tmp_path)
    run(["git", "config", "user.name", "Dev"], tmp_path)
    (tmp_path / "file.txt").write_text("hello", encoding="utf-8")
    run(["git", "add", "file.txt"], tmp_path)
    run(["git", "commit", "-m", "initial"], tmp_path)
    root = resolve_repo(tmp_path)
    info = inspect_commit(root["repo_root"], "HEAD")
    assert info.commit_message == "initial"
    assert "file.txt" in info.changed_files
