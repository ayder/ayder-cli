# Agent-Result Pull Delivery — Design Spec (rev. 2)

**Date:** 2026-06-18
**Status:** Approved (brainstorming) — pending spec re-review
**Supersedes:** `docs/superpowers/plans/2026-06-17-agent-result-push-delivery.md` (rev. 5 — the serial `TurnEngine` / push design)
**Consumes:** `docs/superpowers/specs/2026-06-18-agent-notes-design.md` (auto-written deliverable notes — kept; injection-specific parts superseded, see §10)

**rev. 2 — spec review corrections (all confirmed against the code):** (1) `new_generation()` filters visibility instead of dropping `_runs`, so active runs survive cancellation/UI/completion; (2) **single-loop ownership** of all registry state (§4); (3) the serial spine queues **complete turn/command requests with deferred mutations**, not just user strings (§6); (4) pull tools are registered in **both** CLI and TUI; only the timer-nudge is TUI-only (§5, §12); (A) `nudged` is set only after the wake turn is enqueued; (B) `timeout_s` is capped (§5); (C) note wording corrected — a note is a durable copy, not extra information (§10); (D) nudges are **event-driven** (completion + turn-finished) with the 1 s timer as a recovery fallback (§7).

---

## 1. Why this replaces the push design

The push plan (rev. 5) grew to ~1800 lines / 9 tasks — serial `TurnEngine`, `WakeDebouncer`, `cycle_id` invalidation, a three-mode command-transition API — to deliver one thing: results arriving one at a time.

Two facts collapse most of that:

1. **The current code already pushes.** `call_agent` is already fire-and-forget (`tool.py:81`), agents already run concurrently (`registry.py:204`), and the `pre_iteration_hook` already drains results before each iteration (`app.py:363`). The one thing forcing "wait for each other, return together" is a single gate — `if registry.active_count != 0: return False` in `_wake_for_pending_agents` (`app.py:50-72`).

2. **Model behavior changed.** Old models dispatched agents and *ended the turn*, so the system had to **wake** an absent model. New models **stay in the turn and poll** (`list_agents` every minute on "wait 5 minutes") — they want to **pull** the result, but no tool returns the deliverable, so they get stuck on `status: completed`.

So we let the model pull. This deletes the **injection/wake layer** that existed only for absent models (out-of-band system-message injection, `WakeDebouncer`, batch summaries) and removes the observed overlap race, because **results enter the conversation only when the model reads them, inside a turn it controls — no second writer.**

What this does **not** delete: a single serialized turn consumer. rev. 5 was right that turn execution must be serialized; it was wrong to wrap that in push injection + `cycle_id` + three transition modes. We keep the serial consumer (§6) and shed the rest.

## 2. The model in five pieces

1. **`AgentRun`** — a per-dispatch state record the LLM polls and drains (§3).
2. **Single-loop ownership** — the event loop is the sole mutator of registry state (§4).
3. **Two pull tools** — `agent_status()` and `read_agent_result()` (§5), registered in CLI **and** TUI.
4. **A serial turn/command consumer** — one `ChatLoop.run()` at a time; commands defer their state mutation into the request so they can't corrupt a running turn (§6).
5. **Event-driven nudges** — on agent completion / turn-finished, if the LLM left a result unread while idle, wake it once; a 1 s timer is the recovery fallback (§7).

## 3. Data model — `AgentRun`

A per-dispatch record kept by the registry, keyed by `run_id`. Folds in and replaces `AgentSummary` (deleted, along with `_summary_queue`).

| field | type | meaning |
|---|---|---|
| `run_id` | `int` | unique within the registry instance |
| `generation` | `int` | the conversation generation at dispatch (§8) |
| `agent_name` | `str` | which configured agent |
| `status` | `str` | `"working"` → `"done"` \| `"error"` (timeout → `error` with a timeout message) |
| `result` | `str` | the agent's **final assistant message**, verbatim; `""` until finished |
| `error` | `str \| None` | error/timeout detail, separate from `result` |
| `note_path` | `str \| None` | project-relative path of the auto-written note (§10) |
| `started_at` | `float` | `monotonic()` at dispatch — for `working_time` |
| `finished_at` | `float \| None` | `monotonic()` at completion |
| `drained` | `bool` | the LLM has read `result` via `read_agent_result` |
| `nudged` | `bool` | a nudge has already been raised for this result (set only after the wake turn is enqueued) |
| `done_event` | `asyncio.Event` | set on completion; lets `read_agent_result(wait=true)` block |

