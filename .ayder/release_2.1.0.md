# ayder-cli 2.1.0

**Release date:** 2026-06-19
**Previous release:** 2.0.0

## Highlights

This release re-architects how background agents deliver their results
(push → pull), adds a complete **multi-agent software-delivery harness**
behind a new `--agent` startup mode, and improves the TUI (serial turn
handling, live context gauge, scrollable agents panel).

---

## Added

### Multi-agent SDLC harness (`--agent`)
- **`--agent` startup flag** — launches an ORCHESTRATOR session that injects the
  new `AGENTIC` system prompt, so the main LLM *coordinates* a 9-role pipeline
  (clarify → spec → spec-review → plan → plan-review → build → QA → code-review →
  acceptance-gate) by delegating to configured agents instead of writing code
  itself. Implies `write`+`execute`+`http` permissions (agents run unattended).
- **`docs/config.toml.example`** — a ready-to-use 9-role harness configuration
  backed by Ollama Cloud models, with model-per-role rationale (reasoning models
  for planning/review/gating, coding models for build/test) and a documented
  budget alternative.
- **`docs/README_AGENT_WORKFLOW.md`** + an installed **`agent-workflow` skill**
  (`/skill agent-workflow`) — the orchestration playbook: git-branch isolation
  per task (optional worktrees), gate-driven merges, and materialising the
  approved plan as `.ayder/tasks/` files (mirrors `/plan`) so progress is visible
  via `/tasks` (pending / in_progress / done).

### Agent pull-delivery tools
- **`agent_status()`** — snapshot of every run (working / done / error) without
  result bodies.
- **`read_agent_result(run_id, wait=, timeout_s=)`** — drain a finished run, with
  an optional blocking wait for a straggler instead of busy-polling.
- **`call_agent`** now returns a run id immediately (no join barrier) — the main
  LLM polls and collects on its own schedule.
- **Durable agent notes** — every run's final deliverable is saved to
  `.ayder/notes/` (collision-proof, YAML-safe) with a `note_path` for retrieval
  after it scrolls out of context.

---

## Changed

### Agent result delivery: push → pull (core re-architecture)
- Replaced the out-of-band **push** model (agent summaries injected into the
  conversation via a batch join barrier that woke the idle LLM) with a **pull**
  model: results never self-inject; the LLM collects them via `agent_status` /
  `read_agent_result`. A 1-second timer plus completion events nudge **once** if a
  turn ends with results still unread.
- **Parallel dispatch, no join barrier** — many agents run concurrently and are
  collected individually as they finish.
- **Single event-loop ownership** of all registry state (worker threads marshal
  through the loop); **generation markers** invalidate stale results across
  `/clear` and compaction.

### TUI
- **Serial turn consumer** — one app-owned turn queue replaces overlapping
  `exclusive=True` workers; `request_turn` defers state-mutating commands until
  the turn is quiescent; **Ctrl+C cancels the active turn only** (the queue is
  preserved).
- **Live context gauge** — the status bar now shows the main LLM's current
  context-window fill (`ctx: used/window (%)`) instead of a cumulative,
  ever-growing token counter. (Agent token usage is excluded; it appears in DEBUG
  logs only.)
- **Scrollable agents panel** (Ctrl+G) — PageUp/PageDown, Home/End, and
  Ctrl+PageUp/PageDown now scroll the panel when it is open.
- `/permission` and `/verbose` apply **immediately** (no longer deferred behind a
  turn).

### Prompts
- New **`AGENTIC`** system-prompt tier (orchestrator role).
- Agent system prompt carries a **final-message deliverable directive**; the
  capability prompt documents the pull contract (`agent_status` /
  `read_agent_result`).

---

## Fixed
- **Completed agents show a green ✓** in the agents panel — previously a red ✗,
  because successful runs report status `done`, which the panel matched only as
  `completed`.
- Added **DEBUG-level logging** across the agent lifecycle (dispatch / done /
  drained / nudge / generation).
- Enforced the provider **`DriverCapability` sdk/extra invariant** (mypy fix).
- Multi-line **paste** into the input preserves surrounding text.

---

## Notes
- **Ollama Cloud auth:** route `:cloud` models through the local daemon
  (`base_url = "http://localhost:11434"`, authenticated once with `ollama
  signin`) — no `OLLAMA_API_KEY` needed. Alternatively target `https://ollama.com`
  directly with `OLLAMA_API_KEY` exported (the `api_key` config field is inert on
  the native driver). The example config defaults to the daemon path.
- The version is sourced from `pyproject.toml`; a reinstall
  (`uv pip install -e .`) refreshes the value reported by `--version`.
