from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    feature_title: str | None = None
    repo_path: str | None = None
    repo_name: str | None = None
    branch_name: str | None = None
    status: str
    start_time: datetime | None = None
    end_time: datetime | None = None
    session_summary: str | None = None
    start_note: str | None = None
    memory_ref: str | None = None
    memory_source_path: str | None = None
    memory_error: str | None = None
    raw_source_text: str | None = None
    transcript_text: str | None = None
    created_at: datetime
    updated_at: datetime


class SessionStart(BaseModel):
    feature_title: str | None = None
    repo_path: str | None = None
    branch_name: str | None = None
    start_note: str | None = None


class LinkCommitIn(BaseModel):
    repo_path: str | None = None
    commit_sha: str


class ImportCodexIn(BaseModel):
    source_path: str


class AgentIn(BaseModel):
    name: str
    source_path: str
    enabled: bool = True


class SearchResult(BaseModel):
    session_id: str
    result_type: str
    title: str
    body_text: str
    commit_sha: str | None = None
    file_path: str | None = None
    source_ref: str | None = None
    score: int
    evidence_summary: dict[str, Any]


class RemoteProjectIn(BaseModel):
    name: str
    description: str | None = None
    debug_mode_enabled: bool = True


class RemoteDeveloperIn(BaseModel):
    name: str
    email: str
    tool_name: str | None = None
    fetch_url: str | None = None
    active: bool = True


class RemoteSessionUploadIn(BaseModel):
    project_id: int | None = None
    project_name: str | None = None
    developer_email: str | None = None
    developer_name: str | None = None
    tool_name: str | None = None
    external_session_id: str | None = None
    title: str | None = None
    repo_path: str | None = None
    repo_name: str | None = None
    branch_name: str | None = None
    transcript_text: str | None = None
    raw_source_text: str | None = None
    session_summary: str | None = None
    source_ref: str | None = None
    occurred_at: datetime | None = None
    issue_count: int = 0


class RemoteFetchIn(BaseModel):
    project_id: int | None = None
    project_name: str | None = None
    source_url: str
    developer_email: str | None = None
    tool_name: str | None = None


class RemoteDebugBriefIn(BaseModel):
    project_id: int | None = None
    developer_id: int | None = None
    query: str | None = None
    llm_mode: str = "local"
