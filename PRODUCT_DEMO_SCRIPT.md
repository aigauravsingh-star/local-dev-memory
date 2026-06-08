# Local Dev Memory - Product Demo Script

## 1. Opening Pitch

Hello everyone, today I am presenting **Local Dev Memory**.

Local Dev Memory is a private memory system for developers who use AI coding assistants like Codex, GitHub Copilot, Claude Code, Cursor, Perplexity, and similar tools.

The main problem we are solving is this:

Developers now use AI coding assistants every day while fixing bugs, building features, and creating pull requests. But the knowledge created during those conversations is usually lost.

A developer may work on many pull requests over a few months. Later, when they need to understand why a change was made, what approach was taken, or what reasoning led to a specific implementation, that information is difficult to find.

Most tools only show recent sessions. Older conversations become hard to reach unless the developer manually saved them.

So valuable engineering knowledge disappears.

Local Dev Memory solves this by reading local coding-agent session logs and creating a searchable knowledge base.

Now developers can search old conversations by keyword, file name, date, repository, commit id, or change text.

When a bug appears later, we can answer:

- What exactly changed?
- Why was it changed?
- Which files were touched?
- Which developer or AI agent session caused this?
- Was the change tested?
- Can we debug this from the original engineering evidence?

In simple words:

**Git tracks code. Local Dev Memory tracks engineering knowledge.**

## 2. Product Positioning

This product has two modes.

The first is **Local Mode**.

Local Mode is for an individual developer. It reads local Codex sessions, indexes them privately, and lets the developer search, inspect, and export their own engineering history.

The second is **Team Debug Mode**.

Team Debug Mode is for teams. Imagine a project with ten developers. Each developer is using Codex or another coding agent. Their sessions are kept in one shared debug memory. Like local mode, the team can search, inspect, open, and debug sessions, but now across multiple developers.

If a production issue happens, the team can search the collective memory and find relevant conversations, files, commits, decisions, and original implementation intent.

## 3. Demo Navigation Script

Use this section while recording the video. Follow the steps in order.

### Step 1 - Open the App

Open the browser and go to:

`http://localhost:8076`

Say:

This is the Local Dev Memory dashboard. At the top, I can search across local engineering evidence by date, repository, commit id, change text, and file name.

### Step 2 - Explain Search

Point to the search panel at the top.

Say:

This search is local evidence search. It searches summaries, transcript snippets, file paths, commit IDs, and decision evidence. For example, I can search for a file name like `retry_policy.py`, a commit id, or a phrase such as `token refresh`.

Do not search yet unless you want to show it later.

### Step 3 - Show Codex Sessions

Look at the left sidebar called **Codex Sessions**.

Say:

On the left side, we have Codex Sessions. These are imported or discovered developer sessions. Each row represents a coding-agent session. I can filter by date, status, repository, branch, or search text.

Click one session from the left.

Say:

When I select a session, the right side opens the session viewer. The UI loads quickly and shows a clean summary first.

### Step 4 - Explain Summary Tab

Stay on the **Summary** tab.

Say:

The Summary tab explains the session in a human-readable way. It shows what the developer or agent was trying to do, the starting note, key prompts, decisions, and the session context.

This is useful because we do not have to read a full raw transcript just to understand the engineering intent.

### Step 5 - Explain What Changed Tab

Click **What changed**.

Say:

The What Changed tab is one of the most important parts of the product. It answers the debugging questions directly.

Here we can see:

- the goal of the session,
- the outcome,
- files touched or discussed,
- why the change happened,
- commands and validation signals,
- linked commits,
- and suggested commits.

This helps a reviewer or debugging engineer understand not only what changed, but also why it changed.

### Step 6 - Explain Commit Detail, Timeline, Transcript

Click **Commit detail**.

Say:

Commit detail connects the session to Git evidence. When a commit is linked, the app can show commit message, changed files, author time, and diff summary.

Click **Timeline**.

Say:

Timeline shows chronological events and commits. This is useful when we want to reconstruct the order of work.

Click **Transcript**.

Say:

Transcript keeps the original conversation evidence available. The app gives a cleaned view, but the raw transcript is also preserved for audit or deeper debugging.

### Step 7 - Explain Explorer

Click **Explorer**.

Say:

Explorer is for deeper investigation. It lets us inspect raw session entries, filter by role, type, text, decision evidence, tool events, or file-related entries.

This is helpful when a senior engineer or QA person wants to validate exactly what happened inside the coding-agent session.

### Step 8 - Show Search Results

Go back to the top search box.

Search for a known file or phrase, for example:

`retry_policy.py`

Click **Search**.

Say:

Search results show matching evidence across sessions. The result also includes a "Why this changed" explanation when decision evidence is available.

This is powerful because instead of searching only code, we are searching engineering memory.

