import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  addAgent,
  addRemoteDeveloper,
  clearSessionIndex,
  createRemoteDemo,
  createRemoteProject,
  createDemoSession,
  diagnostics,
  deleteSession,
  endSession,
  exportSessionJsonUrl,
  exportSessionMarkdownUrl,
  getFacets,
  getSessionView,
  getTimeline,
  health,
  importCodexSession,
  linkCommit,
  listAgents,
  listCodexSessions,
  listSessions,
  reindexCodexSessions,
  remoteDebugBoard,
  remoteDebugBrief,
  remoteOverview,
  searchEvidence,
  uploadRemoteSession,
} from "./api";

function parseExplorer(raw, transcript) {
  if (raw) {
    return raw.split(/\r?\n/).filter(Boolean).map((line, index) => {
      try {
        const item = JSON.parse(line);
        const payload = item.payload || item;
        const role = payload.role || item.role || "";
        const type = item.type || item.event_type || item.name || "event";
        const text = JSON.stringify(item, null, 2);
        const tags = [];
        if (/decision|because|reason|chose|root cause/i.test(text)) tags.push("decision");
        if (/\.[a-z0-9]{1,12}\b|[/\\]/i.test(text)) tags.push("file");
        if (/tool|command|shell/i.test(text)) tags.push("tool");
        return { index, role, type, timestamp: item.timestamp || item.time || "", text, tags, raw: item };
      } catch {
        return { index, role: "", type: "raw", timestamp: "", text: line, tags: [] };
      }
    });
  }
  return (transcript || "").split(/\n{2,}/).filter(Boolean).map((text, index) => ({ index, role: "", type: "transcript", timestamp: "", text, tags: [] }));
}

function formatDateTime(value) {
  if (!value) return "No date";
  return new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function shortText(value, fallback = "Not available") {
  return value || fallback;
}

function todayInputValue() {
  const today = new Date();
  const offset = today.getTimezoneOffset();
  return new Date(today.getTime() - offset * 60000).toISOString().slice(0, 10);
}

function cleanSessionTitle(value) {
  const title = stripTechnicalNoise(value);
  if (!title) return "";
  if (/^rollout-\d{4}-\d{2}-\d{2}/i.test(title)) return "";
  if (/^manual$/i.test(title)) return "";
  if (/^new$/i.test(title)) return "New Codex session";
  return title;
}

function repoName(path) {
  return path ? path.split(/[\\/]/).filter(Boolean).pop() : "";
}

function displayPath(path) {
  if (!path) return "Not available";
  const parts = path.split(/[\\/]/).filter(Boolean);
  if (parts.length <= 3) return path;
  return `.../${parts.slice(-3).join("/")}`;
}

function sessionTitle(item) {
  const title = cleanSessionTitle(item.display_title || item.prompt_preview || item.feature_title || item.title);
  if (title) return title;
  const repo = repoName(item.repo_path) || item.repo_name;
  return repo ? `Codex session in ${repo}` : "Codex session";
}

function dateOnly(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60000).toISOString().slice(0, 10);
}

function inDateWindow(value, from, to) {
  const day = dateOnly(value);
  if (!day) return !from && !to;
  if (from && day < from) return false;
  if (to && day > to) return false;
  return true;
}

function extractFiles(text) {
  return [...new Set((text || "").match(/(?:[A-Za-z]:)?(?:\.{1,2}[/\\])?(?:[\w.-]+[/\\])+[\w.-]+\.[A-Za-z0-9]{1,12}/g) || [])].slice(0, 12);
}

function extractCommits(text) {
  return [...new Set((text || "").match(/\b[0-9a-f]{7,40}\b/gi) || [])].slice(0, 12);
}

function extractDecisions(text) {
  return (text || "")
    .split(/\n{2,}|(?<=[.!?])\s+/)
    .map(part => part.trim())
    .filter(part => part.length > 30 && /decision|because|reason|changed|fixed|implemented|root cause|chose/i.test(part))
    .slice(0, 5);
}

