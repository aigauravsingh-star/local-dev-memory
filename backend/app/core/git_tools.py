from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class CommitInfo:
    commit_sha: str
    commit_message: str
    author_name: str
    author_email: str
    author_time: datetime | None
    diff_summary: str
    changed_files: list[str]


def _git(repo: str | Path, args: list[str]) -> str:
    repo_path = str(Path(repo).resolve())
    cmd = ["git", "-c", f"safe.directory={repo_path}", "-C", repo_path, *args]
    completed = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return completed.stdout.strip()


def resolve_repo(repo_path: str | Path) -> dict[str, str]:
    root = _git(repo_path, ["rev-parse", "--show-toplevel"])
    branch = _git(root, ["branch", "--show-current"]) or "HEAD"
    return {"repo_root": root, "branch": branch}


def _parse_git_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def inspect_commit(repo_path: str | Path, sha: str) -> CommitInfo:
    root = resolve_repo(repo_path)["repo_root"]
    fmt = "%H%x1f%s%x1f%an%x1f%ae%x1f%aI"
    raw = _git(root, ["show", "-s", f"--format={fmt}", sha])
    full_sha, msg, author, email, when = raw.split("\x1f", 4)
    diff = _git(root, ["show", "--stat", "--oneline", "--no-renames", "--format=", full_sha])
    files_raw = _git(root, ["diff-tree", "--root", "--no-commit-id", "--name-only", "-r", full_sha])
    return CommitInfo(
        commit_sha=full_sha,
        commit_message=msg,
        author_name=author,
        author_email=email,
        author_time=_parse_git_time(when),
        diff_summary=diff,
        changed_files=[line for line in files_raw.splitlines() if line.strip()],
    )


def _configured_user(repo_path: str | Path) -> tuple[str | None, str | None]:
    name = email = None
    try:
        name = _git(repo_path, ["config", "user.name"]) or None
    except subprocess.CalledProcessError:
        pass
    try:
        email = _git(repo_path, ["config", "user.email"]) or None
    except subprocess.CalledProcessError:
        pass
    return name, email


def find_commits_in_window(repo_path: str | Path, branch: str, start_time: datetime | None, end_time: datetime | None, limit: int = 5) -> list[CommitInfo]:
    root = resolve_repo(repo_path)["repo_root"]
    _, email = _configured_user(root)
    args = ["log", branch or "HEAD", "--format=%H"]
    if start_time:
        args.append(f"--since={start_time.isoformat()}")
    if end_time:
        args.append(f"--until={end_time.isoformat()}")
    if email:
        args.append(f"--author={email}")
    shas = _git(root, [*args, "-n", str(max(1, limit))]).splitlines()
    return [inspect_commit(root, sha) for sha in shas[:limit]]


def find_branch_commits_by_author(repo_path: str | Path, branch: str | None = None) -> list[CommitInfo]:
    root = resolve_repo(repo_path)["repo_root"]
    _, email = _configured_user(root)
    args = ["log", branch or "HEAD", "--format=%H", "-n", "50"]
    if email:
        args.append(f"--author={email}")
    shas = _git(root, args).splitlines()
    return [inspect_commit(root, sha) for sha in shas]
