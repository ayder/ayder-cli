# Agent-Result Pull Delivery — Design Spec

**Date:** 2026-06-18
**Status:** Approved (brainstorming) — pending spec review
**Supersedes:** `docs/superpowers/plans/2026-06-17-agent-result-push-delivery.md` (rev. 5 — the serial `TurnEngine` / push design)
**Consumes:** `docs/superpowers/specs/2026-06-18-agent-notes-design.md` (auto-written deliverable notes — kept; the injection-specific parts of it are superseded, see §9)

---

## 1. Why this replaces the push design

The push-delivery plan (rev. 5) grew to ~1800 lines across 9 tasks — a serial `TurnEngine`, a `WakeDebouncer`, `cycle_id` invalidation, a three-mode command-transition API — to deliver one thing: agent results arriving one at a time instead of in a batch.

Two facts collapse all of that:

1. **The current code already pushes.** `call_agent` is already fire-and-forget (`tool.py:81`), agents already run concurrently (`registry.py:204`), and the `pre_iteration_hook` already drains results before each iteration (`app.py:363`). The *only* thing forcing "wait for each other, return together" is one gate — `if registry.active_count != 0: return False` in `_wake_for_pending_agents` (`app.py:50-72`) — which holds the wake until **every** agent has finished, then injects all summaries at once.

2. **Model behavior has changed.** Older models dispatched agents and *ended the turn* — so the system had to **wake** an absent model when results landed. Newer models **stay in the turn and poll** (`list_agents` every minute when told to "wait 5 minutes"). They reach out to **pull** the result — but no tool returns the deliverable, so they see `status: completed` and get stuck. The architecture (push) and the models (pull) are fighting each other.

So we stop pushing and let the model pull. This deletes the entire wake/debounce/cycle layer that existed only to serve absent models, and it eliminates the overlap race observed in practice (two `ChatLoop.run()`s sharing `self.messages`), because **results enter the conversation only when the model reads them, inside a turn it controls — there is no second writer.**

## 2. The model in three pieces

1. **An agent run is a small state record** the main LLM polls and drains.
2. **Two tools** let the LLM pull: `agent_status()` and `read_agent_result()`.
3. **One 1-second TUI timer** wakes the LLM *only* when it left a finished result unread while idle.

Everything below is in service of those three.

## 3. Data model — `AgentRun`

A per-dispatch record kept by the registry, keyed by `run_id`. It folds in and replaces `AgentSummary` (which is deleted along with `_summary_queue`).

| field | type | meaning |
|---|---|---|
| `run_id` | `int` | unique within the registry instance |
| `agent_name` | `str` | which configured agent |
| `status` | `str` | `"working"` → `"done"` \| `"error"` (timeout is reported as `error` with a timeout message) |
| `result` | `str` | the agent's **final assistant message**, verbatim; `""` until finished |
| `error` | `str \| None` | error/timeout detail, separate from `result` |
| `note_path` | `str \| None` | project-relative path of the auto-written note (§9) |
| `started_at` | `float` | `monotonic()` at dispatch — for `working_time` |
| `finished_at` | `float \| None` | `monotonic()` at completion |
| `drained` | `bool` | the main LLM has read `result` via `read_agent_result` |
| `nudged` | `bool` | the timer has already woken the LLM about this result |
| `done_event` | `asyncio.Event` | set on completion; lets `read_agent_result(wait=true)` block |

`working_time` is derived: `(finished_at or now) - started_at`.

The registry holds `_runs: dict[int, AgentRun]`. `active_count` becomes `sum(1 for r in _runs.values() if r.status == "working")`. The existing `_settled` re-dispatch guard (block an agent that failed this cycle) and `reset_settled()` are **kept as-is** — orthogonal to delivery.

### Status vocabulary

Model-facing status is exactly `working | done | error` (decision §13). The richer internal outcomes map: `running → working`; `completed → done`; `timeout / exception / failed → error` (with the cause in `error`). "idle" is dropped — it was ambiguous with "not yet started."

## 4. Tools — the LLM pulls