function stripTechnicalNoise(value) {
  return (value || "")
    .replace(/<environment_context>.*?<\/environment_context>/gis, " ")
    .replace(/\b(cwd|shell|current_date|timezone)\s*[:=]\s*[^\n<>]+/gi, " ")
    .replace(/rollout-\d{4}-\d{2}-\d{2}T[\w.-]+\.jsonl/gi, "")
    .replace(/[A-Za-z]:\\[^\s]+/g, "")
    .replace(/(?:\.{1,2}[/\\])?(?:[\w.-]+[/\\])+[\w.-]+\.[A-Za-z0-9]{1,12}/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function sessionSummaryText(row) {
  const source = row.summary || row.title || "";
  const cleaned = stripTechnicalNoise(source);
  if (cleaned.length > 20) return cleaned.slice(0, 220);
  if (row.imported) return "Imported Codex session with searchable conversation, file, decision, and commit evidence.";
  return "Codex session available to import and review.";
}

function App() {
  const [healthState, setHealthState] = useState(null);
  const [diag, setDiag] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [selected, setSelected] = useState(null);
  const [openingSessionId, setOpeningSessionId] = useState("");
  const latestOpenRef = useRef("");
  const [evidence, setEvidence] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [facets, setFacets] = useState({ statuses: [], repositories: [], branches: [], counts: {} });
  const [tab, setTab] = useState("Summary");
  const [filters, setFilters] = useState({ status: "", repo: "", branch: "", date_from: "", date_to: "" });
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [searchState, setSearchState] = useState("idle");
  const [searchScope, setSearchScope] = useState("all");
  const [sessionQuery, setSessionQuery] = useState("");
  const [candidates, setCandidates] = useState([]);
  const [importQuery, setImportQuery] = useState("");
  const [importsOpen, setImportsOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [remoteOpen, setRemoteOpen] = useState(false);
  const [remoteState, setRemoteState] = useState(null);
  const [remoteBoard, setRemoteBoard] = useState(null);
  const [remoteFilters, setRemoteFilters] = useState({ project_id: "", developer_id: "", q: "" });
  const [remoteBrief, setRemoteBrief] = useState(null);
  const [remoteQuestion, setRemoteQuestion] = useState("What should the team debug first?");
  const [remoteUpload, setRemoteUpload] = useState("");
  const [showDetectedAgents, setShowDetectedAgents] = useState(true);
  const [agents, setAgents] = useState(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [commitSha, setCommitSha] = useState("");
  const [explorerFilters, setExplorerFilters] = useState({ role: "", type: "", focus: "all", text: "", raw: false, page: 0 });

  async function refresh(openId, nextFilters = filters) {
    const [h, d, s, f] = await Promise.all([
      health().catch(e => ({ error: e.message })),
      diagnostics().catch(e => ({ error: e.message })),
      listSessions(nextFilters).catch(() => []),
      getFacets().catch(() => ({ statuses: [], repositories: [], branches: [], counts: {} }))
    ]);
    setHealthState(h);
    setDiag(d);
    setSessions(s);
    setFacets(f);
    const meaningful = s.find(item => item.session_summary || item.transcript_text || item.memory_ref);
    const target = openId === null ? (meaningful?.id || s[0]?.id) : (openId || selected?.id || meaningful?.id || s[0]?.id);
    if (target) openSession(target);
  }

  async function openSession(id) {
    try {
      latestOpenRef.current = id;
      setOpeningSessionId(id);
      setNotice("");
      setTimeline([]);
      const view = await getSessionView(id);
      setSelected(view.session);
      setEvidence(view.evidence);
      setResults([]);
      setTab("Summary");
      requestAnimationFrame(() => document.querySelector(".detail")?.scrollIntoView({ behavior: "smooth", block: "start" }));
      getTimeline(id)
        .then(tl => {
          if (latestOpenRef.current === id) setTimeline(tl);
        })
        .catch(() => {
          if (latestOpenRef.current === id) setTimeline([]);
        });
    } catch (error) {
      setNotice(`Could not open session: ${error.message}`);
    } finally {
      setOpeningSessionId("");
    }
  }

  async function removeSelectedSession() {
    if (!selected) return;
    if (!window.confirm("Delete this local session from the index? Source Codex files are not deleted.")) return;
    try {
      setBusy("Deleting session index entry...");
      await deleteSession(selected.id);
      setNotice("Deleted local session index entry. Source files were left untouched.");
      setSelected(null);
      setEvidence(null);
      setTimeline([]);
      await refresh(null);
    } catch (error) {
      setNotice(`Could not delete session: ${error.message}`);
    } finally {
      setBusy("");
    }
  }

  async function createDemo() {
    try {
      setBusy("Creating demo session...");
      const res = await createDemoSession();
      setNotice("Demo session created.");
      await refresh(res.session_id);
    } catch (error) {
      setNotice(`Could not create demo session: ${error.message}`);
    } finally {
      setBusy("");
    }
  }

  async function clearAllSessions() {
    if (!window.confirm("Clear the entire local session index? Original Codex files and repositories are not deleted.")) return;
    try {
      setBusy("Clearing local index...");
      const res = await clearSessionIndex();
      setSelected(null);
      setEvidence(null);
      setTimeline([]);
      setNotice(`Cleared ${res.sessions_deleted} local session index entries. Source files were left untouched.`);
      await refresh(null);
    } catch (error) {
      setNotice(`Could not clear local index: ${error.message}`);
    } finally {
      setBusy("");
    }
  }

  useEffect(() => { refresh(); }, []);
  useEffect(() => { listCodexSessions(200).then(setCandidates).catch(e => setNotice(e.message)); }, []);
  useEffect(() => { refreshRemote(); }, []);

  async function refreshRemote(nextFilters = remoteFilters) {
    const [overview, board] = await Promise.all([
      remoteOverview(),
      remoteDebugBoard(nextFilters).catch(() => null),
    ]);
    setRemoteState(overview);
    setRemoteBoard(board);
  }

  async function submitRemoteProject(e) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    try {
      setBusy("Saving remote project...");
      await createRemoteProject({
        name: fd.get("name"),
        description: fd.get("description"),
        debug_mode_enabled: true,
      });
      e.currentTarget.reset();
      await refreshRemote();
      setNotice("Remote debug project saved.");
    } catch (error) {
      setNotice(`Could not save remote project: ${error.message}`);
    } finally {
      setBusy("");
    }
  }

  async function submitRemoteDeveloper(e) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const projectId = fd.get("project_id");
    if (!projectId) return;
    try {
      setBusy("Saving developer...");
      await addRemoteDeveloper(projectId, {
        name: fd.get("name"),
        email: fd.get("email"),
        tool_name: fd.get("tool_name"),
        fetch_url: fd.get("fetch_url"),
        active: true,
      });
      e.currentTarget.reset();
      await refreshRemote();
      setNotice("Developer added to remote debug project.");
    } catch (error) {
      setNotice(`Could not add developer: ${error.message}`);
    } finally {
      setBusy("");
    }
  }

  async function submitRemoteUpload(e) {
    e.preventDefault();
    try {
      const payload = JSON.parse(remoteUpload);
      setBusy("Uploading remote debug session...");
      const res = await uploadRemoteSession(payload);
      setRemoteUpload("");
      await Promise.all([refreshRemote(), refresh(res.session_id)]);
      setNotice(res.duplicate ? "Remote session was already indexed; opening existing session." : "Remote session uploaded and indexed for debug mode.");
    } catch (error) {
      setNotice(`Remote upload failed: ${error.message}`);
    } finally {
      setBusy("");
    }
  }

  async function createRemoteDemoMode() {
    try {
      setBusy("Creating remote demo data...");
      const res = await createRemoteDemo();
      setRemoteOpen(true);
      await Promise.all([refreshRemote(), refresh(res.session_id)]);
      setNotice(`Demo mode ready: ${res.developers} developers and ${res.sessions} remote sessions are indexed.`);
    } catch (error) {
      setNotice(`Could not create remote demo data: ${error.message}`);
    } finally {
      setBusy("");
    }
  }

  async function runRemoteBrief() {
    try {
      setBusy("Preparing remote debug brief...");
      const brief = await remoteDebugBrief({
        project_id: remoteFilters.project_id || null,
        developer_id: remoteFilters.developer_id || null,
        query: remoteQuestion,
        llm_mode: "local",
      });
      setRemoteBrief(brief);
      setRemoteOpen(true);
    } catch (error) {
      setNotice(`Could not prepare remote debug brief: ${error.message}`);
    } finally {
      setBusy("");
    }
  }

  async function searchRemoteEvidence(queryText) {
    const text = queryText || remoteFilters.q || remoteQuestion;
    if (!text?.trim()) return;
    setQuery(text);
    setSearchScope("all");
    setSearchState("loading");
    try {
      const matches = await searchEvidence(text);
      setResults(matches.filter(item => item.session_id?.startsWith("remote-") || item.result_type));
      setSearchState(matches.length ? "done" : "empty");
      setTab("Search results");
    } catch (error) {
      setNotice(`Remote search failed: ${error.message}`);
      setSearchState("error");
    }
  }

  const repos = facets.repositories || [];
  const branches = facets.branches || [];
  const explorer = useMemo(() => parseExplorer(selected?.raw_source_text, selected?.transcript_text), [selected]);
  const filteredExplorer = explorer.filter(item => {
    if (explorerFilters.role && item.role !== explorerFilters.role) return false;
    if (explorerFilters.type && item.type !== explorerFilters.type) return false;
    if (explorerFilters.text && !item.text.toLowerCase().includes(explorerFilters.text.toLowerCase())) return false;
    if (explorerFilters.focus === "decision" && !item.tags.includes("decision")) return false;
    if (explorerFilters.focus === "tool" && !item.tags.includes("tool")) return false;
    if (explorerFilters.focus === "file" && !item.tags.includes("file")) return false;
    return true;
  });
  const pageItems = filteredExplorer.slice(explorerFilters.page * 50, explorerFilters.page * 50 + 50);

  async function runSearch(e) {
    e.preventDefault();
    if (!query.trim()) return;
    setSearchState("loading");
    try {
      const scopedSession = searchScope === "selected" ? selected?.id : "";
      const matches = await searchEvidence(query, scopedSession);
      setResults(matches);
      setSearchState(matches.length ? "done" : "empty");
      setTab("Search results");
    } catch (error) {
      setNotice(`Search failed: ${error.message}`);
      setSearchState("error");
    }
  }

  async function importCandidate(candidate) {
    try {
      setBusy("Importing Codex session...");
      const res = await importCodexSession({ source_path: candidate.source_path });
      setNotice(res.duplicate ? "Already imported; opening existing session." : "Imported Codex session.");
      const updated = await listCodexSessions(20);
      setCandidates(updated);
      await refresh(res.session_id);
    } catch (error) {
      setNotice(`Import failed: ${error.message}`);
    } finally {
      setBusy("");
    }
  }

  function updateFilters(next) {
    setFilters(next);
  }

  async function clearFilters() {
    const reset = { status: "", repo: "", branch: "", date_from: "", date_to: "" };
    setFilters(reset);
    await refresh(undefined, reset);
  }

  async function todayFilters() {
    const todayOnly = { ...filters, date_from: todayInputValue(), date_to: todayInputValue() };
    setFilters(todayOnly);
    await refresh(undefined, todayOnly);
  }

  const filteredCandidates = candidates.filter(candidate => {
    const hay = [
      candidate.file_name,
      candidate.prompt_preview,
      candidate.repo_path,
      candidate.branch_name,
      candidate.source_path,
      candidate.session_id,
    ].filter(Boolean).join("\n").toLowerCase();
    return !importQuery.trim() || hay.includes(importQuery.toLowerCase());
  });
  const codexSessionRows = useMemo(() => {
    const rows = [];
    const seen = new Set();
    for (const session of sessions) {
      if (!session.memory_source_path && session.status !== "remote-debug") continue;
      const key = session.memory_source_path || session.id;
      if (seen.has(key)) continue;
      seen.add(key);
      rows.push({
        id: session.id,
        key,
        title: sessionTitle(session),
        status: session.status,
        repo: session.repo_name || repoName(session.repo_path) || "",
        branch: session.branch_name || "",
        time: session.start_time || session.created_at,
        summary: session.session_summary || session.transcript_text || "",
        files: extractFiles([session.session_summary, session.transcript_text].filter(Boolean).join("\n")).length,
        commits: extractCommits([session.session_summary, session.transcript_text].filter(Boolean).join("\n")).length,
        imported: true,
        remote: session.status === "remote-debug",
        session,
      });
    }
    for (const candidate of candidates) {
      const key = candidate.source_path || candidate.session_id;
      if (seen.has(key)) continue;
      seen.add(key);
      rows.push({
        id: candidate.session_id,
        key,
        title: sessionTitle(candidate),
        status: candidate.imported ? "closed" : "new",
        repo: repoName(candidate.repo_path) || "",
        branch: candidate.branch_name || "",
        time: candidate.modified_time,
        summary: candidate.prompt_preview || "",
        files: extractFiles(candidate.prompt_preview || "").length,
        commits: extractCommits(candidate.prompt_preview || "").length,
        imported: candidate.imported,
        candidate,
      });
    }
    return rows
      .filter(row => {
        const hay = [row.title, row.summary, row.repo, row.branch, row.id].filter(Boolean).join("\n").toLowerCase();
        return !sessionQuery.trim() || hay.includes(sessionQuery.toLowerCase());
      })
      .filter(row => !filters.status || row.status === filters.status)
      .filter(row => !filters.repo || row.repo === filters.repo)
      .filter(row => !filters.branch || row.branch === filters.branch)
      .filter(row => inDateWindow(row.time, filters.date_from, filters.date_to))
      .sort((a, b) => new Date(b.time || 0) - new Date(a.time || 0));
  }, [sessions, candidates, sessionQuery, filters.status, filters.repo, filters.branch, filters.date_from, filters.date_to]);

  async function openCodexRow(row) {
    setOpeningSessionId(row.id);
    setSelected(row.session || {
      id: row.id,
      feature_title: row.title,
      display_title: row.title,
      repo_name: row.repo,
      branch_name: row.branch,
      status: row.status,
      start_time: row.time,
      created_at: row.time,
      session_summary: row.summary,
    });
    setEvidence(null);
    setTimeline([]);
    setResults([]);
    setTab("Summary");
    requestAnimationFrame(() => document.querySelector(".detail")?.scrollIntoView({ behavior: "smooth", block: "start" }));
    try {
      if (row.session) {
        await openSession(row.id);
        return;
      }
      if (row.candidate?.imported) {
        try {
          await openSession(row.id);
          return;
        } catch {
          // Fall through and let the import endpoint resolve the existing session.
        }
      }
      if (row.candidate) {
        await importCandidate(row.candidate);
      }
    } finally {
      setOpeningSessionId("");
    }
  }

  return (
    <div className="app">
      <header>
        <div className="headerCopy">
          <h1>Local Dev Memory</h1>
          <div className="browseLine">Browse by date, repository, commit id, change text, and file name.</div>
        </div>
        <button className="iconButton" aria-label="Settings" title="Settings" onClick={async () => { setShowDetectedAgents(true); setAgents(await listAgents()); setSettingsOpen(true); }}>
          <span aria-hidden="true">&#9881;</span>
        </button>
      </header>

      {notice && <div className="notice">{notice}</div>}
      {busy && <div className="notice busyNotice">{busy}</div>}

      <section className="queryPanel">
        <div className="eyebrow">QUERY</div>
        <h2>Search local session evidence <span className="infoDot">i</span></h2>
        <p>Local keyword retrieval only. Search summaries, file paths, commit SHAs, transcript snippets, and decision evidence.</p>
        <form className="search" onSubmit={runSearch}>
          <input placeholder={'Examples: "auth_service.py", "token refresh", "commit 1a2b3c4", "refactor auth flow"'} value={query} onChange={e => setQuery(e.target.value)} />
          <select value={searchScope} onChange={e => setSearchScope(e.target.value)} disabled={!selected}>
            <option value="all">All sessions</option>
            <option value="selected">Selected session</option>
          </select>
          <button>Search</button>
        </form>
        <div className="queryChips"><span>auth_service.py</span><span>token refresh</span><span>commit 1a2b3c4</span><small>{searchState === "loading" ? "Searching..." : searchState === "empty" ? "No matches found" : results.length ? `${results.length} matches` : "Local evidence only"}</small></div>
      </section>

      <RemoteDebugPanel
        open={remoteOpen}
        setOpen={setRemoteOpen}
        state={remoteState}
        board={remoteBoard}
        filters={remoteFilters}
        setFilters={setRemoteFilters}
        question={remoteQuestion}
        setQuestion={setRemoteQuestion}
        brief={remoteBrief}
        uploadText={remoteUpload}
        setUploadText={setRemoteUpload}
        onProject={submitRemoteProject}
        onDeveloper={submitRemoteDeveloper}
        onUpload={submitRemoteUpload}
        onDemo={createRemoteDemoMode}
        onBrief={runRemoteBrief}
        onSearchRemote={searchRemoteEvidence}
        onRefresh={refreshRemote}
        openSession={openSession}
      />

      <main>
        <aside>
          <div className="sessionBrowserHead">
            <div>
              <div className="filterTitle">Codex Sessions</div>
              <div className="filterHint">Click a session to open its summary.</div>
            </div>
            <div className="libraryCounts"><span>{codexSessionRows.length} shown</span><span>{facets.counts?.open || 0} open</span></div>
          </div>
          <details className="filters">
            <summary>
              <span>Filter / search sessions</span>
              <small>{sessionQuery || filters.status || filters.repo || filters.branch || filters.date_from || filters.date_to ? "Active" : "Optional"}</small>
            </summary>
            <label>Search sessions<input placeholder="Search title, summary, repo, branch, session id" value={sessionQuery} onChange={e => setSessionQuery(e.target.value)} /></label>
            <label>Status<select value={filters.status} onChange={e => updateFilters({ ...filters, status: e.target.value })}><option value="">All statuses</option><option value="new">New</option>{(facets.statuses || []).map(status => <option key={status}>{status}</option>)}</select></label>
            <label>Repository<select value={filters.repo} onChange={e => updateFilters({ ...filters, repo: e.target.value })}><option value="">All repositories</option>{repos.map(repo => <option key={repo}>{repo}</option>)}</select></label>
            <label>Branch<select value={filters.branch} onChange={e => updateFilters({ ...filters, branch: e.target.value })}><option value="">All branches</option>{branches.map(branch => <option key={branch}>{branch}</option>)}</select></label>
            <label>From date<input type="date" value={filters.date_from} onChange={e => updateFilters({ ...filters, date_from: e.target.value })} /></label>
            <label>To date<input type="date" value={filters.date_to} onChange={e => updateFilters({ ...filters, date_to: e.target.value })} /></label>
            <div className="filterActions">
              <button className={filters.date_from || filters.date_to ? "active" : ""} onClick={() => refresh()}>Apply dates</button>
              <button className={filters.date_from === todayInputValue() && filters.date_to === todayInputValue() ? "active" : ""} onClick={todayFilters}>Today</button>
              <button className={!filters.date_from && !filters.date_to && !sessionQuery ? "active" : ""} onClick={async () => { setSessionQuery(""); await clearFilters(); }}>All dates</button>
            </div>
            <div className="filterHint">{filters.date_from || filters.date_to ? `Showing Codex sessions from ${filters.date_from || "the beginning"} to ${filters.date_to || "latest"}` : "Showing latest Codex sessions across all dates"}</div>
          </details>
          <div className="sessionList">
            {codexSessionRows.map(row => <button className={selected?.id === row.id || openingSessionId === row.id ? "active item sessionRow" : "item sessionRow"} key={row.key} onClick={() => openCodexRow(row)}>
              <div className="rowTop"><strong>{row.title}</strong><span className={`pill ${row.imported ? "open" : ""}`}>{row.remote ? "remote" : row.imported ? "ready" : "new"}</span></div>
              <span className="rowPreview">{sessionSummaryText(row)}</span>
              <div className="rowMeta">
                <small>{formatDateTime(row.time)}</small>
                <span>{row.files} files</span>
                <span>{row.commits} commits</span>
                {openingSessionId === row.id && <span>opening...</span>}
              </div>
            </button>)}
            {!codexSessionRows.length && <OnboardingEmptyState onCreateDemo={createDemo} onOpenSettings={async () => { setShowDetectedAgents(true); setAgents(await listAgents()); setSettingsOpen(true); }} />}
          </div>
        </aside>

        <section className="workspace">
          <section className="importer">
            <div className="sectionHead importToggle">
              <button className="collapseButton" aria-expanded={importsOpen} onClick={() => setImportsOpen(!importsOpen)}>
                <span aria-hidden="true">{importsOpen ? "v" : ">"}</span>
                <span>Codex Import Browser</span>
                <small>{filteredCandidates.length} of {candidates.length} sessions</small>
              </button>
              {importsOpen && <button disabled={!!busy} onClick={async () => {
                try {
                  setBusy("Reindexing local sessions...");
                  await reindexCodexSessions();
                  await refresh();
                } catch (error) {
                  setNotice(`Reindex failed: ${error.message}`);
                } finally {
                  setBusy("");
                }
              }}>Reindex</button>}
            </div>
            {importsOpen && <div className="importPanel">
              <input placeholder="Filter imports by task, repo, branch, path, or session id" value={importQuery} onChange={e => setImportQuery(e.target.value)} />
              <div className="candidateGrid">
                {filteredCandidates.map(c => <div className="candidate" key={c.source_path}>
                  <div className="candidateTitle">
                    <b>{sessionTitle(c)}</b>
                    <span className={`pill ${c.imported ? "open" : ""}`}>{c.imported ? "imported" : "new"}</span>
                  </div>
                  <small>{formatDateTime(c.modified_time)} | {displayPath(c.repo_path) || "unknown repo"} | {c.branch_name || "unknown branch"}</small>
                  <span>{c.prompt_preview || "No prompt preview was found in this Codex session."}</span>
                  <details><summary>Source file</summary><code>{c.file_name}</code><code>{c.source_path}</code></details>
                  <button disabled={!!busy} onClick={() => c.imported ? openSession(c.session_id) : importCandidate(c)}>{c.imported ? "Open session" : "Import session"}</button>
                </div>)}
              </div>
              {!filteredCandidates.length && <EmptyState title="No import candidates" body="Adjust the import filter or add a coding-agent source in Settings." />}
              </div>}
          </section>

          {selected && <section className="detail">
            <div className="selectedHeader">
              <div>
                <h2>{sessionTitle(selected)}</h2>
                <div className="selectedMeta">
                  <span>Evidence quality: {evidence?.quality_score ?? 0}%</span>
                  <span>{evidence?.what_changed?.files?.length || evidence?.files?.length || 0} files</span>
                  <span>{(evidence?.linked_commits?.length || 0) + (evidence?.commit_suggestions?.length || 0)} commit signals</span>
                </div>
              </div>
            </div>

            <details className="sessionTools">
              <summary>
                <span>Session details & tools</span>
                <small>{selected.status} | {evidence?.counts?.commits ?? timeline.filter(item => item.kind === "commit").length} commits | {evidence?.counts?.events ?? timeline.length} timeline items</small>
              </summary>
              <div className="selectedMeta">
                <span>{selected.repo_name || repoName(selected.repo_path) || "unknown repo"}</span>
                <span>{selected.branch_name || "unknown branch"}</span>
                <span>{formatDateTime(selected.start_time || selected.created_at)}</span>
              </div>
              <div className="actionGrid">
                <form className="actionCard" onSubmit={async e => {
                  e.preventDefault();
                  if (!selected) return;
                  try {
                    setBusy("Linking commit...");
                    await linkCommit(selected.id, { commit_sha: commitSha });
                    await openSession(selected.id);
                    setNotice("Commit linked to local session evidence.");
                  } catch (error) {
                    setNotice(`Could not link commit: ${error.message}`);
                  } finally {
                    setBusy("");
                  }
                }}>
                  <label>Link commit SHA<input placeholder="Paste commit SHA" value={commitSha} onChange={e => setCommitSha(e.target.value)} /></label>
                  <button disabled={!selected || !!busy}>Link commit</button>
                </form>
                <div className="actionCard">
                  <label>Transcript path for ending session<input placeholder="Optional rollout-*.jsonl path" disabled /></label>
                  <button disabled={!selected || selected.status === "closed" || !!busy} onClick={async () => {
                    try {
                      setBusy("Ending session...");
                      await endSession(selected.id);
                      await refresh(selected.id);
                    } catch (error) {
                      setNotice(`Could not end session: ${error.message}`);
                    } finally {
                      setBusy("");
                    }
                  }}>End session</button>
                </div>
                <div className="actionCard">
                  <label>Search scope<select value={searchScope} onChange={e => setSearchScope(e.target.value)} disabled={!selected}><option value="all">All sessions</option><option value="selected">Selected session</option></select></label>
                  <button onClick={() => setTab("Search results")}>View search results</button>
                </div>
                <div className="actionCard">
                  <label>Export session</label>
                  <a className="buttonLink" href={exportSessionJsonUrl(selected.id)}>Export JSON</a>
                  <a className="buttonLink" href={exportSessionMarkdownUrl(selected.id)}>Export Markdown</a>
                </div>
                <div className="actionCard dangerCard">
                  <label>Local index controls</label>
                  <button disabled={!selected || !!busy} onClick={removeSelectedSession}>Delete session index</button>
                </div>
                <LocalModePanel
                  diag={diag}
                  healthState={healthState}
                  onCreateDemo={createDemo}
                  onClearAll={clearAllSessions}
                  onReindex={async () => {
                    try {
                      setBusy("Refreshing local index...");
                      const res = await reindexCodexSessions();
                      setNotice(`Local index refreshed: ${res.documents} documents across ${res.reindexed_sessions} sessions.`);
                      await refresh(selected?.id);
                    } catch (error) {
                      setNotice(`Refresh failed: ${error.message}`);
                    } finally {
                      setBusy("");
                    }
                  }}
                />
              </div>
            </details>
            <nav className="tabs">{["Overview", "Summary", "What changed", "Commit detail", "Timeline", "Recent turns", "Transcript", "Explorer", "Search results"].map(t => <button className={tab === t ? "active" : ""} onClick={() => setTab(t)} key={t}>{t}</button>)}</nav>
            {tab === "Overview" && <Overview selected={selected} timeline={timeline} evidence={evidence} />}
            {tab === "Summary" && <SessionSummary selected={selected} evidence={evidence} />}
            {tab === "What changed" && <WhatChanged selected={selected} evidence={evidence} onUseCommit={sha => { setCommitSha(sha); setNotice("Commit SHA loaded in Session details & tools. Open tools and click Link commit."); }} />}
            {tab === "Commit detail" && <CommitDetail timeline={timeline} evidence={evidence} />}
            {tab === "Timeline" && <Timeline items={timeline} />}
            {tab === "Recent turns" && <RecentTurns turns={evidence?.recent_turns} fallback={explorer.slice(-20)} />}
            {tab === "Transcript" && <TranscriptView selected={selected} />}
            {tab === "Search results" && <ResultList results={results} openSession={openSession} />}
            {tab === "Explorer" && <Explorer filters={explorerFilters} setFilters={setExplorerFilters} items={pageItems} total={filteredExplorer.length} />}
          </section>}
        </section>
      </main>

      {settingsOpen && <div className="modal"><div className="modalBody">
        <button className="close" onClick={() => setSettingsOpen(false)}>Close</button>
        <h2>Coding Agent Sources</h2>
        <p className="muted">Choose whether to show coding agents detected on this system. Detected sources are read-only until you add one below.</p>
        <label className="checkRow"><input type="checkbox" checked={showDetectedAgents} onChange={async e => { setShowDetectedAgents(e.target.checked); if (e.target.checked && !agents) setAgents(await listAgents()); }} /> Show detected coding agents from this system</label>
        {showDetectedAgents && <div className="agentGrid">
          {(agents?.detected || []).map(agent => <div className="agentCard" key={agent.source_path}>
            <b>{agent.name}</b>
            <span className={`pill ${agent.exists ? "open" : "closed"}`}>{agent.exists ? "available" : "missing"}</span>
            <code title={agent.source_path}>{displayPath(agent.source_path)}</code>
          </div>)}
        </div>}
        <h3>Configured Sources</h3>
        <div className="agentGrid">
          {(agents?.configured || []).map(agent => <div className="agentCard" key={agent.source_path}>
            <b>{agent.name}</b>
            <span className={`pill ${agent.enabled ? "open" : "closed"}`}>{agent.enabled ? "enabled" : "disabled"}</span>
            <code title={agent.source_path}>{displayPath(agent.source_path)}</code>
          </div>)}
        </div>
        <form onSubmit={async e => { e.preventDefault(); const fd = new FormData(e.currentTarget); await addAgent({ name: fd.get("name"), source_path: fd.get("source_path") }); setAgents(await listAgents()); e.currentTarget.reset(); }}>
          <input name="name" placeholder="Source name" /><input name="source_path" placeholder="Path" /><button>Add</button>
        </form>
      </div></div>}
    </div>
  );
}

function RemoteDebugPanel({ open, setOpen, state, board, filters, setFilters, question, setQuestion, brief, uploadText, setUploadText, onProject, onDeveloper, onUpload, onDemo, onBrief, onSearchRemote, onRefresh, openSession }) {
  const projects = board?.projects || state?.projects || [];
  const developers = board?.developers || state?.developers || [];
  const sessions = board?.sessions || state?.recent_uploads || [];
  const hotspots = board?.hotspots || state?.hotspots || {};
  const stats = board?.stats || {};
  const filteredDevelopers = developers.filter(dev => !filters.project_id || String(dev.project_id) === String(filters.project_id));
  const sample = {
    project_name: projects[0]?.name || "Payments Platform",
    developer_email: "developer@company.com",
    developer_name: "Developer Name",
    tool_name: "Codex",
    external_session_id: "codex-session-001",
    title: "Fix checkout retry issue",
    repo_name: "payments-service",
    branch_name: "bugfix/retry",
    session_summary: "Debugged retry failure and updated validation.",
    transcript_text: "user: Fix retry bug\nassistant: Decision: changed retry logic because duplicate payment attempts were not guarded.",
    issue_count: 1
  };
  return <section className="remotePanel">
    <div className="remoteHead">
      <button className="collapseButton" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span aria-hidden="true">{open ? "v" : ">"}</span>
        <span>Remote Debug Mode</span>
        <small>{state?.remote_session_count || 0} sessions | {state?.developer_count || 0} developers | {state?.project_count || 0} projects</small>
      </button>
      <div className="remoteHeadActions">
        <button className="demoButton" onClick={onDemo}>Demo mode</button>
        <button onClick={() => onRefresh(filters)}>Refresh</button>
      </div>
    </div>
    {open && <div className="remoteBody">
      <div className="remoteStats">
        <span>Projects: {stats.project_count ?? state?.project_count ?? 0}</span>
        <span>Developers: {stats.developer_count ?? state?.developer_count ?? 0}</span>
        <span>Remote sessions: {stats.remote_session_count ?? state?.remote_session_count ?? 0}</span>
        <span>Issues: {stats.issue_count ?? state?.issue_count ?? 0}</span>
        <span>LLM: local brief ready</span>
      </div>

      <div className="remoteDebugBar">
        <select value={filters.project_id} onChange={e => setFilters({ ...filters, project_id: e.target.value, developer_id: "" })}>
          <option value="">All projects</option>
          {projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}
        </select>
        <select value={filters.developer_id} onChange={e => setFilters({ ...filters, developer_id: e.target.value })}>
          <option value="">All developers</option>
          {filteredDevelopers.map(dev => <option key={dev.id} value={dev.id}>{dev.name} ({dev.tool_name || "tool"})</option>)}
        </select>
        <input placeholder="Filter remote sessions by issue, repo, file, developer" value={filters.q} onChange={e => setFilters({ ...filters, q: e.target.value })} />
        <button onClick={() => onRefresh(filters)}>Apply scope</button>
        <button onClick={() => onSearchRemote(filters.q || question)}>Search remote evidence</button>
      </div>

      <div className="remoteOpsGrid">
        <section className="remoteCard aiCard">
          <div className="resultHead"><h3>AI debug brief</h3><span className="pill open">local</span></div>
          <textarea value={question} onChange={e => setQuestion(e.target.value)} />
          <div className="remoteActions">
        <button onClick={onBrief}>Generate brief</button>
            <button onClick={() => onSearchRemote(question)}>Search evidence</button>
          </div>
          {brief && <div className="debugBrief">
            <b>{brief.answer?.summary}</b>
            <span>{brief.llm_status}</span>
            <h4>Likely root causes</h4>
            {(brief.answer?.likely_root_causes || []).map((item, index) => <p key={index}>{item}</p>)}
            <h4>Next actions</h4>
            {(brief.answer?.next_actions || []).map((item, index) => <p key={index}>{item}</p>)}
          </div>}
        </section>

        <section className="remoteCard">
          <h3>Debug hotspots</h3>
          <div className="hotspotList">
            {(hotspots.files || []).map(item => <button key={item.file} onClick={() => onSearchRemote(item.file)}><span>{item.file}</span><b>{item.count}</b></button>)}
            {!(hotspots.files || []).length && <p className="muted">No hotspot files yet.</p>}
          </div>
          <h3>Repositories</h3>
          <div className="hotspotList">
            {(hotspots.repositories || []).map(item => <button key={item.repo} onClick={() => onSearchRemote(item.repo)}><span>{item.repo}</span><b>{item.count}</b></button>)}
            {!(hotspots.repositories || []).length && <p className="muted">No repository hotspots yet.</p>}
          </div>
        </section>
      </div>

      <div className="remoteGrid">
        <section className="remoteCard remoteSpan">
          <h3>Remote sessions in scope</h3>
          <div className="remoteSessionList">
            {sessions.slice(0, 12).map(item => <article key={item.id || item.session_id}>
              <div className="resultHead"><b>{item.session_title || item.external_session_id}</b><span className="pill">{item.issue_count || 0} issues</span></div>
              <small>{item.developer_name || "Unknown developer"} | {item.tool_name || "unknown tool"} | {item.repo_name || "no repo"} | {formatDateTime(item.uploaded_at)}</small>
              <p>{stripTechnicalNoise(item.summary || "")}</p>
              <div className="evidence">
                {(item.files || []).slice(0, 4).map(file => <span key={file}>{file}</span>)}
              </div>
              <div className="remoteActions">
                <button onClick={() => openSession(item.session_id)}>Open session viewer</button>
                <button onClick={() => onSearchRemote(item.session_title || item.external_session_id)}>Find related evidence</button>
              </div>
            </article>)}
            {!sessions.length && <p className="muted">No remote sessions match this scope.</p>}
          </div>
        </section>

        <section className="remoteCard">
          <h3>Developer coverage</h3>
          <div className="developerList">
            {filteredDevelopers.slice(0, 12).map(dev => <button key={dev.id} onClick={() => setFilters({ ...filters, developer_id: String(dev.id) })}>
              <span><b>{dev.name}</b><small>{dev.email} | {dev.tool_name || "unknown tool"}</small></span>
              <em>{dev.session_count} sessions / {dev.issue_count} issues</em>
            </button>)}
            {!filteredDevelopers.length && <p className="muted">No developers in this scope.</p>}
          </div>
        </section>
      </div>

      <div className="remoteGrid">
        <form className="remoteCard" onSubmit={onProject}>
          <h3>Project</h3>
          <input name="name" placeholder="Project name" required />
          <input name="description" placeholder="Debug mode description" />
          <button>Create / update project</button>
        </form>
        <form className="remoteCard" onSubmit={onDeveloper}>
          <h3>Developer</h3>
          <select name="project_id" required><option value="">Select project</option>{projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select>
          <input name="name" placeholder="Developer name" required />
          <input name="email" placeholder="developer@company.com" required />
          <input name="tool_name" placeholder="Codex, Cursor, Claude Code..." />
          <input name="fetch_url" placeholder="Optional session feed URL" />
          <button>Add developer</button>
        </form>
        <form className="remoteCard remoteUpload" onSubmit={onUpload}>
          <h3>Upload remote session JSON</h3>
          <textarea value={uploadText} onChange={e => setUploadText(e.target.value)} placeholder={JSON.stringify(sample, null, 2)} required />
          <div className="remoteActions">
            <button type="button" onClick={() => setUploadText(JSON.stringify(sample, null, 2))}>Use sample</button>
            <button>Upload session</button>
          </div>
        </form>
      </div>
      <div className="remoteGrid">
        {projects.map(project => <article className="remoteCard" key={project.id}>
          <div className="resultHead"><b>{project.name}</b><span className={`pill ${project.debug_mode_enabled ? "open" : "closed"}`}>{project.debug_mode_enabled ? "debug on" : "debug off"}</span></div>
          <p>{project.description || "Remote debug project."}</p>
          <div className="remoteStats compact"><span>{project.developer_count} developers</span><span>{project.session_count} sessions</span><span>{project.issue_count} issues</span></div>
        </article>)}
      </div>
    </div>}
  </section>;
}

function Overview({ selected, timeline, evidence }) {
  const evidenceText = [selected.session_summary, selected.transcript_text, selected.raw_source_text].filter(Boolean).join("\n");
  const files = evidence?.file_changes?.length ? evidence.file_changes : extractFiles(evidenceText);
  const commits = evidence?.commit_refs?.length ? evidence.commit_refs : extractCommits(evidenceText);
  const decisions = evidence?.decision_snippets?.length ? evidence.decision_snippets : extractDecisions(evidenceText);
  const facts = [
    ["Status", selected.status],
    ["Started", formatDateTime(selected.start_time)],
    ["Ended", formatDateTime(selected.end_time)],
    ["Repository", displayPath(selected.repo_path)],
    ["Branch", shortText(selected.branch_name)],
    ["Memory ref", displayPath(selected.memory_ref)],
  ];
  return <div className="overviewGrid">
    {facts.map(([label, value]) => <div className="fact" key={label}><span>{label}</span><b>{value}</b></div>)}
    {selected.memory_error && <div className="fact wide"><span>Memory error</span><b>{selected.memory_error}</b></div>}
    <div className="fact wide"><span>Timeline items</span><b>{evidence?.counts?.events ?? timeline.length}</b></div>
    <section className="evidencePanel">
      <h3>Session Evidence</h3>
      <div className="evidenceColumns">
        <div><span>What you tried to change</span><p>{evidence?.what_tried_to_change || selected.feature_title || "No user intention found."}</p><span>Decision snippets</span>{decisions.length ? decisions.map((item, index) => <p key={index}>{item}</p>) : <p>No decision/change summary found yet.</p>}</div>
        <div><span>Files</span>{files.length ? files.map(file => <code key={file}>{file}</code>) : <p>No file references found.</p>}</div>
        <div><span>Commits</span>{commits.length ? commits.map(commit => <code key={commit}>{commit}</code>) : <p>No commit references found.</p>}</div>
      </div>
    </section>
  </div>;
}

function SessionSummary({ selected, evidence }) {
  const context = evidence?.session_context || {};
  const files = evidence?.files?.length ? evidence.files : evidence?.file_changes || [];
  const intention = context.user_intention || evidence?.intention || selected.start_note || sessionTitle(selected);
  const featureSummary = stripTechnicalNoise(context.activity_summary || evidence?.summary || selected.session_summary || "");
  const startNote = stripTechnicalNoise(selected.start_note || intention);
  const decisions = evidence?.decision_snippets || [];
  const commands = evidence?.commands_run || [];
  const tests = evidence?.tests_run || [];
  const errors = evidence?.errors || [];
  const openQuestions = evidence?.open_questions || [];
  const keyPrompt = decisions[0] || intention;
  return <section className="summaryBoard">
    <div className="summaryMain">
      <article className="summaryCard">
        <h3>Session summary</h3>
        <div className="summaryStack">
          <p className="summaryStrip stripGreen">{featureSummary || `Feature session for ${sessionTitle(selected)}.`}</p>
          <p className="summaryStrip stripBlue">Start note: {startNote || "No start note captured."}</p>
          <p className="summaryStrip stripYellow">Key prompts: {stripTechnicalNoise(keyPrompt) || "No key prompt captured."}</p>
        </div>
        <div className="summaryDates">
          <span>Started: {formatDateTime(selected.start_time || selected.created_at)}</span>
          <span>Ended: {formatDateTime(selected.end_time)}</span>
        </div>
        <details className="summaryDiagnostics">
          <summary>View diagnostics</summary>
          <p>{selected.memory_error || "No diagnostics reported for this session."}</p>
        </details>
        {selected.memory_error && <div className="diagnosticWarn">{selected.memory_error}</div>}
      </article>

      <article className="summaryCard decisionCard">
        <h3>Decision snippets</h3>
        {decisions.length
          ? decisions.map((item, index) => <p key={index}>{item}</p>)
          : <p className="muted">No decision snippets indexed yet.</p>}
      </article>

      <article className="summaryCard intelligenceCard">
        <h3>Session intelligence</h3>
        <div className="intelGrid">
          <div><span>Outcome</span><p>{evidence?.outcome || "Outcome not detected yet."}</p></div>
          <div><span>Commands</span>{commands.length ? commands.slice(0, 5).map(item => <code key={item}>{item}</code>) : <p>No commands detected.</p>}</div>
          <div><span>Tests / build signals</span>{tests.length ? tests.slice(0, 5).map(item => <p key={item}>{item}</p>) : <p>No test or build signal detected.</p>}</div>
          <div><span>Errors / warnings</span>{errors.length ? errors.slice(0, 5).map(item => <p key={item}>{item}</p>) : <p>No error evidence detected.</p>}</div>
          <div><span>Open questions</span>{openQuestions.length ? openQuestions.slice(0, 5).map(item => <p key={item}>{item}</p>) : <p>No open follow-up detected.</p>}</div>
        </div>
      </article>
    </div>

    <article className="summaryCard summaryContextCard">
      <h3>Session context</h3>
      <div className="contextLines">
        <div><span className="tag tagBlue">What you tried to change</span><p>{intention}</p></div>
        <div><span className="tag tagPink">Intention</span><p>{context.user_intention || evidence?.what_tried_to_change || intention}</p></div>
        <div><span className="tag tagYellow">File changes</span><p>{files.length ? files.slice(0, 8).join(", ") : "No file changes indexed yet."}</p></div>
      </div>
    </article>
  </section>;
}

function QualityMeter({ score = 0, signals = {} }) {
  const items = Object.entries(signals);
  return <div className="qualityBox">
    <div className="qualityHead"><b>Session quality</b><span>{score}%</span></div>
    <div className="qualityTrack"><div style={{ width: `${Math.max(0, Math.min(100, score))}%` }} /></div>
    {!!items.length && <div className="qualitySignals">
      {items.map(([key, present]) => <span className={present ? "on" : ""} key={key}>{key.replace("has_", "").replace(/_/g, " ")}</span>)}
    </div>}
  </div>;
}

function WhatChanged({ selected, evidence, onUseCommit }) {
  const changed = evidence?.what_changed || {};
  const files = changed.files || evidence?.files || evidence?.file_changes || [];
  const linked = changed.linked_commits || evidence?.linked_commits || [];
  const suggested = changed.suggested_commits || evidence?.commit_suggestions || [];
  const decisions = changed.decisions || evidence?.decision_snippets || [];
  const commands = changed.commands || evidence?.commands_run || [];
  const tests = changed.tests || evidence?.tests_run || [];
  const errors = changed.errors || evidence?.errors || [];
  return <section className="whatChanged">
    <div className="changeHero">
      <div>
        <span className="eyebrow">WHAT CHANGED</span>
        <h3>{changed.title || sessionTitle(selected)}</h3>
        <p>{stripTechnicalNoise(changed.goal || evidence?.user_goal || selected.session_summary || "No user goal detected for this session.")}</p>
      </div>
      <QualityMeter score={evidence?.quality_score || 0} signals={evidence?.quality_signals || {}} />
    </div>

    <div className="whatChangedGrid">
      <article className="summaryCard">
        <h3>Outcome</h3>
        <p>{changed.outcome || evidence?.outcome || "Outcome not detected from local transcript evidence."}</p>
      </article>
      <article className="summaryCard">
        <h3>Files touched or discussed</h3>
        {files.length ? files.slice(0, 12).map(file => <code key={file}>{file}</code>) : <p className="muted">No file evidence indexed yet.</p>}
      </article>
      <article className="summaryCard">
        <h3>Why it changed</h3>
        {decisions.length ? decisions.slice(0, 5).map((item, index) => <p key={index}>{item}</p>) : <p className="muted">No decision evidence indexed yet.</p>}
      </article>
      <article className="summaryCard">
        <h3>Commands and validation</h3>
        {commands.length ? commands.slice(0, 5).map(item => <code key={item}>{item}</code>) : <p className="muted">No commands detected.</p>}
        {tests.length ? tests.slice(0, 5).map(item => <p key={item}>{item}</p>) : <p className="muted">No test or build signal detected.</p>}
        {errors.length ? <div className="diagnosticWarn">{errors.slice(0, 3).join(" ")}</div> : null}
      </article>
      <article className="summaryCard">
        <h3>Linked commits</h3>
        {linked.length ? linked.map(commit => <div className="commitSuggestion" key={commit.sha}><code>{commit.sha}</code><b>{commit.message || "No commit message"}</b><small>{formatDateTime(commit.time)}</small></div>) : <p className="muted">No commit is linked to this session yet.</p>}
      </article>
      <article className="summaryCard">
        <h3>Suggested commits</h3>
        {suggested.length ? suggested.map(commit => <div className="commitSuggestion" key={commit.sha}>
          <code>{commit.sha}</code>
          <b>{commit.message || "No commit message"}</b>
          <small>{formatDateTime(commit.time)} | {(commit.files || []).slice(0, 3).join(", ")}</small>
          <button onClick={() => onUseCommit(commit.sha)}>Use this SHA</button>
        </div>) : <p className="muted">{evidence?.commit_suggestion_error ? "Could not inspect local git commits for this repository." : "No nearby local commits found for the session window."}</p>}
      </article>
    </div>
  </section>;
}

function CommitDetail({ timeline, evidence }) {
  const linked = evidence?.linked_commits || [];
  const commits = linked.length ? linked.map(commit => ({ kind: "commit", sha: commit.sha, message: commit.message, time: commit.time, diff_summary: commit.diff_summary, files: commit.files || [] })) : timeline.filter(item => item.kind === "commit");
  if (!commits.length) return <EmptyState title="No linked commits" body="Link a commit SHA to attach commit message, author time, and changed evidence to this session." />;
  return <div className="results">{commits.map(commit => <article className="entry" key={commit.sha}>
    <div className="resultHead"><b>{commit.sha}</b><span className="pill">commit</span></div>
    <small>{formatDateTime(commit.time)}</small>
    <p>{commit.message || "No commit message"}</p>
    {commit.diff_summary && <pre>{commit.diff_summary}</pre>}
    {!!commit.files?.length && <div className="evidence">{commit.files.map(file => <span key={file}>{file}</span>)}</div>}
  </article>)}</div>;
}

function Timeline({ items }) {
  if (!items.length) return <EmptyState title="No timeline yet" body="Imported events and linked commits will appear here in chronological order." />;
  return <div className="results">{items.map((item, index) => <article className="entry" key={`${item.kind}-${index}`}>
    <div className="resultHead"><b>{item.type || item.kind}</b><span className="pill">{item.kind}</span></div>
    <small>{formatDateTime(item.time)}</small>
    {item.message && <p>{item.message}</p>}
    {item.sha && <code>{item.sha}</code>}
    {item.payload && <details><summary>Raw payload</summary><pre>{item.payload}</pre></details>}
  </article>)}</div>;
}

function RecentTurns({ turns, fallback }) {
  const items = turns?.length ? turns : (fallback || []).map(item => ({ role: item.role || item.type, text: stripTechnicalNoise(item.text || "") })).filter(item => item.text);
  if (!items.length) return <EmptyState title="No recent turns" body="Imported conversation turns will appear here after the session is indexed." />;
  return <div className="results">{items.map((item, index) => <article className="entry turnEntry" key={index}>
    <div className="resultHead"><b>{item.role || "turn"}</b><span className="pill">turn</span></div>
    <p>{item.text}</p>
  </article>)}</div>;
}

function TranscriptView({ selected }) {
  const sessionText = stripTechnicalNoise(selected.transcript_text || selected.session_summary || "");
  return <section className="tabPanel transcriptPanel">
    <h3>Transcript</h3>
    <p className="muted">Conversation-style rendering with full raw transcript preserved below.</p>
    <details>
      <summary>View session text</summary>
      <pre>{sessionText || "No cleaned session text is available."}</pre>
    </details>
    <details>
      <summary>View full raw transcript</summary>
      <pre>{selected.raw_source_text || selected.transcript_text || "No raw transcript text"}</pre>
    </details>
  </section>;
}

function ResultList({ results, openSession }) {
  if (!results.length) return <EmptyState title="No search results" body="Search by repository, commit id, change text, or file name." />;
  return <div className="results">{results.map((r, i) => <article className="entry" key={i}>
    <div className="resultHead"><b>{r.title}</b><span className="pill">{r.result_type}</span></div>
    <small>{r.session_title || r.session_id} | {r.repo_name || "no repo"} | {r.branch_name || "no branch"} | score {r.score}</small>
    <p>{r.body_text}</p>
    {r.evidence_summary && <div className="evidenceSummary">
      <b>{r.evidence_summary.likely_reason}</b>
      <p>{r.evidence_summary.supporting_evidence}</p>
    </div>}
    {r.evidence_summary && /(decision|summary|file)/i.test(r.result_type || "") && <div className="whyAnswer">
      <span>Why this changed</span>
      <b>{r.evidence_summary.likely_reason || "Reason evidence found in this session"}</b>
      <p>{r.evidence_summary.supporting_evidence || r.body_text}</p>
    </div>}
    <div className="evidence">
      <span>{r.commit_sha ? `Commit ${r.commit_sha}` : "No commit linked"}</span>
      <span>{r.file_path || "No file path linked"}</span>
    </div>
    <button onClick={() => openSession(r.session_id)}>Open session</button>
  </article>)}</div>;
}

function EmptyState({ title, body }) {
  return <div className="emptyState"><b>{title}</b><span>{body}</span></div>;
}

function OnboardingEmptyState({ onCreateDemo, onOpenSettings }) {
  return <div className="emptyState onboardingState">
    <b>No Codex sessions found</b>
    <span>Add or confirm your local Codex source, then refresh the index. You can also create a demo session to explore the product safely.</span>
    <div className="emptyActions">
      <button onClick={onCreateDemo}>Create demo session</button>
      <button onClick={onOpenSettings}>Open settings</button>
    </div>
  </div>;
}

function LocalModePanel({ diag, healthState, onReindex, onCreateDemo, onClearAll }) {
  const roots = diag?.codex_roots || [];
  const availableRoots = roots.filter(root => root.exists);
  return <details className="actionCard localModePanel">
    <summary>
      <span>Local controls</span>
      <small>{diag?.session_count ?? 0} sessions | API {healthState?.status || (healthState?.error ? "offline" : "checking")}</small>
    </summary>
    <div className="localModeBody">
      <div>
        <div className="eyebrow">LOCAL MODE</div>
        <h2>Private local evidence index</h2>
        <p>{diag?.local_mode?.privacy || "Sessions, transcripts, commit metadata, and exports stay on this machine."}</p>
      </div>
      <div className="localStats">
        <span>API: {healthState?.status || (healthState?.error ? "offline" : "checking")}</span>
        <span>Sessions: {diag?.session_count ?? 0}</span>
        <span>Search docs: {diag?.search_doc_count ?? 0}</span>
        <span>Files: {diag?.file_ref_count ?? 0}</span>
        <span>Sources: {availableRoots.length}/{roots.length}</span>
        <span>Missing source files: {diag?.missing_source_count ?? 0}</span>
      </div>
      <div className="localActions">
        <button onClick={onReindex}>Refresh local index</button>
        <button onClick={onCreateDemo}>Create demo session</button>
        <button className="subtleDanger" onClick={onClearAll}>Clear local index</button>
        <details>
          <summary>Local paths</summary>
          <code title={diag?.data_root || ""}>Data: {displayPath(diag?.data_root)}</code>
          <code title={diag?.database_url || ""}>Database: {displayPath(diag?.database_url)}</code>
          {roots.map(root => <code title={root.path} key={root.path}>{root.exists ? "OK" : "Missing"}: {displayPath(root.path)} ({root.rollout_files || 0} rollout files)</code>)}
        </details>
      </div>
    </div>
  </details>;
}

function Explorer({ filters, setFilters, items, total }) {
  return <div>
    <div className="explorerControls">
      <input placeholder="Filter text" value={filters.text} onChange={e => setFilters({ ...filters, text: e.target.value, page: 0 })} />
      <select value={filters.role} onChange={e => setFilters({ ...filters, role: e.target.value, page: 0 })}><option value="">Any role</option><option>user</option><option>assistant</option><option>system</option><option>tool</option></select>
      <select value={filters.type} onChange={e => setFilters({ ...filters, type: e.target.value, page: 0 })}><option value="">Any type</option><option>session_meta</option><option>turn_context</option><option>event_msg</option><option>response_item</option><option>raw</option></select>
      <select value={filters.focus} onChange={e => setFilters({ ...filters, focus: e.target.value, page: 0 })}><option value="all">All content</option><option value="decision">Decision evidence</option><option value="tool">System/tool events</option><option value="file">File-related entries</option></select>
      <label><input type="checkbox" checked={filters.raw} onChange={e => setFilters({ ...filters, raw: e.target.checked })} /> Raw</label>
    </div>
    <small>{total} entries</small>
    {items.map(item => <article className="entry" key={item.index}><b>{item.role || item.type}</b><small>{item.timestamp} | {item.tags.join(", ")}</small><pre>{filters.raw ? item.text : item.text.slice(0, 1800)}</pre></article>)}
    <div className="pager"><button disabled={filters.page === 0} onClick={() => setFilters({ ...filters, page: filters.page - 1 })}>Prev</button><span>Page {filters.page + 1}</span><button disabled={(filters.page + 1) * 50 >= total} onClick={() => setFilters({ ...filters, page: filters.page + 1 })}>Next</button></div>
  </div>;
}

export default App;