### Step 9 - Open Team Debug Mode

Scroll or look near the top section called **Remote Debug Mode** in the UI. In the demo speech, explain this as **Team Debug Mode**.

Expand it if it is collapsed.

Say:

Now I will show Team Debug Mode. This is the shared debugging workspace for multiple developers.

In this mode, a project can have multiple developers using different coding agents. Their sessions are kept in one central private debug index. Like local mode, we can search, inspect, open, and debug these sessions, but now at team level.

### Step 10 - Demo Mode

Click **Demo mode**.

Say:

For demonstration, I am loading dummy team data. This creates one project, ten developers, and several remote debug sessions with issue signals.

Wait for the UI to refresh.

Say:

Now we can see project count, developer count, remote session count, and issue count.

### Step 11 - Explain Team Debug Filters

Show the project/developer/filter row.

Say:

Here I can filter the team debug board by project, developer, or issue text. This helps a lead engineer or engineering manager narrow down the investigation.

For example, if a production issue is related to checkout retry, I can search for `retry` or filter by the developer who worked on checkout.

### Step 12 - Explain AI Debug Brief

Point to **AI debug brief**.

Say:

This section gives an AI-style debug brief. Today it is generated locally from indexed evidence, so private data does not need to leave the machine.

The same evidence payload can later be connected to a private or hosted LLM.

Click **Generate brief**.

Say:

The debug brief summarizes the issue scope, likely root causes, hotspot files, highest-risk sessions, and recommended next actions.

This helps a team decide where to start debugging.

### Step 13 - Explain Hotspots

Point to **Debug hotspots**.

Say:

Debug hotspots show files and repositories that appear repeatedly across team sessions. If the same file appears across multiple issue sessions, that is a strong signal for investigation.

Click one hotspot file if available.

Say:

Clicking a hotspot can search related evidence, so the team can quickly find all sessions connected to that file.

### Step 14 - Explain Team Sessions in Scope

Point to **Remote sessions in scope** in the UI. In the speech, call these team sessions.

Say:

This section lists team sessions matching the current project, developer, or search scope. Each session shows developer name, tool name, repository, issue count, files, and summary.

Click **Open session viewer** on one remote session.

Say:

Team sessions open in the same normal session viewer. That means Team Debug Mode gets the same capabilities as Local Mode: Summary, What Changed, Timeline, Transcript, Explorer, Search, and Export.

### Step 15 - Explain Developer Coverage

Point to **Developer coverage**.

Say:

Developer coverage shows which developers have uploaded sessions, which tool they used, how many sessions they have, and how many issue signals are connected to them.

This helps a lead understand whether debugging evidence is complete across the team.

### Step 16 - Explain Upload / Future Fetch

Point to the project, developer, and upload forms.

Say:

Team sessions can be uploaded as JSON. In the future, this can also be automated through a fetch endpoint or agent integration.

This means each developer's coding-agent session can become part of the team debug memory automatically.

## 4. Closing Pitch

To summarize:

Local Dev Memory gives developers and teams a private memory layer over AI-assisted engineering work.

For an individual developer, it is a local session browser and search system.

For a team, Team Debug Mode becomes a shared debugging workspace where developer sessions, files, commits, decisions, and issue signals are connected.

The main value is faster debugging, better traceability, better AI-code review, and preserved engineering context.

Instead of asking, "Who changed this and why?", the team can open Local Dev Memory and see the actual evidence.

That is the vision of Local Dev Memory: a searchable memory layer for software development.

Again, the simple message is:

**Git tracks code. Local Dev Memory tracks engineering knowledge.**

## 5. Merits

- Private local-first design.
- Works with coding-agent sessions.
- Helps explain what changed and why.
- Supports local and team debug workflows.
- Makes sessions searchable by file, commit, repo, date, and decision text.
- Preserves transcript and raw evidence.
- Provides AI-style debug briefs without requiring external LLMs.
- Team Debug Mode supports project, developer, session, issue, and hotspot investigation.
- Useful for debugging, audit, code review, and onboarding.

## 6. Demerits / Current Limitations

- Team session upload is still manual unless integrated with developer tools.
- LLM mode is currently local evidence-based, not connected to a hosted model yet.
- Git commit linking still needs stronger automation for remote repositories.
- The UI is functional but can be further refined for large enterprise teams.
- Authentication, RBAC, and multi-tenant controls are not fully implemented yet.
- Large-scale indexing and background jobs should be added before production SaaS use.
- Real-time team sync is not yet implemented.

## 7. Future Roadmap

- Add private LLM connector for debug briefs.
- Add automatic session upload agent.
- Add GitHub/GitLab integration.
- Add developer authentication and project roles.
- Add background indexing workers.
- Add team dashboards and issue tracker integration.
- Add Slack/Teams incident debug assistant.
- Add production deployment mode.
