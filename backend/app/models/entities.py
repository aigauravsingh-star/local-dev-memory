from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SchemaVersion(Base):
    __tablename__ = "schema_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AgentSource(Base):
    __tablename__ = "agent_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    feature_title: Mapped[str | None] = mapped_column(String(300))
    repo_path: Mapped[str | None] = mapped_column(Text)
    repo_name: Mapped[str | None] = mapped_column(String(240))
    branch_name: Mapped[str | None] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(40), default="open", index=True)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    session_summary: Mapped[str | None] = mapped_column(Text)
    start_note: Mapped[str | None] = mapped_column(Text)
    memory_ref: Mapped[str | None] = mapped_column(Text)
    memory_source_path: Mapped[str | None] = mapped_column(Text, unique=True)
    memory_error: Mapped[str | None] = mapped_column(Text)
    raw_source_text: Mapped[str | None] = mapped_column(Text)
    transcript_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    events: Mapped[list["SessionEvent"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    commits: Mapped[list["SessionCommit"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    files: Mapped[list["SessionFile"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    search_docs: Mapped[list["SessionSearchDoc"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class SessionEvent(Base):
    __tablename__ = "session_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    message: Mapped[str | None] = mapped_column(Text)
    payload_json: Mapped[str | None] = mapped_column(Text)
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class SessionCommit(Base):
    __tablename__ = "session_commits"
    __table_args__ = (UniqueConstraint("session_id", "commit_sha", name="uq_session_commit"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    commit_sha: Mapped[str] = mapped_column(String(80), index=True)
    commit_message: Mapped[str | None] = mapped_column(Text)
    author_name: Mapped[str | None] = mapped_column(String(240))
    author_email: Mapped[str | None] = mapped_column(String(320))
    author_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    diff_summary: Mapped[str | None] = mapped_column(Text)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SessionFile(Base):
    __tablename__ = "session_files"
    __table_args__ = (UniqueConstraint("session_id", "session_commit_id", "file_path", name="uq_session_file"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    session_commit_id: Mapped[int | None] = mapped_column(ForeignKey("session_commits.id"), nullable=True)
    file_path: Mapped[str] = mapped_column(Text, index=True)


class SessionSearchDoc(Base):
    __tablename__ = "session_search_docs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    result_type: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(Text)
    body_text: Mapped[str] = mapped_column(Text)
    commit_sha: Mapped[str | None] = mapped_column(String(80), index=True)
    file_path: Mapped[str | None] = mapped_column(Text, index=True)
    source_ref: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RemoteProject(Base):
    __tablename__ = "remote_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    debug_mode_enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    developers: Mapped[list["RemoteDeveloper"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    ingests: Mapped[list["RemoteSessionIngest"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class RemoteDeveloper(Base):
    __tablename__ = "remote_developers"
    __table_args__ = (UniqueConstraint("project_id", "email", name="uq_remote_developer_email"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("remote_projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    tool_name: Mapped[str | None] = mapped_column(String(120))
    fetch_url: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RemoteSessionIngest(Base):
    __tablename__ = "remote_session_ingests"
    __table_args__ = (UniqueConstraint("project_id", "external_session_id", name="uq_remote_external_session"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("remote_projects.id"), index=True)
    developer_id: Mapped[int | None] = mapped_column(ForeignKey("remote_developers.id"), nullable=True, index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    external_session_id: Mapped[str] = mapped_column(String(160), index=True)
    tool_name: Mapped[str | None] = mapped_column(String(120))
    source_ref: Mapped[str | None] = mapped_column(Text)
    ingest_status: Mapped[str] = mapped_column(String(40), default="received", index=True)
    issue_count: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
