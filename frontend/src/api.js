const API = "http://127.0.0.1:8176";

async function request(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options
  });
  if (!res.ok) throw new Error(await res.text());
  const type = res.headers.get("content-type") || "";
  return type.includes("application/json") ? res.json() : res.text();
}

export const health = () => request("/health");
export const diagnostics = () => request("/api/v1/sessions/diagnostics");
export const getFacets = () => request("/api/v1/sessions/facets");
export const listSessions = (params = {}) => request(`/api/v1/sessions?${new URLSearchParams(Object.entries(params).filter(([, v]) => v))}`);
export const getSession = (id) => request(`/api/v1/sessions/${id}`);
export const getSessionView = (id) => request(`/api/v1/sessions/${id}/view`);
export const getSessionEvidence = (id) => request(`/api/v1/sessions/${id}/evidence`);
export const getTimeline = (id) => request(`/api/v1/sessions/${id}/timeline`);
export const startSession = (payload) => request("/api/v1/sessions/start", { method: "POST", body: JSON.stringify(payload) });
export const createDemoSession = () => request("/api/v1/sessions/demo", { method: "POST" });
export const endSession = (id) => request(`/api/v1/sessions/${id}/end`, { method: "POST" });
export const deleteSession = (id) => request(`/api/v1/sessions/${id}`, { method: "DELETE" });
export const clearSessionIndex = () => request("/api/v1/sessions", { method: "DELETE" });
export const linkCommit = (id, payload) => request(`/api/v1/sessions/${id}/link-commit`, { method: "POST", body: JSON.stringify(payload) });
export const searchEvidence = (q, sessionId) => {
  const params = new URLSearchParams({ q });
  if (sessionId) params.set("session_id", sessionId);
  return request(`/api/v1/search?${params}`);
};
export const listAgents = () => request("/api/v1/agents");
export const addAgent = (payload) => request("/api/v1/agents", { method: "POST", body: JSON.stringify(payload) });
export const listCodexSessions = (limit = 20) => request(`/api/v1/imports/codex-sessions?limit=${limit}`);
export const importCodexSession = (payload) => request("/api/v1/imports/codex-sessions", { method: "POST", body: JSON.stringify(payload) });
export const reindexCodexSessions = () => request("/api/v1/imports/codex-sessions/reindex", { method: "POST" });
export const remoteOverview = () => request("/api/v1/remote/overview");
export const remoteDebugBoard = (params = {}) => request(`/api/v1/remote/debug-board?${new URLSearchParams(Object.entries(params).filter(([, v]) => v))}`);
export const remoteDebugBrief = (payload) => request("/api/v1/remote/debug-brief", { method: "POST", body: JSON.stringify(payload) });
export const createRemoteDemo = () => request("/api/v1/remote/demo", { method: "POST" });
export const createRemoteProject = (payload) => request("/api/v1/remote/projects", { method: "POST", body: JSON.stringify(payload) });
export const addRemoteDeveloper = (projectId, payload) => request(`/api/v1/remote/projects/${projectId}/developers`, { method: "POST", body: JSON.stringify(payload) });
export const uploadRemoteSession = (payload) => request("/api/v1/remote/sessions/upload", { method: "POST", body: JSON.stringify(payload) });
export const fetchRemoteSessions = (payload) => request("/api/v1/remote/fetch", { method: "POST", body: JSON.stringify(payload) });
export const exportAllUrl = `${API}/api/v1/export/sessions.jsonl`;
export const exportSessionJsonUrl = (id) => `${API}/api/v1/sessions/${id}/export.json`;
export const exportSessionMarkdownUrl = (id) => `${API}/api/v1/sessions/${id}/export.md`;
