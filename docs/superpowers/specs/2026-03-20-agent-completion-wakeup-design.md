# Agent Completion Wake-up & Batch Coordination

**Date:** 2026-03-20
**Status:** Approved (brainstorm)

## Problem

When agents complete their work, the main LLM only learns about it on the next user message (via `pre_iteration_hook`). The main LLM should automatically react to agent completions without the user needing to type anything.

Additionally, when multiple agents are dispatched in parallel, the main LLM should receive all results at once — not be woken per completion.

## Design

### 1. Batch Wake-up

Add an `on_complete` callback to `AgentRegistry`. When an agent finishes:

1. `_run_and_queue()` puts `AgentSummary` in `_summary_queue` (existing)
2. `_run_and_queue()` calls `on_complete(summary)` (new)
3. Callback checks: are other agents still in `_active`?
   - **YES** → update `AgentPanel` only, don't wake LLM
   - **NO** → drain all summaries from queue, inject into `self.messages` as system messages, call `start_llm_processing()` if `_is_processing` is False

This ensures:
- Single agent dispatch: immediate wake-up on completion
- Multi-agent dispatch: one wake-up after ALL agents finish, all summaries delivered together
- If main LLM is already processing (user typed while agents ran): `pre_iteration_hook` handles it as before

### 2. Re-dispatch Guard

Prevent infinite agent retry loops with a batch-scoped tracker:

- `AgentRegistry` maintains a `_settled: dict[str, str]` mapping agent name → last status
- After all agents complete (batch settles), populate `_settled` from completed summaries
- On next `dispatch()` call, check `_settled`:
  - If agent's last status was `"error"` or `"timeout"` → reject with message: "Agent '{name}' failed in this cycle. Handle the task directly."
  - If agent's last status was `"completed"` → allow re-dispatch (agent worked fine, task results may vary)
- `_settled` resets on next user message (new cycle)

**Key distinction:**
- `status = "completed"` → agent infrastructure worked. Summary content describes task outcome (tests passed/failed, data found/not found). Re-dispatch allowed.
- `status = "error"` or `"timeout"` → agent itself broke. Re-dispatch blocked. Main LLM handles task directly.

### 3. Status Indicator

Non-blocking "Agents running..." display while agents work:

- `AgentPanel` already shows/hides and tracks agent status
- Add a lightweight indicator to `ActivityBar` when agents are active (count of running agents)
- Clear indicator when batch completes (ties into the `on_complete` callback)

## Data Flow

```
User: "Run all news agents and summarize"
  │
  ├─ Main LLM dispatches agent-1, agent-2, agent-3
  │    └─ dispatch() → fire-and-forget, returns immediately
  │    └─ Main LLM responds: "Dispatched 3 agents..."
  │    └─ ChatLoop.run() exits (text-only response)
  │    └─ _is_processing = False (idle)
  │
  ├─ TUI shows "Agents running (3)..." in activity bar
  │
  ├─ agent-1 completes → on_complete → _active has 2 left → panel update only
  ├─ agent-2 completes → on_complete → _active has 1 left → panel update only
  ├─ agent-3 completes → on_complete → _active empty →
  │    └─ drain all 3 summaries
  │    └─ inject into messages as system messages
  │    └─ call start_llm_processing()
  │
  └─ Main LLM wakes with all 3 summaries → produces unified response
```

## Files Affected

- `src/ayder_cli/agents/registry.py` — add `on_complete` callback, `_settled` tracker, guard logic
- `src/ayder_cli/tui/app.py` — wire `on_complete`, handle idle wake-up, activity bar indicator
- `src/ayder_cli/tui/widgets.py` — optional: activity bar agent count display

## Constraints

- No architectural changes to `ChatLoop` or `ChatCallbacks`
- `AgentRegistry` stays Textual-agnostic (communicates via callbacks only)
- `pre_iteration_hook` remains as fallback for mid-processing completions
- Existing tests must not break