`working_time` is derived: `(finished_at or now) - started_at`.

The registry holds `_runs: dict[int, AgentRun]` and `_current_generation: int`. `active_count` is `sum(1 for r in _runs.values() if r.status == "working")`. The runner reference for cancellation lives on the run (or in the existing `_active` map). The `_settled` re-dispatch guard is kept, with one change (§8): a completing run updates `_settled` only if it is current-generation.

**Status vocabulary** is exactly `working | done | error` (decision §14); "idle" is dropped (ambiguous with "not started").

## 4. Concurrency model — single-loop ownership

All `AgentRun`/registry **state is owned by the event loop**; nothing mutates it from a worker thread (correcting rev. 1's reliance on `dispatch`'s existing worker-thread mutation, which is a GIL-masked latent race, not a sanctioned pattern).

- Code that already runs on the loop — the completion callback (`_run_and_queue`), the nudge timer, turn-finished handling — calls registry methods **directly**.
- **Tool handlers run in worker threads** (`asyncio.to_thread`, `chat_loop.py:566`). Every registry operation they need is marshalled onto the loop with `run_coroutine_threadsafe(coro, loop).result(...)`:
  - `call_agent` → `create_run(name, task)` (creates the `AgentRun` + schedules the agent run on the loop; returns `run_id`).
  - `agent_status` → `snapshot()`.
  - `read_agent_result(wait=false)` → `read_result(run_id)` (returns body, sets `drained`).
  - `read_agent_result(wait=true)` → `await_run(run_id, timeout_s)` (awaits `done_event` on the loop, then reads).
- The worker thread blocking on `.result()` is fine — it is *not* the loop thread, so the loop stays free to run the marshalled coroutine. No deadlock, no lock needed; the loop's single-threadedness *is* the serialization.

This makes finding 2 structural rather than hope-based, and it keeps `dispatch`'s state creation on the loop too.

## 5. Tools — the LLM pulls (registered in CLI and TUI)

### `call_agent(name, task)` — *changed return only*

Still fire-and-forget. The return string now leads with the **run_id**:

> `Dispatched 'reviewer' as run #7 (working). Poll with agent_status; collect with read_agent_result(7).`

### `agent_status()` — **new**, the poll

Read-only (`permission="r"`). Returns a JSON list over current-generation runs, newest first:

```json
[{"run_id": 7, "name": "reviewer", "status": "done",
  "working_time_s": 42, "has_unread_result": true,
  "note_path": ".ayder/notes/20260618-143022-reviewer-run7.md"}]
```

