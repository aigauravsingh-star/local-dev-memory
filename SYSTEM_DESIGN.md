# Local Dev Memory - System Design and Architecture

## 1. Product Summary

Local Dev Memory is a private developer memory system that indexes coding-agent sessions and turns them into searchable engineering evidence.

It supports:

- Local developer session browsing.
- Codex session import.
- Search by file, repo, commit, decision, and text.
- Session evidence extraction.
- What Changed analysis.
- Remote Debug Mode for team sessions.
- Local AI-style debug briefs.
- Export to JSON and Markdown.

## 2. High-Level Architecture

```mermaid
flowchart LR
    U[User / Developer] --> UI[React Frontend]
    UI --> API[FastAPI Backend]
    API --> DB[(SQLite Local Database)]
    API --> FS[Local Codex Session Files]
    API --> GIT[Local Git Repositories]
    API --> IDX[Search Evidence Index]
    API --> REM[Remote Debug Ingest]
    REM --> DB
    REM --> IDX
    API --> LLM[Local AI Debug Brief / Future LLM Connector]
```

## 3. Main Components

### Frontend

Technology:

- React
- Webpack
- CSS

Responsibilities:

- Local session browsing.
- Search UI.
- Session viewer tabs.
- Remote Debug Mode board.
- Demo mode.
- Upload forms.
- AI debug brief UI.
- Export links.

### Backend

Technology:

- FastAPI
- SQLAlchemy async
- SQLite

Responsibilities:

- Session APIs.
- Codex import APIs.
- Search APIs.
- Remote Debug APIs.
- Evidence extraction.
- Git commit inspection.
- Export generation.

### Database

Current database:

- SQLite local database

Main tables:

- `sessions`
- `session_events`
- `session_commits`
- `session_files`
- `session_search_docs`
- `agent_sources`
- `remote_projects`
- `remote_developers`
- `remote_session_ingests`

### Evidence Layer

The evidence layer extracts:

- user goal,
- session summary,
- decision snippets,
- file references,
- commit references,
- commands,
- tests,
- errors,
- outcomes,
- open questions,
- quality score,
- what changed data.

## 4. Local Mode Flow

```mermaid
sequenceDiagram
    participant User
    participant UI as React UI
    participant API as FastAPI
    participant Parser as Codex Parser
    participant DB as SQLite

    User->>UI: Open Local Dev Memory
    UI->>API: GET /api/v1/imports/codex-sessions
    API->>Parser: Scan local Codex rollout files
    Parser-->>API: Session candidates
    API-->>UI: Candidate list
    User->>UI: Import or open session
    UI->>API: POST /api/v1/imports/codex-sessions
    API->>Parser: Parse transcript and events
    API->>DB: Store session, files, events, search docs
    API-->>UI: Session id
    UI->>API: GET /api/v1/sessions/{id}/view
    API-->>UI: Summary and evidence
```

## 5. Remote Debug Mode Flow

```mermaid
sequenceDiagram
    participant Lead as Team Lead
    participant Dev as Developer / Agent
    participant UI as React UI
    participant API as FastAPI
    participant DB as SQLite
    participant Search as Evidence Search

    Lead->>UI: Create remote project
    UI->>API: POST /api/v1/remote/projects
    API->>DB: Save project

    Lead->>UI: Add developer
    UI->>API: POST /api/v1/remote/projects/{id}/developers
    API->>DB: Save developer

    Dev->>API: Upload remote session JSON
    API->>DB: Save remote ingest and session
    API->>Search: Create evidence docs

    Lead->>UI: Open Remote Debug Mode
    UI->>API: GET /api/v1/remote/debug-board
    API-->>UI: Projects, developers, sessions, hotspots

    Lead->>UI: Generate AI debug brief
    UI->>API: POST /api/v1/remote/debug-brief
    API-->>UI: Local evidence-based debug brief
```

## 6. User Flow Diagram

```mermaid
flowchart TD
    A[Open App] --> B{Choose Mode}
    B --> C[Local Mode]
    B --> D[Remote Debug Mode]

    C --> C1[Browse Codex Sessions]
    C1 --> C2[Select Session]
    C2 --> C3[View Summary]
    C3 --> C4[Open What Changed]
    C4 --> C5[Search / Timeline / Transcript / Export]

    D --> D1[Create or Select Project]
    D1 --> D2[Add Developers]
    D2 --> D3[Upload or Fetch Sessions]
    D3 --> D4[View Debug Board]
    D4 --> D5[Filter by Project / Developer / Issue]
    D5 --> D6[Generate AI Debug Brief]
    D6 --> D7[Open Related Session Viewer]
```

## 7. Session Viewer Tabs

```mermaid
flowchart LR
    S[Selected Session] --> O[Overview]
    S --> SUM[Summary]
    S --> WC[What Changed]
    S --> CD[Commit Detail]
    S --> TL[Timeline]
    S --> RT[Recent Turns]
    S --> TR[Transcript]
    S --> EX[Explorer]
    S --> SR[Search Results]
```