### `call_agent(name, task)` — *changed return only*

Still fire-and-forget, still `registry.dispatch(...)`. The return string now leads with the **run_id** so the model can poll/drain it:

> `Dispatched 'reviewer' as run #7 (working). Poll with agent_status; collect with read_agent_result(7).`

### `agent_status()` — **new**, the poll

Returns a JSON list over `_runs` (newest first):

```json
[{"run_id": 7, "name": "reviewer", "status": "done",
  "working_time_s": 42, "has_unread_result": true,
  "note_path": ".ayder/notes/20260618-143022-reviewer-run7.md"}]
```

Cheap, read-only (`permission="r"`). This is the answer the model's "poll every minute" loop has been missing. It deliberately does **not** include `result` (that's a deliberate drain step, so terse output isn't drowned by status noise).

### `read_agent_result(run_id, wait=false, timeout_s=60)` — **new**, the drain

Returns `{run_id, name, status, result, note_path, working_time_s, error}` and sets `drained=True`. This is the tool that's missing today.

- `wait=false` (default): returns immediately. If still `working`, returns `status:"working"` and an empty result (the model can poll again or end its turn and let the timer wake it).
- `wait=true`: **blocks the tool call** on `done_event` until the run finishes or `timeout_s` elapses, then returns. This folds the model's improvised "wait 5 minutes, poll every minute" loop into a single efficient call. On timeout it returns the current (`working`) state without error.

Decision §13: include `wait` as an add-on; the core (poll + read) works without it.

> **Concurrency note (implementation):** tool handlers run inside `asyncio.to_thread` (`chat_loop.py:566`), i.e. on a worker thread, while the runner mutates `AgentRun` on the event loop. The registry methods these tools call must be safe from a worker thread — mirror `dispatch`'s existing pattern. `wait=true` blocks via `run_coroutine_threadsafe(run.done_event.wait(), loop).result(timeout_s)`. Simple field reads/`drained=True` writes rely on the same single-loop affinity `dispatch` already assumes.

### Capability prompt rewrite — `registry.py:99-119`

Replace the batch language ("you will receive all agent summaries after all agents complete") with the pull contract:

- dispatch with `call_agent` (returns a run id); agents run in the background.
- **You pull results** — they are not delivered automatically. Use `agent_status()` to see what's running/done and `read_agent_result(run_id)` to collect a finished one.
- To wait for an agent, call `read_agent_result(run_id, wait=true, timeout_s=…)` rather than polling in a loop.
- Each finished run has a `note_path` to its full saved deliverable (best-effort); if a result has scrolled out of context, `read_file` that path instead of re-dispatching.
- If you end your turn with results still unread, you'll be nudged once to collect them.
- On agent failure, handle the task yourself; do not re-dispatch a failed agent.

## 5. The 1-second timer — the only background trigger

In `on_mount`: `self.set_interval(1.0, self._check_agents)` (idiomatic Textual; a once-per-second dict scan is free; early-return instantly when no registry/agents).

```
_check_agents (every 1s, runs on the event loop):
    if a turn is running:            return     # the model drains via tools mid-turn
    pending = registry.pending_nudge()          # status in {done,error}, not drained, not nudged
    if not pending:                  return
    registry.mark_nudged(pending)               # at most ONE nudge per finished result
    self.messages.append({"role": "user",
        "content": "[system] <N> agent result(s) are ready and unread. "
                   "Call agent_status() to see them and read_agent_result(run_id) to collect."})
    self._start_turn()                          # the woken turn; the model then PULLS
```

This single level-triggered check covers **both** timing cases with one mechanism:

- **Agent finishes while the LLM is idle** (it already exited) → caught on the next tick.
- **Agent finishes mid-turn, the model didn't drain, the turn then ends** → next tick sees it `done + unread + idle` → wakes.

Notes on the design:

- The wake injects a **nudge** ("go check"), never the deliverable — the deliverable is still pulled. So this stays a pull architecture; the nudge is just a wake trigger and is harmless if stale.
- `nudged` (distinct from `drained`) is **load-bearing**: without it, a model that wakes and chooses *not* to drain would be re-woken every second forever. One nudge per result; after that the result waits, readable on demand, un-nagged.
- It runs on the single-threaded event loop and starts the turn **only when idle**, so it cannot overlap a running turn.
- `_agent_complete` (`app.py:259-283`) no longer triggers any wake — it only updates the agent panel / activity bar UI. The `active_count` gate, `_wake_for_pending_agents`, and the `pre_iteration_hook` agent-drain are removed.

## 6. Serial turn-start — the ~20-line spine

The observed overlap came from Textual's `exclusive=True` worker, whose cancel does **not** await teardown, so a replacement `ChatLoop.run()` started while the old one was still unwinding on the shared `self.messages`/`callbacks`. We replace it with one app-owned task:

```
self._turn_task: asyncio.Task | None = None

_start_turn():
    if self._turn_task is not None:    return       # busy — caller queues (see below)
    self._turn_task = asyncio.create_task(self.chat_loop.run())
    self._turn_task.add_done_callback(self._on_turn_done)

is_turn_running -> bool:  return self._turn_task is not None
```

`_on_turn_done` clears `_turn_task`, does the existing post-turn UI teardown, and then **drains the user queue**: if `self._pending_messages` is non-empty, start the next queued user turn. Both callers of `_start_turn` — user input (`handle_input_submitted`) and the timer wake — start a turn only when idle and otherwise queue the user text (existing `_pending_messages`). Because the timer checks `is_turn_running` and `create_task` with no intervening `await`, no second turn can interleave.

This spine is the *entire* residue of rev. 5's `TurnEngine`. It replaces the scattered `start_llm_processing()` calls and the exclusive worker.

## 7. Conversation reset — staleness in one line

`cycle_id` is gone. When the conversation is **replaced** (`/clear`, `/compact`, `apply_pending_compact`, skill load, provider/model switch), call `registry.reset_runs()`, which drops `_runs` (or marks all `drained`). A result from the old conversation then can't be pulled into the new one, and the timer has nothing to nudge about. `/load-context` *appends* and does **not** reset (prior runs stay valid). This replaces the entire cycle-invalidation map from rev. 5.

## 8. Data flow

```
call_agent(name, task)
  → registry.dispatch: create AgentRun(status=working, started_at=now); schedule _run_and_queue
  → returns run_id  → tool: "Dispatched 'name' as run #N (working)."

(background) runner.run(task)
  → ChatLoop runs the agent
  → _final_message(messages)                 # the deliverable (last real assistant text)
  → write_agent_note(...)                    # auto-persist to .ayder/notes/  (§9)
  → _run_and_queue updates the run: status=done|error, result, error, note_path,
       finished_at=now, done_event.set()

(model, mid-turn)   agent_status()           → snapshot of all runs
(model)             read_agent_result(id)    → result + note_path; drained=True
                    read_agent_result(id, wait=true, timeout_s) → blocks on done_event

(timer, idle, 1s)   done+unread+not-nudged?  → mark_nudged + nudge message + _start_turn → model pulls

(conversation reset) registry.reset_runs()   → stale results unreadable; nothing to nudge
```

## 9. Notes integration (consumes the agent-notes spec)

Kept, with one change. `write_agent_note(...)` and the runner auto-persisting the **final message** to `.ayder/notes/{ts}-{slug}-run{id}.md` for every terminal status (best-effort, never fails the run) are exactly as in `2026-06-18-agent-notes-design.md`. This is the durability answer for "small LLMs complete and return nothing": even a terse `result` leaves a full note, and `note_path` is surfaced in both pull tools.

**Superseded parts of that spec:** the `note=` attribute on an injected `[agent-result]` block, and its dependence on `cycle_id` / `format_for_injection` / `inject_agent_results`. There is no injected block anymore — `note_path` reaches the model via `agent_status()` / `read_agent_result()` instead. `_write_note` extraction, the collision-proof filename, and YAML-safe frontmatter all carry over unchanged.