Deliberately omits `result` (drain is a separate step, so terse output isn't buried in status noise).

### `read_agent_result(run_id, wait=false, timeout_s=60)` — **new**, the drain

Returns `{run_id, name, status, result, note_path, working_time_s, error}` and sets `drained=True`.

- `wait=false`: returns immediately; if still `working`, returns the `working` state with empty `result`.
- `wait=true`: blocks on `done_event` until the run finishes or `timeout_s` elapses, then returns. Folds the model's "poll every minute" loop into one call. On timeout, returns the current `working` state (no error).
- **`timeout_s` is validated and capped** to `[0, agent_timeout]` (finding B). The blocking wait runs inside a worker-thread `to_thread` call and **cannot be cancelled mid-wait** (only times out), so the cap is the sole guard against a model occupying a worker thread.

### Capability prompt — `registry.py:99-119` (shared by CLI and TUI)

Replace the batch language with the pull contract: dispatch returns a run id; **you pull results — they are not delivered automatically**; use `agent_status()` then `read_agent_result(run_id)`; to wait, use `read_agent_result(run_id, wait=true, timeout_s=…)` instead of looping; each finished run has a best-effort `note_path` (`read_file` it if the result scrolled out of context); if you end your turn with results unread you'll be nudged once; on failure, handle the task yourself.

### Registration (finding 4)

`agent_status` and `read_agent_result` are registry tools, registered wherever `call_agent` is — **`tui/app.py` and `cli_runner.py:64-67`**. The shared `get_capability_prompts()` then matches the tools that actually exist in both entry points. Pull works in single-shot CLI too (the CLI wires the loop, `cli_runner.py:100`, so `wait` and marshalling function). **Only the timer-nudge (§7) is TUI-only** — the CLI's single turn ends when the model stops, which is correct for single-shot.

## 6. Serial turn/command consumer

The observed overlap came from Textual's `exclusive=True` worker, whose cancel does **not** await teardown, so a replacement `ChatLoop.run()` began while the old one was still unwinding on the shared `self.messages`/`callbacks`. We replace it with one app-owned serial consumer. This **is** the legitimate core of rev. 5's `TurnEngine` — what we shed vs rev. 5 is `cycle_id` (→ generation, §8), the `WakeDebouncer` (→ §7), and the three named transition modes (→ one `request_turn` + a `prepare` callback).

```
@dataclass
class TurnRequest:
    prepare: Callable[[], None] | None = None   # state mutation, run ONLY when quiescent
    run_loop: bool = True                        # False => mutate runtime only (e.g. /provider)
    no_tools: bool = False                       # e.g. /ask
    interrupt: bool = False                      # cancel the active turn before this one

self._requests: asyncio.Queue[TurnRequest]
self._run_task: asyncio.Task | None = None      # the one in-flight ChatLoop.run()

async def _turn_consumer():                      # single consumer, started in on_mount
    while True:
        req = await self._requests.get()
        if req.prepare: req.prepare()            # safe: no turn is running here
        if not req.run_loop: continue
        self._run_task = create_task(chat_loop.run(no_tools=req.no_tools))
        try:    await self._run_task             # AWAIT teardown before the next request
        finally:
            self._run_task = None
            self._after_turn_finished()          # UI teardown + nudge check (§7)

def request_turn(prepare=None, *, run_loop=True, no_tools=False, interrupt=False):
    self._requests.put_nowait(TurnRequest(prepare, run_loop, no_tools, interrupt))
    if interrupt and self._run_task: self._run_task.cancel()  # consumer awaits teardown, then runs next
```

**Why finding 3 needs this:** commands mutate shared state immediately today (`/compact` clears `messages`, `/provider` rebuilds the provider, `/skill` replaces `messages`, `/ask` appends + starts a no-tools turn). Queuing user *strings* doesn't stop that. Each breaking command instead defers its mutation into `prepare` and calls `request_turn(...)`; the consumer runs `prepare` only when no turn is in flight, so it can't corrupt a running turn. User input is just `request_turn(prepare=append-the-message)`. The nudge (§7) is `request_turn(prepare=append-nudge-text)`.

**v1 interrupt policy (open decision, §12):** breaking commands default to **queue** (`interrupt=False` → run after the current turn finishes); `Esc`/cancel cancels the active `_run_task`. The `interrupt=True` path exists for when we decide a command must preempt.

## 7. Nudges — event-driven, timer as fallback (finding D)

A nudge wakes the LLM when it left a finished result unread **while idle**. It injects a short *nudge* ("go check"), never the deliverable — the deliverable is still pulled (so this stays pull; a stale nudge is harmless).

```
_maybe_nudge():                                  # runs on the loop
    if self._run_task is not None: return        # a turn is running; model drains via tools
    pending = registry.pending_nudge()           # current-gen, status in {done,error}, not drained, not nudged
    if not pending: return
    self.messages.append({"role": "user",
        "content": "[system] <N> agent result(s) are ready and unread. "
                   "Call agent_status() then read_agent_result(run_id) to collect."})
    request_turn()                               # enqueue the wake turn
    registry.mark_nudged(pending)                # finding A: set nudged AFTER enqueue succeeds
```

Triggers:

- **Primary (immediate):** the agent-completion callback calls `_maybe_nudge()`; and `_after_turn_finished()` (turn teardown) calls it. Together these react with no delay and cover both "finishes while idle" and "finishes mid-turn, undrained, then the turn ends."
- **Fallback (recovery):** `set_interval(1.0, _maybe_nudge)` catches anything the events missed (e.g. a completion that raced with teardown). A once-per-second guarded check is free.

`nudged` (distinct from `drained`) is load-bearing: it makes running events **and** the timer safe (no double-wake) and stops a re-wake loop if the model chooses not to drain. One nudge per result; after that it waits, readable on demand.

`_agent_complete` (`app.py:259-283`) keeps only its UI updates plus the `_maybe_nudge()` call. The `active_count` gate, `_wake_for_pending_agents`, and the `pre_iteration_hook` agent-drain are removed.

## 8. Conversation generation — staleness without dropping runs (finding 1)

`cycle_id`'s invalidation map is gone, but a generation marker is still needed so a prior conversation's result can't be pulled into a new one. It is **lightweight**: one bump site, three read-side filters.

- `registry.new_generation()` increments `_current_generation` and calls `reset_settled()`. It does **not** touch `_runs`, so active agents keep running, stay counted in `active_count`, remain cancellable, and their completion still updates their own record correctly.
- A dispatch stamps `run.generation = _current_generation`.
- The three delivery paths filter on `run.generation == _current_generation`: `snapshot()` (status), `read_result`/`await_run` (drain), `pending_nudge()` (wake). Old-generation runs finish harmlessly and are simply never delivered/nudged into the new conversation.
- A completing run updates `_settled[name]` **only if** `run.generation == _current_generation`, so an obsolete run can't pollute the new conversation's re-dispatch guard.

`new_generation()` is called from the conversation-replacement paths — `/clear` (`do_clear`), `/compact` (`handle_compact`), `apply_pending_compact` (`app.py:808`), skill load (`handle_skill`), provider/model switch. `/load-context` *appends* → **no** bump (prior runs stay valid). (In-flight agents are intentionally **not** cancelled on reset — they finish and are filtered out. Reset-cancels-agents is a separate product choice, out of scope.)

## 9. Data flow

```
call_agent(name, task)
  → (worker thread) run_coroutine_threadsafe(create_run(name, task), loop).result()
  → (loop) AgentRun(status=working, generation=current, started_at=now); schedule the agent run
  → returns run_id  → tool: "Dispatched 'name' as run #N (working)."

(background, loop) agent run completes
  → _final_message(messages)          # the deliverable (last real assistant text)
  → write_agent_note(...)             # auto-persist to .ayder/notes/  (§10)
  → update run: status=done|error, result, error, note_path, finished_at, done_event.set()
  → if run.generation == current: _settled[name] = status
  → _maybe_nudge()                    # event-driven (§7)

(model, mid-turn)  agent_status()                         → snapshot (current-gen)
(model)            read_agent_result(id[, wait, timeout]) → result + note_path; drained=True

(idle)             completion/turn-finished/1s-timer → _maybe_nudge() → wake turn → model pulls
(conversation reset) registry.new_generation()       → old-gen runs finish but are never delivered
```

## 10. Notes integration (consumes the agent-notes spec)

Kept. `write_agent_note(...)` and the runner auto-persisting the **final message** to `.ayder/notes/{ts}-{slug}-run{id}.md` for every terminal status (best-effort, never fails the run) are exactly as in `2026-06-18-agent-notes-design.md`.

**Correction (finding C):** a note is a **durable copy of the final message** — browsable via `/notes`, re-readable after the result scrolls out of context. It does **not** contain more than the model produced; a terse final message yields a terse note. The mitigation for terse models is the system-prompt **directive** to put the complete deliverable in the final message (decision §14) — a model-dependent prompt lever, not a magic property of notes.

**Superseded parts of that spec:** the `note=` attribute on an injected `[agent-result]` block and its dependence on `cycle_id` / `format_for_injection` / `inject_agent_results` — there is no injected block; `note_path` reaches the model via the pull tools. `_write_note` extraction, the collision-proof filename, and YAML-safe frontmatter carry over unchanged.

## 11. Deleted vs rev. 5 / current — and what is kept

**Deleted:** out-of-band system-message injection (`inject_agent_results`, the user-vs-system role analysis, oversized path-only rendering), `WakeDebouncer` (never built), the `active_count != 0` gate, `_wake_for_pending_agents`, the `pre_iteration_hook` agent-drain, `AgentSummary` + `_summary_queue` + `drain_summaries` + `has_pending_summaries`, `_parse_summary`/`_SUMMARY_PATTERN`, the three-mode command-transition API.

**Kept from rev. 5's core (it was right):** a single serialized turn consumer with `request_turn` + a `prepare` callback that mutates only when quiescent (§6); a generation marker (§8, now visibility-only).

**New / smaller:** `AgentRun`, two pull tools, single-loop ownership, event+timer nudges, `new_generation()` (one bump + three filters), auto-notes.

## 12. Scope

**In scope:** `AgentRun` + pull tools (CLI **and** TUI), single-loop ownership, the serial turn/command consumer, generation-based staleness, event+timer nudges (TUI), auto-notes, capability-prompt rewrite.

**Open decision (needs your call before the plan):** the **v1 interrupt policy** of §6 — do breaking commands **queue** behind a running turn (simplest; `Esc` cancels), or must specific commands (e.g. `/ask`, `/provider`) **interrupt** (`interrupt=True`) on day one? The machinery supports both; this only sets defaults.

**Out of scope / deferred:**
- Model-callable agent cancellation — next phase.
- Cancelling in-flight agents on conversation reset — product choice, deferred (§8).
- Note retention/cleanup — gitignored scratch, user-managed.

## 13. Testing strategy

- **`AgentRun` / registry (single-loop):** `create_run` stamps `generation` + `working`; completion sets `done`/`error` + `result` + `note_path` + `finished_at` + fires `done_event`; `pending_nudge()` returns only current-gen `done|error ∧ ¬drained ∧ ¬nudged`; `read_result` sets `drained`; `await_run` resolves on completion and on timeout returns `working`; `mark_nudged` sets `nudged`; `working_time` derives correctly.
- **Generation (finding 1):** `new_generation()` bumps + `reset_settled` but **keeps** `_runs` and `active_count`; an old-gen run still completing updates its record but is excluded from `snapshot`/`read`/`pending_nudge`, and does **not** update `_settled`.
- **Concurrency (finding 2):** tool-path operations marshalled via `run_coroutine_threadsafe` return correctly from a worker thread; `read_agent_result(wait=true)` blocks then resolves (async test with a controllable `done_event`); `timeout_s` is capped (finding B).
- **Serial consumer (finding 3):** two `request_turn`s never run two concurrent `ChatLoop.run()`s; a `prepare` mutation runs only while quiescent (assert no mutation lands during an in-flight turn); a queued command's `prepare` runs on `_after_turn_finished`; `interrupt=True` cancels the active task and the next request runs after teardown.
- **Nudge (findings A, D):** completion while idle nudges immediately; turn-finished with an unread result nudges; a running turn suppresses the nudge; an already-`nudged` result does not re-nudge (no loop); `nudged` is **not** set if enqueue fails (assert a later trigger retries); the 1 s timer nudges a completion the events missed.
- **CLI (finding 4):** `agent_status`/`read_agent_result` are registered and callable in `cli_runner`; the capability prompt names only tools that exist.
- Run `uv run poe check-all` **and** `uv run poe test-all` (the latter covers config tests `poe test` ignores — `pyproject.toml:72`).

## 14. Locked decisions (from brainstorming + spec review)

1. Delivery is **pull**, not push; unprompted idle-wake is abandoned except the minimal nudge.
2. Status names: `working / done / error`.
3. `read_agent_result` includes the optional **blocking** `wait=true, timeout_s` variant, with `timeout_s` capped.
4. Note = the agent's auto-written final message; the agent is *prompted* to put its full deliverable there (notes add durability, not information).
5. Nudges are **event-driven** (completion + turn-finished); the 1 s timer is a recovery fallback. `nudged` is distinct from `drained` and set only after the wake turn is enqueued.
6. Registry state is **owned solely by the event loop**; worker-thread tool handlers marshal via `run_coroutine_threadsafe`.
7. Conversation staleness uses a **generation marker that filters visibility**, never dropping active runs.
8. The serial turn consumer queues **complete turn/command requests** (with `prepare` mutations), not just user strings. Pull tools are registered in **both** CLI and TUI.