## 8. Remote Debug Board Data Model

```mermaid
erDiagram
    REMOTE_PROJECT ||--o{ REMOTE_DEVELOPER : has
    REMOTE_PROJECT ||--o{ REMOTE_SESSION_INGEST : receives
    REMOTE_DEVELOPER ||--o{ REMOTE_SESSION_INGEST : uploads
    SESSION ||--o{ SESSION_EVENT : contains
    SESSION ||--o{ SESSION_FILE : references
    SESSION ||--o{ SESSION_COMMIT : links
    SESSION ||--o{ SESSION_SEARCH_DOC : indexes
    REMOTE_SESSION_INGEST }o--|| SESSION : creates
```

## 9. API Surface

### Local Sessions

- `GET /api/v1/sessions`
- `GET /api/v1/sessions/{id}/view`
- `GET /api/v1/sessions/{id}/evidence`
- `GET /api/v1/sessions/{id}/timeline`
- `POST /api/v1/sessions/{id}/link-commit`
- `GET /api/v1/sessions/{id}/export.json`
- `GET /api/v1/sessions/{id}/export.md`

### Imports

- `GET /api/v1/imports/codex-sessions`
- `POST /api/v1/imports/codex-sessions`
- `POST /api/v1/imports/codex-sessions/reindex`

### Search

- `GET /api/v1/search?q=...`

### Remote Debug

- `GET /api/v1/remote/overview`
- `GET /api/v1/remote/debug-board`
- `POST /api/v1/remote/debug-brief`
- `POST /api/v1/remote/projects`
- `POST /api/v1/remote/projects/{project_id}/developers`
- `POST /api/v1/remote/sessions/upload`
- `POST /api/v1/remote/demo`
- `POST /api/v1/remote/fetch`

## 10. LLM Integration Design

Current mode:

- Local evidence-based debug brief.
- No private data needs to leave the machine.

Future LLM mode:

```mermaid
flowchart LR
    UI[Remote Debug UI] --> API[Debug Brief API]
    API --> Evidence[Session Evidence Payload]
    Evidence --> Policy[Privacy / Redaction Layer]
    Policy --> LLM{LLM Provider}
    LLM --> Local[Local Model]
    LLM --> Private[Private Enterprise LLM]
    LLM --> Hosted[Hosted LLM API]
    Local --> API
    Private --> API
    Hosted --> API
    API --> UI
```

LLM should receive:

- scoped project,
- developer sessions,
- summaries,
- decisions,
- files,
- commands,
- tests,
- errors,
- issue counts,
- hotspot files,
- related commits.

LLM should return:

- likely root causes,
- risky files,
- related sessions,
- next debugging actions,
- confidence and evidence citations.

## 11. Security and Privacy

Current protections:

- local-first storage,
- secret redaction patterns,
- local SQLite index,
- no mandatory external LLM,
- source files are not deleted when index is cleared.

Recommended production upgrades:

- authentication,
- role-based access control,
- project-level permissions,
- audit logs,
- encrypted database or disk-level encryption,
- secure remote upload token,
- per-project retention policy,
- private LLM routing,
- PII and secret detection improvements.

## 12. Deployment Model

### Local Developer Mode

```mermaid
flowchart LR
    Browser --> Frontend[Webpack Dev Server]
    Frontend --> Backend[FastAPI Uvicorn]
    Backend --> SQLite[(SQLite)]
    Backend --> Codex[Local Codex Sessions]
    Backend --> Git[Local Git]
```

### Team / Remote Mode

```mermaid
flowchart LR
    DeveloperAgents[Developer Coding Agents] --> UploadAPI[Remote Upload API]
    UploadAPI --> Backend[FastAPI]
    Backend --> DB[(Shared DB)]
    TeamLead[Team Lead Browser] --> Frontend[React UI]
    Frontend --> Backend
    Backend --> LLM[Optional Private LLM]
```

## 13. Product Strengths

- Clear local developer value.
- Strong team debugging direction.
- Works with AI coding-agent sessions.
- Converts transcripts into structured evidence.
- Searchable by engineering context, not just code.
- Remote mode supports project and developer analysis.
- Local AI-style brief avoids immediate dependency on hosted LLMs.

## 14. Product Gaps

- Needs authentication before real team deployment.
- Needs automatic session uploader.
- Needs stronger GitHub/GitLab integration.
- Needs production database option.
- Needs background indexing for scale.
- Needs real LLM connector for advanced reasoning.
- Needs better enterprise admin controls.

## 15. Roadmap

1. Add authentication and project roles.
2. Add automatic developer session uploader.
3. Add GitHub/GitLab commit and PR integration.
4. Add private LLM connector.
5. Add issue tracker integration.
6. Add deployment scripts for team server mode.
7. Add audit logs and retention policies.
8. Add advanced analytics dashboard.