The agent system prompt is *directed* (decision §13) to put its complete deliverable in its final message — that single message is both the `read_agent_result` payload and the note body. No separate "write your report" tool step.

## 10. What gets deleted vs rev. 5 / current

**Deleted:** `WakeDebouncer` (never built), `cycle_id` everywhere, the `INTERRUPT_AND_RUN/MUTATE` command-transition API, out-of-band system-message injection, the `active_count != 0` wake gate, `_wake_for_pending_agents`, `pre_iteration_hook` agent-drain, `AgentSummary` + `_summary_queue` + `drain_summaries` + `has_pending_summaries`, `_parse_summary` / `_SUMMARY_PATTERN`.

**Kept small:** `AgentRun` record, two pull tools, one 1-second timer, the ~20-line serial turn-start, `registry.reset_runs()`, auto-notes.

## 11. Scope

**In scope:** the pull tools + `AgentRun` state, the timer wake, the serial turn-start that removes the agent-wake overlap, reset-on-replace staleness, auto-notes, capability-prompt rewrite. TUI (`AyderApp`) only.

**Out of scope / deferred (with reasons):**

- **Safe command *interruption* mid-turn** (cancel a running turn and start a replacement for `/ask`, `/provider`, etc.). This is a **pre-existing** concern, independent of agents, and is the *other* source of the overlap rev. 5 tried to fix. The serial spine guarantees no overlap by never running two turns at once; for now breaking commands **queue** behind a running turn rather than interrupting it. Full cancel-and-replace (await teardown, mutate-when-quiescent) is a separate follow-up. **Open question for the plan phase:** is "commands queue, no mid-turn interrupt" acceptable as the first step, or is interrupting `/ask` required on day one?
- **CLI (`cli_runner.py`)** single-shot path — unchanged; documented as TUI-only.
- **Model-callable agent cancellation** — next phase.
- **Note retention/cleanup** — gitignored scratch; user-managed.

## 12. Testing strategy

- **`AgentRun` / registry:** dispatch creates a `working` run; completion sets `done`/`error` + `result` + `note_path` + `finished_at` + fires `done_event`; `pending_nudge()` returns only `done|error ∧ ¬drained ∧ ¬nudged`; `read_result` sets `drained`; `mark_nudged` sets `nudged`; `reset_runs` empties; `working_time` derives from start/finish.
- **Tools:** `agent_status()` snapshot shape, newest-first, `has_unread_result` correctness, no `result` leakage; `read_agent_result` returns body + sets `drained`; `wait=true` blocks then returns on completion and returns `working` on timeout (async test with a controllable `done_event`).
- **Runner:** `_final_message` returns the last real assistant text (skips `<think>`/tool-only), not the transcript; `error` status whenever `callbacks.last_system_error` is set (drop the cumulative-`last_content` guard); note persisted and `note_path` set (tmp_path ctx).
- **Timer `_check_agents`:** wakes once on `done+unread+idle`; does **not** wake while a turn runs; does **not** re-wake an already-`nudged` result (no loop); injects a nudge (not the deliverable) then starts one turn.
- **Serial turn-start:** two `_start_turn()` calls never produce two concurrent tasks; user text arriving mid-turn queues and runs on `_on_turn_done`.
- **Reset:** `reset_runs()` on `/clear`/compact/skill/provider leaves nothing to pull or nudge.
- Run `uv run poe check-all` **and** `uv run poe test-all` (the latter covers config tests `poe test` ignores — `pyproject.toml:72`).

## 13. Locked decisions (from brainstorming)

1. Delivery model is **pull**, not push; unprompted idle-wake is abandoned except the minimal timer nudge.
2. Status names: `working / done / error`.
3. `read_agent_result` includes the optional **blocking** `wait=true, timeout_s` variant.
4. Note = the agent's auto-written final message; the agent is prompted to put its full deliverable there.
5. Wake mechanism = a **1-second TUI timer**, level-triggered on `done + unread + not-nudged + idle`, with `nudged` distinct from `drained`.
