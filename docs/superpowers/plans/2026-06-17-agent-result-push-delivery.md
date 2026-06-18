# Agent-Result Push Delivery Implementation Plan (rev. 5 — serial turn engine)

> **⚠️ SUPERSEDED (2026-06-18)** by `docs/superpowers/specs/2026-06-18-agent-result-pull-delivery-design.md`. This push design (serial `TurnEngine` + `WakeDebouncer` + `cycle_id` + command-transition API) is replaced by a **pull** model: the LLM polls `agent_status()` and drains via `read_agent_result()`, with a single 1-second TUI timer nudging it when it leaves a result unread. Do not implement this plan. Kept for history / review provenance.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Revision note:** Revised after `.ayder/020-codex-multi-agent-review.md`. Findings F1, F2, F3, F5, F6, F7 confirmed against the code and incorporated; F4 (role) resolved by decision (user-role block); F8 addressed (unit + integration). Verified facts: `commands.py` has 7 direct `start_llm_processing()` calls (363, 380, 394, 427, 483, 783, 869); `callbacks.py:59` accumulates `last_content` across all iterations and never resets; `claude.py:170-171` / `gemini.py:176-177` concatenate **all** system messages into the top-level system prompt; `pyproject.toml:72` ignores `tests/core/test_config.py`. **rev. 3** folds in the agent-notes design (`docs/superpowers/specs/2026-06-18-agent-notes-design.md`): the runner persists each agent's final message to `.ayder/notes/` (reusing the existing `notes.py` writer + `/notes` browser) and surfaces the path via a `note=` attribute — Task 1 (`note_path` field), new Task 2b (writer + wiring), Task 7 (capability line).

**Goal:** Deliver each sub-agent's final deliverable into the main conversation and wake the main LLM as soon as it's ready — no head-of-line blocking, no stale/competing turns, with a single turn arbiter enforcing one turn at a time.

**Architecture:** A single serial **`TurnEngine`** (one consumer task) owns turn execution: requests carry a `prepare` callback (state mutation) + `run_loop` flag; the engine runs one `ChatLoop.run()` at a time and **awaits each turn's teardown before starting the next**, so an interrupting request can never overlap the cancelled turn on the shared `chat_loop`/`callbacks`/`messages`. A small pure **`WakeDebouncer`** coalesces agent completions into one delayed wake (gated by "is a turn running?"). Agents return their **final assistant message** (the deliverable, conforming to a caller-specified structure), injected as a **user-role** labeled block (path-only when oversized). A per-dispatch `cycle_id` rejects results from a replaced conversation. Each run is also persisted to `.ayder/notes/`.

**Revision 5** addresses the fourth review (`.ayder/020-codex-multi-agent-review.md`, rev-4 re-review): the lease-based arbiter fixed *bookkeeping* but not the physical overlap of two `ChatLoop.run()`s under Textual's non-awaiting `exclusive=True`. Rev. 5 replaces it with the serial `TurnEngine` + a **command-transition API** (`SOFT` / `INTERRUPT_AND_RUN` / `INTERRUPT_AND_MUTATE`) so breaking commands mutate state only when quiescent (F1/F2); in-place `self.messages[:]` so `chat_loop.messages` stays connected (F3); the engine's `try/finally` subsumes the lease rollback (F4); a corrected cycle-invalidation map (`/load-context` appends → no bump; `apply_pending_compact` is in `tui/app.py`) (F5); `json.dumps` YAML scalars (F6); and a real async serialization lifecycle test (F7). Product decision: provider/model switches are `INTERRUPT_AND_MUTATE` (cancel the turn, apply the runtime change when quiescent, start no new turn). Earlier-review fixes (final-message payload, user-role injection, oversized hard-cap, notes collision/escaping, error classification, result-before-user ordering, optional-note wording) carry forward from rev. 4.

**Tech Stack:** Python 3.12, Pydantic v2, Textual TUI, asyncio, pytest (+ `anyio`), ruff, mypy.

## Global Constraints

- Target Python **3.12**. All changes pass `uv run poe check-all` **and** `uv run poe test-all` (the latter is required because `poe test` ignores `tests/core/test_config.py` — `pyproject.toml:72`).
- Async tests use `@pytest.mark.anyio` (see `tests/loops/test_chat_loop_hook.py`).
- Injected results use **`role: "user"`** (NOT `system`) — provider-neutral; Claude/Gemini hoist system messages into the master prompt (`claude.py:170-171`, `gemini.py:176-177`).
- **Payload = final assistant message only**, captured from conversation history, **never the raw transcript/context**. Injected in full unless it exceeds `agent_result_inline_limit` (F10), in which case a **path-only** block points at the always-written note. The main LLM validates the requested structure and treats a non-conforming result as failed (prompt-level contract, not code).
- **I1 (single turn) via the serial engine:** one `_turn_engine()` consumer runs exactly one `ChatLoop.run()` at a time. Every turn and every runtime mutation goes through `request_turn(...)`. An interrupt cancels the active `_run_task`; the engine **`await`s its teardown** before processing the next request — no overlap on shared `chat_loop`/`callbacks`/`messages` (F1/F2).
- **Quiescent mutation (F2):** breaking commands defer their state change into a `prepare` callback that the engine runs **only when no turn is executing**. Command transitions: `SOFT` (no `request_turn`), `INTERRUPT_AND_RUN` (`/ask`,`/plan`,`/compact`,`/implement`,`/skill`), `INTERRUPT_AND_MUTATE` (`/provider`,`/model` — `run_loop=False`, no new turn). User *text* queues (never interrupts); agent wakes never interrupt.
- **Engine + debouncer always constructed** (F3), independent of an agent registry, so coordination holds in the no-agent case.
- **Non-cancellable tool side effects:** a turn cancelled while inside `asyncio.to_thread` cannot stop the thread; its result is discarded (the loop has unwound) and does not re-enter the conversation. Documented, not prevented.
- **Failure handling (F4):** the engine's `try/finally` always clears `_run_task` and runs `_finish_turn`; a `prepare` failure is reported and the request is skipped. The `WakeDebouncer` rolls back to `IDLE` on schedule failure.
- **Error classification (F8):** terminal status is `error` whenever `callbacks.last_system_error` is set — independent of cumulative `last_content`.
- **Cycle invalidation (F5)** is centralized in `AyderApp._new_conversation_cycle()` and called from every conversation-replacement path (`/clear`, `/compact`, `apply_pending_compact`, skill, load-context, provider/model switch).
- **Notes (F6/F7):** non-overwriting (exclusive create + numeric suffix, unique across restarts) and YAML-safe (quoted/escaped scalars).
- **I2 (exactly once):** every in-cycle result injected exactly once.
- **I3 (no head-of-line block):** a completion triggers delivery regardless of other running agents.
- **I4 (order):** results inject in FIFO enqueue order (≈ completion order; not physical model finish time).
- **Stale safety:** pending wakes are cancelled and stale results dropped on cancel, `/clear`, and conversation replacement (via timer generation + `cycle_id`).
- **User preempts:** user input or a slash command during the debounce window cancels the pending wake and runs immediately; pending results are consumed by that turn's pre-iteration drain.
- **Scope:** this phase wires push delivery into the **TUI (`AyderApp`) only**. The single-shot CLI path (`cli_runner.py:56-67`) keeps its current behavior; a note is added there. **Model-callable agent cancellation is the next phase** — not in this plan.
- **Agent notes (`2026-06-18-agent-notes-design.md`):** the runner persists each agent's final message to `.ayder/notes/` for **every** terminal status, using a collision-proof filename `{YYYYMMDD-HHMMSS}-{agent-slug}-run{run_id}.md`, and surfaces the project-relative path via a `note=` attribute on the injected block. Note writing is **best-effort** — a failure logs and sets `note_path=None`, never failing the agent run. Retention/cleanup is out of scope (gitignored scratch).

---

## File Structure

- `src/ayder_cli/agents/summary.py` — `AgentSummary` → `AgentResult` (`run_id`, `cycle_id`, `agent_name`, `status`, `content`, `error`, `note_path`); `format_for_injection` renders a delimiter-safe labeled block with an optional `note=` attribute.
- `src/ayder_cli/agents/__init__.py` — export rename.
- `src/ayder_cli/agents/runner.py` — capture the **final assistant message** from history; drop `_parse_summary`; build `AgentResult`; persist the message via `write_agent_note` and set `note_path`.
- `src/ayder_cli/tools/builtins/notes.py` — extract a shared `_write_note`; add `write_agent_note` (collision-proof filename, best-effort, all statuses).
- `src/ayder_cli/agents/registry.py` — rename queue/methods to `_result_queue` / `drain_results` / `has_pending_results`; add `cycle_id` tracking (`new_cycle()`, stamp at dispatch, drop stale before enqueue); push-semantics capability prompt.
- `src/ayder_cli/application/runtime_factory.py` — replace summary suffix with a final-message/structure contract.
- `src/ayder_cli/core/config.py` — add `agent_wake_debounce_ms` + `agent_result_inline_limit`.
- `src/ayder_cli/agents/wake_debouncer.py` — **new** `WakeDebouncer` (pure; coalesces agent completions into one delayed wake).
- `src/ayder_cli/tui/app.py` — **new** serial `TurnEngine` (`_requests`/`_run_task`/`_turn_engine`/`request_turn`/`_finish_turn`/`is_turn_running`); `WakeDebouncer` wiring; user-role + cycle-filtered `inject_agent_results`; in-place `inject_skill`; `_new_conversation_cycle`; `action_cancel` cancels the active `_run_task`.
- `src/ayder_cli/tui/commands.py` — command-transition API: breaking commands defer state mutation into `prepare` + `interrupt=True`; `/provider`,`/model` use `run_loop=False`; correct cycle-bump sites.
- Tests: `tests/agents/test_summary.py`, `tests/agents/test_runner.py`, `tests/agents/test_registry.py`, `tests/agents/test_wake_debouncer.py` (new), `tests/application/test_runtime_factory.py`, `tests/core/test_agent_wake_config.py` (new, **non-ignored** name), `tests/ui/test_agent_wake_injection.py` (new), `tests/providers/test_agent_result_roundtrip.py` (new), `tests/tui/test_agent_wake_integration.py` (new, async lifecycle), `tests/tools/test_agent_notes.py` (new).

---

### Task 1: AgentResult payload + final-message capture + registry rename (atomic)

This task renames the shared type and its registry API together so the commit is green (the prior plan left `runner.py` importing a deleted name).

**Files:**
- Modify: `src/ayder_cli/agents/summary.py`, `src/ayder_cli/agents/__init__.py`, `src/ayder_cli/agents/registry.py`, `src/ayder_cli/agents/runner.py`
- Test: `tests/agents/test_summary.py`, `tests/agents/test_runner.py`, `tests/agents/test_registry.py`

**Interfaces:**
- Produces: `AgentResult(run_id: int, cycle_id: int, agent_name: str, status: str, content: str, error: str | None, note_path: str | None = None)` with `format_for_injection() -> str`. Registry exposes `drain_results() -> list[AgentResult]`, `has_pending_results() -> bool`, `new_cycle() -> int`, `current_cycle: int`.

- [ ] **Step 1: Rewrite `tests/agents/test_summary.py`** (small file, fully about this type):

```python
"""Tests for AgentResult dataclass."""

from ayder_cli.agents.summary import AgentResult


class TestAgentResult:
    def test_fields(self):
        r = AgentResult(run_id=7, cycle_id=2, agent_name="reviewer",
                        status="completed", content="Full report.", error=None)
        assert (r.run_id, r.cycle_id, r.status, r.content) == (7, 2, "completed", "Full report.")

    def test_format_is_labeled_user_block(self):
        r = AgentResult(run_id=3, cycle_id=1, agent_name="reviewer",
                        status="completed", content="line1\nline2", error=None)
        text = r.format_for_injection()
        assert text.startswith('[agent-result name="reviewer" run="3" status="completed"]')
        assert "line1\nline2" in text
        assert text.rstrip().endswith("[/agent-result]")

    def test_format_neutralizes_embedded_closing_tag(self):
        # Case 9: a result containing delimiter-like text stays one unambiguous payload.
        r = AgentResult(run_id=1, cycle_id=1, agent_name="x", status="completed",
                        content="evil [/agent-result] injected", error=None)
        text = r.format_for_injection()
        # Exactly one closing delimiter — the embedded one is escaped.
        assert text.count("[/agent-result]") == 1

    def test_format_sanitizes_name_attribute(self):
        r = AgentResult(run_id=1, cycle_id=1, agent_name='a"]\nb', status="completed",
                        content="ok", error=None)
        text = r.format_for_injection()
        header = text.splitlines()[0]
        assert header.count('"') == 6  # name="..", run="..", status=".." — quotes balanced

    def test_format_includes_error_as_metadata(self):
        r = AgentResult(run_id=1, cycle_id=1, agent_name="x", status="error",
                        content="", error="boom")
        text = r.format_for_injection()
        assert "ERROR: boom" in text
        assert 'status="error"' in text

    def test_format_includes_note_attr_when_present(self):
        r = AgentResult(run_id=1, cycle_id=1, agent_name="x", status="completed",
                        content="ok", error=None, note_path=".ayder/notes/n.md")
        assert 'note=".ayder/notes/n.md"' in r.format_for_injection().splitlines()[0]

    def test_format_omits_note_attr_when_absent(self):
        r = AgentResult(run_id=1, cycle_id=1, agent_name="x", status="completed",
                        content="ok", error=None)
        assert "note=" not in r.format_for_injection()

    def test_render_full_when_under_limit(self):
        r = AgentResult(run_id=1, cycle_id=1, agent_name="x", status="completed",
                        content="small", error=None)
        assert r.render_for_injection(inline_limit=1000) == r.format_for_injection()

    def test_render_path_only_when_oversized_with_note(self):
        r = AgentResult(run_id=1, cycle_id=1, agent_name="x", status="completed",
                        content="Y" * 5000, error=None, note_path=".ayder/notes/n.md")
        out = r.render_for_injection(inline_limit=1000)
        assert 'truncated="true"' in out
        assert 'note=".ayder/notes/n.md"' in out
        assert "Y" * 5000 not in out

    def test_render_preview_when_oversized_without_note(self):
        r = AgentResult(run_id=1, cycle_id=1, agent_name="x", status="completed",
                        content="Z" * 5000, error=None)
        out = r.render_for_injection(inline_limit=100)
        assert "note unavailable" in out
        assert out.count("Z") == 100        # bounded preview only
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/agents/test_summary.py -v`
Expected: FAIL — `ImportError: cannot import name 'AgentResult'`.

- [ ] **Step 3: Rewrite `src/ayder_cli/agents/summary.py`**

```python
"""AgentResult — the final deliverable of a single agent run.

The agent returns exactly what the dispatching task requested (summary,
report, or full document). Only the agent's FINAL message is captured — never
the intermediate transcript — and it is injected verbatim (not truncated) as a
labeled user-role block. (Formerly AgentSummary.)
"""

from dataclasses import dataclass


def _sanitize_attr(value: str) -> str:
    """Make a string safe to embed inside a double-quoted block attribute."""
    return value.replace("\\", "\\\\").replace('"', "'").replace("\n", " ").replace("\r", " ")


@dataclass
class AgentResult:
    """The final result of a single agent dispatch."""

    run_id: int
    cycle_id: int
    agent_name: str
    status: str          # "completed" | "timeout" | "error"
    content: str         # the agent's FINAL message, verbatim, never truncated
    error: str | None    # error/timeout metadata, separate from content
    note_path: str | None = None  # project-relative path of the persisted note, if written

    def format_for_injection(self) -> str:
        """Render as a delimiter-safe labeled block (injected as role=user)."""
        note_attr = f' note="{_sanitize_attr(self.note_path)}"' if self.note_path else ""
        header = (
            f'[agent-result name="{_sanitize_attr(self.agent_name)}" '
            f'run="{self.run_id}" status="{_sanitize_attr(self.status)}"{note_attr}]'
        )
        # Neutralize any embedded closing delimiter so the block stays unambiguous.
        body = (self.content or "").replace("[/agent-result]", "[/agent-result ]")
        if self.error:
            body = f"{body}\nERROR: {self.error}" if body else f"ERROR: {self.error}"
        return f"{header}\n{body}\n[/agent-result]"

    def render_for_injection(self, inline_limit: int | None = None) -> str:
        """Full block, or a path-only block when content exceeds inline_limit (F10).

        Over the limit with a note -> path-only (the note holds the full copy).
        Over the limit with no note -> bounded preview + notice. Otherwise full.
        """
        if inline_limit is None or len(self.content or "") <= inline_limit:
            return self.format_for_injection()
        note_attr = f' note="{_sanitize_attr(self.note_path)}"' if self.note_path else ""
        header = (
            f'[agent-result name="{_sanitize_attr(self.agent_name)}" '
            f'run="{self.run_id}" status="{_sanitize_attr(self.status)}" '
            f'truncated="true"{note_attr}]'
        )
        n = len(self.content or "")
        if self.note_path:
            body = f"Result too large to inline ({n} chars). Read the full deliverable from the note path above."
        else:
            preview = (self.content or "")[:inline_limit].replace("[/agent-result]", "[/agent-result ]")
            body = f"Result too large ({n} chars); note unavailable. Preview:\n{preview}"
        if self.error:
            body += f"\nERROR: {self.error}"
        return f"{header}\n{body}\n[/agent-result]"
```

- [ ] **Step 4: Update `src/ayder_cli/agents/__init__.py`** — change the import and `__all__` entry from `AgentSummary` to `AgentResult`.

- [ ] **Step 5: Edit `src/ayder_cli/agents/registry.py`** (rename API + cycle tracking)

5a. Import: `from ayder_cli.agents.summary import AgentResult`.

5b. In `__init__`, rename the queue and add cycle state:
```python
        self._result_queue: asyncio.Queue[AgentResult] = asyncio.Queue()
        self._current_cycle: int = 0
```
Replace `on_complete: Callable[[int, AgentSummary], None]` and `result: AgentSummary | None` hints with `AgentResult`.

5c. Add cycle accessors (near `reset_settled`):
```python
    @property
    def current_cycle(self) -> int:
        return self._current_cycle

    def new_cycle(self) -> int:
        """Bump the dispatch cycle. Call when the conversation is replaced
        (clear/load/provider switch) or cancelled, so in-flight agents' results
        are recognised as stale and dropped before injection."""
        self._current_cycle += 1
        return self._current_cycle
```

5d. In `dispatch`, stamp the cycle on the runner and pass it through. After `run_id = self._run_counter`, capture `cycle = self._current_cycle` and pass `cycle_id=cycle` to `AgentRunner(...)` (Task 1 Step 7 adds the param). In `_run_and_queue`, drop stale results before enqueue:
```python
                result = await runner.run(task)
                if result.cycle_id == self._current_cycle:
                    await self._result_queue.put(result)
                else:
                    logger.debug("dropping stale agent result: run_id=%d cycle=%d current=%d",
                                 run_id, result.cycle_id, self._current_cycle)
```

5e. Rename `drain_summaries` → `drain_results`, `has_pending_summaries` → `has_pending_results`, updating the queue references (`self._result_queue`) and docstrings.

- [ ] **Step 6: Edit `src/ayder_cli/agents/runner.py`** (final-message capture)

6a. Import `AgentResult`; remove `_SUMMARY_PATTERN`, `import re`, and the `_parse_summary` method.

6b. Add `cycle_id: int = 0` to `__init__` params and store `self._cycle_id = cycle_id`.

6c. Add a final-message extractor:
```python
    @staticmethod
    def _final_message(messages: list[dict]) -> str:
        """Return the last assistant message with real text content.

        ChatLoop appends each iteration's final content as an assistant message
        (chat_loop.py:344-350) and ends on a text-only iteration, so the last
        such message is the agent's deliverable. Pure <think> blocks and
        tool-only (empty-content) messages are skipped.
        """
        for msg in reversed(messages):
            if msg.get("role") != "assistant":
                continue
            content = (msg.get("content") or "").strip()
            if not content:
                continue
            if content.startswith("<think>") and content.endswith("</think>"):
                continue
            return msg.get("content") or ""
        return ""
```

6d. Change `run` signature to `-> AgentResult`. Keep the `messages` list local (already built). After `await asyncio.wait_for(chat_loop.run(), ...)` extract `content = self._final_message(messages)`. Return `AgentResult` in each branch with `run_id=self.run_id, cycle_id=self._cycle_id`:
- timeout: `status="timeout"`, `content=self._final_message(messages) or "Agent timed out before producing output."`, `error=f"Agent exceeded {self._timeout}s timeout"`.
- **error (F8): `if callbacks.last_system_error:`** → `status="error"`, `content=self._final_message(messages)` (the partial deliverable, if any), `error=callbacks.last_system_error`.
- success (no system error): `status="completed"`, `content=content or "Agent completed without producing output."`, `error=None`.
- exception: `status="error"`, `content="Agent encountered an error."`, `error=str(e)`.

**F8:** terminal status is `"error"` whenever `callbacks.last_system_error` is set — the old `and not callbacks.last_content.strip()` guard is **dropped**. `last_content` is cumulative, so a late stream failure *after* earlier tool-call text would otherwise be misclassified as `completed`. (`last_content` is no longer consulted for classification at all.)

- [ ] **Step 7: Write the runner test** — append to `tests/agents/test_runner.py`:

```python
import pytest
from unittest.mock import MagicMock, patch

from ayder_cli.agents.config import AgentConfig
from ayder_cli.agents.runner import AgentRunner


@pytest.mark.anyio
async def test_runner_returns_final_message_not_transcript():
    """Intermediate tool-call chatter is excluded; only the final message is returned."""
    cfg = AgentConfig(name="reporter", system_prompt="Write a report.")
    runner = AgentRunner(
        agent_config=cfg, parent_config=MagicMock(), project_ctx=MagicMock(),
        process_manager=MagicMock(), permissions=set(), timeout=5,
        run_id=42, cycle_id=3,
    )

    fake_rt = MagicMock()
    fake_rt.system_prompt = "sys"
    fake_rt.config = MagicMock(model="m", provider="p", num_ctx=1, max_output_tokens=1,
                               stop_sequences=[], tool_tags=None, max_history_messages=30)

    def loop_ctor(**kwargs):
        msgs = kwargs["messages"]
        m = MagicMock()

        async def _run(*a, **k):
            # Emulate ChatLoop: intermediate assistant text, a tool round, then the final report.
            msgs.append({"role": "assistant", "content": "Let me check the files."})
            msgs.append({"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]})
            msgs.append({"role": "tool", "content": "file contents"})
            msgs.append({"role": "assistant", "content": "# Final Report\nAll done."})

        m.run = _run
        return m

    import ayder_cli.agents.runner as runner_mod
    with patch.object(runner_mod, "create_agent_runtime", return_value=fake_rt), \
         patch.object(runner_mod, "ChatLoop", side_effect=loop_ctor):
        result = await runner.run("Write the report")

    assert result.run_id == 42 and result.cycle_id == 3
    assert result.status == "completed"
    assert result.content == "# Final Report\nAll done."
    assert "Let me check the files." not in result.content


@pytest.mark.anyio
async def test_runner_reports_error_when_stream_fails_after_tool_text():
    """F8: a late stream error after earlier assistant text => status 'error', not 'completed'."""
    cfg = AgentConfig(name="x", system_prompt="s")
    runner = AgentRunner(
        agent_config=cfg, parent_config=MagicMock(), project_ctx=MagicMock(),
        process_manager=MagicMock(), permissions=set(), timeout=5, run_id=1, cycle_id=1,
    )
    fake_rt = MagicMock()
    fake_rt.system_prompt = "sys"
    fake_rt.config = MagicMock(model="m", provider="p", num_ctx=1, max_output_tokens=1,
                               stop_sequences=[], tool_tags=None, max_history_messages=30)

    def loop_ctor(**kwargs):
        cb = kwargs["callbacks"]
        msgs = kwargs["messages"]
        m = MagicMock()

        async def _run(*a, **k):
            msgs.append({"role": "assistant", "content": "intermediate text"})
            cb.last_content = "intermediate text"          # cumulative, non-empty
            cb.last_system_error = "Error: stream failed"  # late failure

        m.run = _run
        return m

    import ayder_cli.agents.runner as runner_mod
    with patch.object(runner_mod, "create_agent_runtime", return_value=fake_rt), \
         patch.object(runner_mod, "ChatLoop", side_effect=loop_ctor):
        result = await runner.run("t")

    assert result.status == "error"                        # NOT "completed"
    assert result.error == "Error: stream failed"
```

- [ ] **Step 8: Run the suite to verify pass + no regressions**

Run: `uv run pytest tests/agents/ -v`
Expected: PASS. Update any existing test still referencing `AgentSummary` / `.summary` / `drain_summaries` to the new names.

- [ ] **Step 9: Commit**

```bash
git add src/ayder_cli/agents/summary.py src/ayder_cli/agents/__init__.py src/ayder_cli/agents/registry.py src/ayder_cli/agents/runner.py tests/agents/
git commit -m "refactor(agents): AgentResult final-message payload + cycle_id + result-queue rename"
```

---

### Task 2: Agent prompt — final-message / structure contract

**Files:**
- Modify: `src/ayder_cli/application/runtime_factory.py:179-194`
- Test: `tests/application/test_runtime_factory.py`

**Interfaces:**
- Produces: agent `system_prompt = identity_prefix + agent_config.system_prompt + tool_prompts + final_message_contract` (no `<agent-summary>` block).

- [ ] **Step 1: Write the failing test** — append to `tests/application/test_runtime_factory.py`:

```python
from unittest.mock import MagicMock, patch

from ayder_cli.agents.config import AgentConfig
from ayder_cli.application import runtime_factory


def test_agent_prompt_uses_final_message_contract_not_summary_block():
    agent_cfg = AgentConfig(name="reporter", system_prompt="Produce a document.")
    parent = MagicMock(provider="ollama", tool_tags=None, retry=MagicMock(enabled=False))
    fake_reg = MagicMock()
    fake_reg.get_system_prompts.return_value = "\n[tools]\n"
    fake_reg.get_schemas.return_value = []

    with patch.object(runtime_factory.provider_orchestrator, "create", return_value=MagicMock()), \
         patch.object(runtime_factory.context_manager_factory, "create", return_value=MagicMock()), \
         patch.object(runtime_factory, "create_default_registry", return_value=fake_reg):
        rt = runtime_factory.create_agent_runtime(
            agent_config=agent_cfg, parent_config=parent,
            project_ctx=MagicMock(), process_manager=MagicMock(), permissions=set(),
        )

    assert "Produce a document." in rt.system_prompt
    assert "<agent-summary>" not in rt.system_prompt
    assert "FINDINGS:" not in rt.system_prompt
    assert "final message" in rt.system_prompt.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/application/test_runtime_factory.py::test_agent_prompt_uses_final_message_contract_not_summary_block -v`
Expected: FAIL — `<agent-summary>` still present.

- [ ] **Step 3: Edit `src/ayder_cli/application/runtime_factory.py`**

Replace the `summary_suffix = (...)` block (lines ~183-191) with:
```python
    final_message_contract = (
        "\n\n---\n"
        "Put your COMPLETE deliverable in your FINAL message, formatted exactly "
        "as the task requests. Only your final message is returned to the caller "
        "— intermediate messages and tool output are not. Do not truncate the "
        "deliverable and do not add a separate summary."
    )
```
and change the assembly (line ~194) to:
```python
    system_prompt = identity_prefix + agent_config.system_prompt + tool_prompts + final_message_contract
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/application/test_runtime_factory.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/application/runtime_factory.py tests/application/test_runtime_factory.py
git commit -m "feat(agents): final-message/structure contract replaces forced summary suffix"
```

---

### Task 2b: Agent deliverable notes — `write_agent_note` + runner wiring

Persists each agent's final message to `.ayder/notes/` and sets `AgentResult.note_path`. Depends on Task 1 (`AgentResult.note_path`, `AgentRunner._final_message`, `self._cycle_id`). Spec: `docs/superpowers/specs/2026-06-18-agent-notes-design.md`. Reuses the existing `notes.py` writer (`_get_notes_dir`, `_title_to_slug`) and the existing `/notes` browser (no command change).

**Files:**
- Modify: `src/ayder_cli/tools/builtins/notes.py` (add `import logging`; extract `_write_note`; add `write_agent_note`)
- Modify: `src/ayder_cli/agents/runner.py` (add `_persist_note`; set `note_path` in each return branch)
- Test: `tests/tools/test_agent_notes.py` (new), `tests/agents/test_runner.py`

**Interfaces:**
- Consumes: `ProjectContext` (`.root`, `.to_relative`), existing `_get_notes_dir` / `_title_to_slug` (`notes.py`), `AgentResult` (Task 1).
- Produces: `write_agent_note(project_ctx, *, agent_name: str, run_id: int, cycle_id: int, status: str, task: str, content: str, timestamp: str, error: str | None = None) -> str | None` — project-relative note path, or `None` on write failure. The `timestamp` is `"YYYYMMDD-HHMMSS"`, passed in (no hidden clock).

- [ ] **Step 1: Write the failing test** — create `tests/tools/test_agent_notes.py`:

```python
"""Tests for write_agent_note — deterministic agent deliverable notes."""

from ayder_cli.core.context import ProjectContext
from ayder_cli.tools.builtins.notes import write_agent_note


def test_writes_note_with_frontmatter_and_sections(tmp_path):
    ctx = ProjectContext(str(tmp_path))
    rel = write_agent_note(
        ctx, agent_name="reviewer", run_id=3, cycle_id=1, status="completed",
        task="Review the auth module", content="# Findings\nAll good.",
        timestamp="20260618-143022",
    )
    assert rel == ".ayder/notes/20260618-143022-reviewer-run3.md"
    text = (tmp_path / rel).read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert 'agent: "reviewer"' in text and "run_id: 3" in text and 'status: "completed"' in text
    assert "tags: [agent-result]" in text
    assert "## Task\nReview the auth module" in text
    assert "## Result\n# Findings\nAll good." in text


def test_error_status_appends_error_section(tmp_path):
    ctx = ProjectContext(str(tmp_path))
    rel = write_agent_note(
        ctx, agent_name="writer", run_id=1, cycle_id=2, status="error",
        task="t", content="partial", timestamp="20260618-090000", error="boom",
    )
    text = (tmp_path / rel).read_text(encoding="utf-8")
    assert 'status: "error"' in text
    assert "## Error\nboom" in text


def test_same_run_does_not_overwrite(tmp_path):
    # F6: identical timestamp + agent + run_id (e.g. across app restarts) must not overwrite.
    ctx = ProjectContext(str(tmp_path))
    a = write_agent_note(ctx, agent_name="x", run_id=1, cycle_id=1, status="completed",
                         task="t", content="FIRST", timestamp="20260618-120000")
    b = write_agent_note(ctx, agent_name="x", run_id=1, cycle_id=1, status="completed",
                         task="t", content="SECOND", timestamp="20260618-120000")
    assert a != b
    assert (tmp_path / a).read_text().endswith("FIRST\n")
    assert (tmp_path / b).read_text().endswith("SECOND\n")


def test_frontmatter_escapes_unsafe_agent_name(tmp_path):
    # F6/F7: quotes/colons/newlines/tabs/controls must not corrupt or inject frontmatter keys.
    ctx = ProjectContext(str(tmp_path))
    rel = write_agent_note(ctx, agent_name='weird:\t"name"\ninjected: true',
                           run_id=1, cycle_id=1, status="completed",
                           task="t", content="c", timestamp="20260618-120000")
    text = (tmp_path / rel).read_text(encoding="utf-8")
    frontmatter = text.split("---", 2)[1]
    assert "\ninjected: true" not in frontmatter      # the newline did NOT create a new key
    assert "\t" not in frontmatter                    # the tab was escaped, not embedded raw
    assert 'agent: "weird:' in frontmatter            # one quoted scalar


def test_write_failure_returns_none(tmp_path, monkeypatch):
    ctx = ProjectContext(str(tmp_path))
    import ayder_cli.tools.builtins.notes as notes_mod

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(notes_mod, "_write_note", boom)
    rel = write_agent_note(ctx, agent_name="x", run_id=1, cycle_id=1, status="completed",
                           task="t", content="c", timestamp="20260618-120000")
    assert rel is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/test_agent_notes.py -v`
Expected: FAIL — `ImportError: cannot import name 'write_agent_note'`.

- [ ] **Step 3: Edit `src/ayder_cli/tools/builtins/notes.py`**

3a. Add at the top (after the existing imports): `import logging` and `logger = logging.getLogger(__name__)`.

3b. Add a shared writer and the agent-note function (after `_title_to_slug`):

```python
def _yaml_scalar(value: object) -> str:
    """Render a value as a safely double-quoted YAML scalar (F6/F7).

    json.dumps emits a double-quoted string that escapes quotes, backslashes,
    newlines, tabs, and other control characters — and a JSON string is a valid
    YAML 1.2 flow scalar. (Replaces the hand-rolled escaper, which missed tabs.)
    """
    import json
    return json.dumps(str(value), ensure_ascii=False)


def _write_note(
    notes_dir: Path, filename: str, frontmatter: list[str], body: str, *, exclusive: bool = False
) -> Path:
    """Write YAML frontmatter + body. When ``exclusive``, never overwrite an
    existing file — append a numeric suffix on collision (F6). Returns the path.
    """
    notes_dir.mkdir(parents=True, exist_ok=True)
    content = "\n".join(["---", *frontmatter, "---"]) + f"\n\n{body}\n"
    if not exclusive:
        path = notes_dir / filename
        path.write_text(content, encoding="utf-8")
        return path
    stem = filename[:-3] if filename.endswith(".md") else filename
    candidate = notes_dir / f"{stem}.md"
    n = 2
    while True:
        try:
            with open(candidate, "x", encoding="utf-8") as f:   # exclusive create — no overwrite
                f.write(content)
            return candidate
        except FileExistsError:
            candidate = notes_dir / f"{stem}-{n}.md"
            n += 1


def write_agent_note(
    project_ctx: ProjectContext,
    *,
    agent_name: str,
    run_id: int,
    cycle_id: int,
    status: str,
    task: str,
    content: str,
    timestamp: str,
    error: str | None = None,
) -> str | None:
    """Persist an agent's final deliverable to .ayder/notes/. Best-effort.

    Non-overwriting (unique across app/registry restarts, F6) and YAML-safe (F7).
    Returns the project-relative note path, or None if writing fails (a note
    failure must never fail the agent run).
    """
    try:
        notes_dir = _get_notes_dir(project_ctx)
        slug = _title_to_slug(agent_name)
        filename = f"{timestamp}-{slug}-run{run_id}.md"
        frontmatter = [
            f"title: {_yaml_scalar(f'{agent_name} run {run_id}')}",
            f"date: {_yaml_scalar(timestamp)}",
            f"agent: {_yaml_scalar(agent_name)}",
            f"run_id: {run_id}",      # int — safe unquoted
            f"cycle_id: {cycle_id}",  # int — safe unquoted
            f"status: {_yaml_scalar(status)}",
            "tags: [agent-result]",
        ]
        body = f"## Task\n{task}\n\n## Result\n{content}"
        if error:
            body += f"\n\n## Error\n{error}"
        path = _write_note(notes_dir, filename, frontmatter, body, exclusive=True)
        return project_ctx.to_relative(path)
    except Exception as e:
        logger.warning("write_agent_note failed for agent '%s' run %d: %s", agent_name, run_id, e)
        return None
```

3c. (DRY, optional but recommended) Refactor `create_note` to use `_write_note`: replace its inline `frontmatter_lines = ["---", ...]` / `note_content = "\n".join(...)` / `path.write_text(...)` with:
```python
        frontmatter = [f'title: "{title}"', f"date: {now}"]
        if tag_list:
            frontmatter.append(f"tags: [{', '.join(tag_list)}]")
        path = _write_note(notes_dir, filename, frontmatter, content)
```
The byte output is identical (frontmatter delimiters + `\n\n{content}\n`), so existing `create_note` tests stay green.

- [ ] **Step 4: Run tests to verify pass (incl. existing notes tests)**

Run: `uv run pytest tests/tools/test_agent_notes.py tests/tools/ -k note -v`
Expected: PASS — `write_agent_note` tests pass and any existing `create_note` test still passes.

- [ ] **Step 5: Wire the runner — edit `src/ayder_cli/agents/runner.py`**

5a. Add a best-effort note helper (alongside `_final_message`):
```python
    def _persist_note(self, task: str, status: str, content: str, error: str | None) -> str | None:
        from datetime import datetime
        from ayder_cli.tools.builtins.notes import write_agent_note
        return write_agent_note(
            self._project_ctx,
            agent_name=self.agent_name,
            run_id=self.run_id,
            cycle_id=self._cycle_id,
            status=status,
            task=task,
            content=content,
            timestamp=datetime.now().strftime("%Y%m%d-%H%M%S"),
            error=error,
        )
```

5b. In each terminal branch of `run`, compute `note_path` from the SAME values used to build the `AgentResult`, and pass it through. For example, the success branch becomes:
```python
            content = content or "Agent completed without producing output."
            note_path = self._persist_note(task, "completed", content, None)
            return AgentResult(
                run_id=self.run_id, cycle_id=self._cycle_id, agent_name=self.agent_name,
                status="completed", content=content, error=None, note_path=note_path,
            )
```
Do the same in the timeout branch (`status="timeout"`, `error=f"Agent exceeded {self._timeout}s timeout"`), the **F8 error branch** (`if callbacks.last_system_error:` → `status="error"`, `content=self._final_message(messages)` — the partial deliverable, not `""` — `error=callbacks.last_system_error`), and the `except` branch (`status="error"`, `content="Agent encountered an error."`, `error=str(e)`). Each passes its own `content`/`status`/`error` to both `_persist_note` and `AgentResult(note_path=...)`.

- [ ] **Step 6: Write the runner note test** — append to `tests/agents/test_runner.py`:

```python
@pytest.mark.anyio
async def test_runner_persists_note_and_sets_path(tmp_path):
    from ayder_cli.core.context import ProjectContext
    cfg = AgentConfig(name="reporter", system_prompt="Write a report.")
    ctx = ProjectContext(str(tmp_path))
    runner = AgentRunner(
        agent_config=cfg, parent_config=MagicMock(), project_ctx=ctx,
        process_manager=MagicMock(), permissions=set(), timeout=5, run_id=7, cycle_id=1,
    )
    fake_rt = MagicMock()
    fake_rt.system_prompt = "sys"
    fake_rt.config = MagicMock(model="m", provider="p", num_ctx=1, max_output_tokens=1,
                               stop_sequences=[], tool_tags=None, max_history_messages=30)

    def loop_ctor(**kwargs):
        msgs = kwargs["messages"]
        m = MagicMock()

        async def _run(*a, **k):
            msgs.append({"role": "assistant", "content": "# Deliverable\nbody"})

        m.run = _run
        return m

    import ayder_cli.agents.runner as runner_mod
    from unittest.mock import patch
    with patch.object(runner_mod, "create_agent_runtime", return_value=fake_rt), \
         patch.object(runner_mod, "ChatLoop", side_effect=loop_ctor):
        result = await runner.run("Do the task")

    assert result.note_path is not None
    note_file = tmp_path / result.note_path
    assert note_file.exists()
    text = note_file.read_text(encoding="utf-8")
    assert "# Deliverable\nbody" in text
    assert "## Task\nDo the task" in text
```

- [ ] **Step 7: Run the runner + notes suites**

Run: `uv run pytest tests/agents/test_runner.py tests/tools/test_agent_notes.py -v`
Expected: PASS. (The Task 1 runner test `test_runner_returns_final_message_not_transcript` still passes — its `MagicMock` project_ctx makes `write_agent_note` fail internally and return `None`, leaving `content` untouched.)

- [ ] **Step 8: Commit**

```bash
git add src/ayder_cli/tools/builtins/notes.py src/ayder_cli/agents/runner.py tests/tools/test_agent_notes.py tests/agents/test_runner.py
git commit -m "feat(agents): persist each agent's final deliverable as a .ayder/notes note"
```

---

### Task 3: Config — `agent_wake_debounce_ms` (non-ignored test module)

**Files:**
- Modify: `src/ayder_cli/core/config.py` (field ~289, validator ~393)
- Test: `tests/core/test_agent_wake_config.py` (**new file** — `tests/core/test_config.py` is ignored by `poe test`, `pyproject.toml:72`)

**Interfaces:**
- Produces: `Config.agent_wake_debounce_ms: int` (default `200`, range `0..5000`).

- [ ] **Step 1: Write the failing test** — create `tests/core/test_agent_wake_config.py`:

```python
"""Tests for Config.agent_wake_debounce_ms (kept out of the ignored test_config.py)."""

import pytest

from ayder_cli.core.config import Config


def test_default():
    assert Config().agent_wake_debounce_ms == 200


def test_rejects_negative():
    with pytest.raises(ValueError):
        Config(agent_wake_debounce_ms=-1)


def test_rejects_too_large():
    with pytest.raises(ValueError):
        Config(agent_wake_debounce_ms=99999)


def test_inline_limit_default():
    assert Config().agent_result_inline_limit == 24000


def test_inline_limit_rejects_negative():
    with pytest.raises(ValueError):
        Config(agent_result_inline_limit=-1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/core/test_agent_wake_config.py -v`
Expected: FAIL — field/validator missing.

- [ ] **Step 3: Edit `src/ayder_cli/core/config.py`**

After `agent_timeout` (line ~289):
```python
    agent_wake_debounce_ms: int = Field(default=200)
    agent_result_inline_limit: int = Field(default=24000)  # F10: chars before path-only injection
```
Alongside `validate_agent_timeout` (line ~393):
```python
    @field_validator("agent_wake_debounce_ms")
    @classmethod
    def validate_agent_wake_debounce_ms(cls, v: int) -> int:
        if v < 0 or v > 5000:
            raise ValueError("agent_wake_debounce_ms must be between 0 and 5000")
        return v

    @field_validator("agent_result_inline_limit")
    @classmethod
    def validate_agent_result_inline_limit(cls, v: int) -> int:
        if v < 0:
            raise ValueError("agent_result_inline_limit must be >= 0")
        return v
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/core/test_agent_wake_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/core/config.py tests/core/test_agent_wake_config.py
git commit -m "feat(config): add agent_wake_debounce_ms (default 200ms)"
```

---

### Task 4: Provider round-trip — user-role block survives at the completion point

Locks F5: a `user` block stays an ordered conversation turn on every adapter (unlike `system`, which Claude/Gemini hoist).

**Files:**
- Test: `tests/providers/test_agent_result_roundtrip.py` (new)

**Interfaces:**
- Consumes: `AgentResult.format_for_injection` (Task 1), `ClaudeAdapter._convert_messages`, `GeminiAdapter._convert_messages`.

- [ ] **Step 1: Write the test** — create `tests/providers/test_agent_result_roundtrip.py`:

```python
"""Case 10: an agent-result user block converts to an ordered user turn, not system."""

from ayder_cli.agents.summary import AgentResult


def _msgs():
    block = AgentResult(run_id=1, cycle_id=1, agent_name="reviewer",
                        status="completed", content="THE-DELIVERABLE", error=None).format_for_injection()
    return [
        {"role": "system", "content": "BASE-SYSTEM"},
        {"role": "user", "content": "do the thing"},
        {"role": "user", "content": block},   # injected agent result
    ]


def test_claude_keeps_result_in_message_history_not_system():
    from ayder_cli.providers.impl.claude import ClaudeAdapter
    system_prompt, messages = ClaudeAdapter._convert_messages(_msgs())
    assert "THE-DELIVERABLE" not in system_prompt          # not hoisted to system authority
    assert any("THE-DELIVERABLE" in str(m.get("content")) for m in messages)
    assert messages[-1]["role"] == "user"                  # appears at completion point


def test_gemini_keeps_result_in_message_history_not_system():
    from ayder_cli.providers.impl.gemini import GeminiAdapter
    system_prompt, messages = GeminiAdapter._convert_messages(_msgs())
    assert "THE-DELIVERABLE" not in system_prompt
    assert any("THE-DELIVERABLE" in str(m) for m in messages)
```

(If `_convert_messages` is an instance method, instantiate the adapter with a `MagicMock` config per the existing provider tests; check `tests/providers/` for the constructor pattern and mirror it.)

- [ ] **Step 2: Run test to verify it passes (behavior already correct for user role)**

Run: `uv run pytest tests/providers/test_agent_result_roundtrip.py -v`
Expected: PASS — confirms the chosen role is provider-neutral. (If it FAILS, that is a real provider bug to fix before proceeding.)

- [ ] **Step 3: Commit**

```bash
git add tests/providers/test_agent_result_roundtrip.py
git commit -m "test(providers): agent-result user block stays an ordered turn (Claude/Gemini)"
```

---

### Task 5: WakeDebouncer — coalesce agent completions

> **Rev. 5 change (re-review v4, F1/F2/F4):** the lease-based `TurnArbiter` is replaced by two pieces — this small **`WakeDebouncer`** (coalescing only) and the **`TurnEngine`** (Task 6, a single serial consumer that owns turn execution). Serialization is now *structural* (one engine awaits each turn's teardown before the next), so the lease, `begin_turn`/`end_turn`, and the `RUNNING` state are gone, and the F4 rollback collapses into the engine's `try/finally`.

**Files:**
- Create: `src/ayder_cli/agents/wake_debouncer.py`
- Test: `tests/agents/test_wake_debouncer.py`

**Interfaces:**
- Produces: `WakeDebouncer(*, is_running: Callable[[], bool], has_pending: Callable[[], bool], fire: Callable[[], None], schedule: Callable[[float, Callable[[], None]], object], cancel_timer: Callable[[object], None], debounce_s: float)`.
  - `request_wake() -> None`: on agent completion / post-turn re-check. Schedules ONE debounced wake when `IDLE` **and** not running **and** pending; further calls during the window coalesce.
  - On timer expiry: if still not running, calls `fire()` (the app drains ready results and enqueues a turn if any). If a turn started during the window, it does nothing (the running turn drains pending results via its pre-iteration hook).
  - `cancel() -> None`: drop the pending wake.
  - `state -> str` (`"idle"|"debouncing"`).
  - It does **not** run, serialize, or own turns. No lease, no `RUNNING` state. Schedule failures roll back to `IDLE`.

- [ ] **Step 1: Write the failing tests** — create `tests/agents/test_wake_debouncer.py`:

```python
"""Tests for WakeDebouncer — coalescing agent completions into one delayed wake."""

import pytest

from ayder_cli.agents.wake_debouncer import WakeDebouncer


class Harness:
    def __init__(self, debounce_s=0.2, pending=1, running=False, schedule_raises=False):
        self.pending = pending
        self.running = running
        self.fired = 0
        self.timers = []
        self._schedule_raises = schedule_raises
        self.wd = WakeDebouncer(
            is_running=lambda: self.running,
            has_pending=lambda: self.pending > 0,
            fire=self._fire,
            schedule=self._schedule,
            cancel_timer=self._cancel_timer,
            debounce_s=debounce_s,
        )

    def _fire(self):
        self.fired += 1

    def _schedule(self, delay, cb):
        if self._schedule_raises:
            raise RuntimeError("schedule failed")
        h = {"delay": delay, "cb": cb, "alive": True}
        self.timers.append(h)
        return h

    def _cancel_timer(self, h):
        h["alive"] = False

    def fire_last_timer(self):
        h = self.timers[-1]
        if h["alive"]:
            h["cb"]()


def test_idle_pending_schedules_one_wake():
    h = Harness(pending=2)
    h.wd.request_wake()
    assert h.wd.state == "debouncing"
    assert h.timers[-1]["delay"] == 0.2
    h.fire_last_timer()
    assert h.fired == 1


def test_coalesces_multiple_completions():
    h = Harness(pending=1)
    h.wd.request_wake()
    h.pending = 3
    h.wd.request_wake()
    h.wd.request_wake()
    assert len(h.timers) == 1                  # one timer for the whole burst
    h.fire_last_timer()
    assert h.fired == 1


def test_no_wake_while_running():
    h = Harness(pending=1, running=True)
    h.wd.request_wake()
    assert h.timers == []                      # the running turn drains pending results itself


def test_no_wake_without_pending():
    h = Harness(pending=0)
    h.wd.request_wake()
    assert h.timers == []


def test_turn_started_during_debounce_suppresses_fire():
    h = Harness(pending=1)
    h.wd.request_wake()
    h.running = True                           # a turn started during the window
    h.fire_last_timer()
    assert h.fired == 0                        # running turn will drain instead
    assert h.wd.state == "idle"


def test_cancel_drops_pending_wake():
    h = Harness(pending=1)
    h.wd.request_wake()
    h.wd.cancel()
    assert h.wd.state == "idle"
    h.fire_last_timer()                        # stale
    assert h.fired == 0


def test_schedule_failure_rolls_back_to_idle():
    h = Harness(pending=1, schedule_raises=True)
    with pytest.raises(RuntimeError):
        h.wd.request_wake()
    assert h.wd.state == "idle"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/agents/test_wake_debouncer.py -v`
Expected: FAIL — `ModuleNotFoundError: ...wake_debouncer`.

- [ ] **Step 3: Create `src/ayder_cli/agents/wake_debouncer.py`**

```python
"""WakeDebouncer — coalesces agent completions into a single delayed wake.

It does NOT run or serialize turns (the TurnEngine owns execution). When agents
complete while the main LLM is idle, it waits a short debounce window, then
fires once so near-simultaneous completions are delivered together. While a turn
is running it stays out of the way — the running turn drains pending results via
its pre-iteration hook.

Pure: all side effects are injected callables; unit-testable without Textual.
"""

from __future__ import annotations

from typing import Callable


class WakeDebouncer:
    IDLE = "idle"
    DEBOUNCING = "debouncing"

    def __init__(
        self,
        *,
        is_running: Callable[[], bool],
        has_pending: Callable[[], bool],
        fire: Callable[[], None],
        schedule: Callable[[float, Callable[[], None]], object],
        cancel_timer: Callable[[object], None],
        debounce_s: float,
    ) -> None:
        self._is_running = is_running
        self._has_pending = has_pending
        self._fire = fire
        self._schedule = schedule
        self._cancel_timer = cancel_timer
        self._debounce_s = debounce_s
        self._state = self.IDLE
        self._timer: object | None = None
        self._gen = 0

    @property
    def state(self) -> str:
        return self._state

    def request_wake(self) -> None:
        if self._state == self.DEBOUNCING:
            return                          # already armed — coalesce
        if self._is_running():
            return                          # running turn drains pending results itself
        if not self._has_pending():
            return
        self._state = self.DEBOUNCING
        self._gen += 1
        gen = self._gen
        try:
            self._timer = self._schedule(self._debounce_s, lambda: self._on_timer(gen))
        except Exception:
            self._timer = None
            self._state = self.IDLE         # rollback on schedule failure
            raise

    def _on_timer(self, gen: int) -> None:
        if gen != self._gen or self._state != self.DEBOUNCING:
            return                          # stale / cancelled
        self._timer = None
        self._state = self.IDLE
        if not self._is_running():
            self._fire()                    # app: drain ready results + enqueue a turn if any

    def cancel(self) -> None:
        self._gen += 1                      # invalidate any in-flight timer callback
        if self._timer is not None:
            try:
                self._cancel_timer(self._timer)
            except Exception:
                pass
            self._timer = None
        self._state = self.IDLE
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/agents/test_wake_debouncer.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/agents/wake_debouncer.py tests/agents/test_wake_debouncer.py
git commit -m "feat(agents): WakeDebouncer — coalesce agent completions into one delayed wake"
```

---

### Task 6: TurnEngine — serialized turn execution + command-transition API

> **Rev. 5 (re-review v4, F1/F2/F3/F5):** replaces the Textual `exclusive=True` worker model with a single serial **TurnEngine**. Only one `ChatLoop.run()` ever executes; an interrupting request cancels the current run and the engine **awaits its teardown before starting the next**, eliminating overlap on the shared `self.chat_loop`/`self._callbacks`/`self.messages`. Breaking commands defer their state mutation into a `prepare` callback that runs only while the engine is quiescent (F2).

**Files:**
- Modify: `src/ayder_cli/tui/app.py` (TurnEngine: `_requests`/`_run_task`/`_turn_engine`/`request_turn`/`_finish_turn`/`is_turn_running`; `WakeDebouncer` wiring + `_fire_agent_wake`; `inject_agent_results`; `_new_conversation_cycle`; `_process_next_message`; `handle_input_submitted`; `_agent_complete`; `action_cancel`; `inject_skill` in-place; start the engine in `on_mount`)
- Modify: `src/ayder_cli/tui/commands.py` (command-transition API — breaking commands defer mutation into `prepare` + `interrupt=True`; `/provider`,`/model` use `run_loop=False`; cycle bumps in the right places)
- Test: `tests/ui/test_agent_wake_injection.py` (new). (Lifecycle/interrupt + F3 identity tests live in Task 8.)

**Interfaces:**
- Consumes: `WakeDebouncer` (Task 5), `AgentResult.render_for_injection` (Task 1), `Config.agent_wake_debounce_ms`/`agent_result_inline_limit` (Task 3), `registry.drain_results()/has_pending_results()/current_cycle/new_cycle()`.
- Produces:
  - `inject_agent_results(registry, messages, inline_limit=None) -> int`.
  - `TurnRequest(prepare: Callable[[], None] | None = None, no_tools: bool = False, run_loop: bool = True)`.
  - `AyderApp.request_turn(prepare=None, *, no_tools=False, run_loop=True, interrupt=False) -> None` — the SINGLE entry for every turn and every runtime mutation under one.
  - `AyderApp.is_turn_running -> bool`; `_fire_agent_wake() -> None`; `_new_conversation_cycle() -> None`.
  - **Command transition policies:** `SOFT` (no `request_turn`), `INTERRUPT_AND_RUN` (`prepare` + `interrupt=True`), `INTERRUPT_AND_MUTATE` (`run_loop=False` + `interrupt=True`).

- [ ] **Step 1: Write the failing injection test** — create `tests/ui/test_agent_wake_injection.py`:

```python
"""Tests for inject_agent_results — user-role blocks, order, cycle filter, oversized cap."""

from ayder_cli.tui.app import inject_agent_results
from ayder_cli.agents.summary import AgentResult


class FakeRegistry:
    def __init__(self, results, current_cycle=1):
        self._results = list(results)
        self.current_cycle = current_cycle

    def drain_results(self):
        out, self._results = self._results, []
        return out


def test_injects_user_role_block():
    reg = FakeRegistry([AgentResult(1, 1, "reviewer", "completed", "Full report.", None)])
    messages = []
    assert inject_agent_results(reg, messages) == 1
    assert messages[0]["role"] == "user"           # NOT system (F5)
    assert '[agent-result name="reviewer" run="1" status="completed"]' in messages[0]["content"]
    assert "Full report." in messages[0]["content"]


def test_preserves_completion_order():
    reg = FakeRegistry([
        AgentResult(1, 1, "a", "completed", "first", None),
        AgentResult(2, 1, "b", "completed", "second", None),
    ])
    messages = []
    inject_agent_results(reg, messages)
    assert "first" in messages[0]["content"] and "second" in messages[1]["content"]


def test_drops_stale_cycle_results():
    reg = FakeRegistry(
        [AgentResult(1, 1, "old", "completed", "STALE", None),
         AgentResult(2, 2, "new", "completed", "FRESH", None)],
        current_cycle=2,
    )
    messages = []
    n = inject_agent_results(reg, messages)
    assert n == 1
    assert "FRESH" in messages[0]["content"]
    assert all("STALE" not in m["content"] for m in messages)


def test_oversized_result_injects_path_only(tmp_path):
    big = "X" * 5000
    reg = FakeRegistry([AgentResult(1, 1, "r", "completed", big, None,
                                    note_path=".ayder/notes/n.md")])
    messages = []
    inject_agent_results(reg, messages, inline_limit=1000)
    block = messages[0]["content"]
    assert 'truncated="true"' in block
    assert 'note=".ayder/notes/n.md"' in block
    assert big not in block
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/ui/test_agent_wake_injection.py -v`
Expected: FAIL — `ImportError: cannot import name 'inject_agent_results'`.

- [ ] **Step 3: app.py imports + module-level `TurnRequest` + `inject_agent_results`** (near line 31, and replacing the old `_wake_for_pending_agents`):

```python
import asyncio
from dataclasses import dataclass
from collections.abc import Callable

from ayder_cli.agents.wake_debouncer import WakeDebouncer


@dataclass
class TurnRequest:
    prepare: Callable[[], None] | None = None
    no_tools: bool = False
    run_loop: bool = True               # False => runtime mutation only (no chat loop)


def inject_agent_results(registry, messages: list[dict], inline_limit: int | None = None) -> int:
    """Drain ready agent results, drop stale-cycle ones, append each as a user block.

    FIFO order; role 'user' so every provider adapter keeps it at the completion
    point. Oversized results render path-only via render_for_injection (F10).
    """
    injected = 0
    for r in registry.drain_results():
        if r.cycle_id != registry.current_cycle:
            continue
        messages.append({"role": "user", "content": r.render_for_injection(inline_limit)})
        injected += 1
    return injected
```

- [ ] **Step 4: Add the TurnEngine to `AyderApp`** (the serial consumer — the F1/F2 fix):

```python
    # in __init__:
    self._requests: asyncio.Queue = asyncio.Queue()
    self._run_task: asyncio.Task | None = None
    self._engine_task: asyncio.Task | None = None

    @property
    def is_turn_running(self) -> bool:
        return self._run_task is not None

    async def _turn_engine(self) -> None:
        """Single serial consumer of turn requests. Guarantees one ChatLoop.run()
        at a time and AWAITS each turn's teardown before starting the next."""
        while True:
            req = await self._requests.get()
            try:
                if req.prepare is not None:
                    req.prepare()              # F2: mutate messages/runtime ONLY while quiescent
            except Exception as e:
                self._report_turn_error(e)
                continue
            if not req.run_loop:
                continue                       # runtime mutation only (provider/model switch)
            self._run_task = asyncio.create_task(self.chat_loop.run(no_tools=req.no_tools))
            try:
                await self._run_task           # <-- the serialized wait; teardown completes here
            except asyncio.CancelledError:
                pass                           # interrupted by a later request
            except Exception as e:
                self._report_turn_error(e)
            finally:
                self._run_task = None
                self._finish_turn()

    def request_turn(self, prepare=None, *, no_tools: bool = False,
                     run_loop: bool = True, interrupt: bool = False) -> None:
        """The single entry for starting a turn or mutating runtime under one."""
        self._requests.put_nowait(TurnRequest(prepare, no_tools, run_loop))
        if interrupt and self._run_task is not None:
            self._run_task.cancel()            # engine awaits teardown, THEN processes this request

    def _finish_turn(self) -> None:
        try:
            self._maybe_stop_activity_timer()
            self.query_one("#activity-bar", ActivityBar).clear()
            self.query_one("#input-bar", CLIInputBar).focus_input()
        except Exception:
            pass
        if self._pending_messages:
            self._process_next_message()       # queued user input
        elif self._agent_registry:
            self._debouncer.request_wake()     # re-check stragglers

    def _report_turn_error(self, exc: Exception) -> None:
        try:
            self.query_one("#chat-view", ChatView).add_system_message(f"Error: {exc}")
        except Exception:
            pass
```

- [ ] **Step 5: Construct the WakeDebouncer (always) + the fire callback** — in `__init__`:

```python
        debounce_ms = getattr(self.config, "agent_wake_debounce_ms", 200)
        self._debouncer = WakeDebouncer(
            is_running=lambda: self.is_turn_running,
            has_pending=lambda: bool(self._agent_registry) and self._agent_registry.has_pending_results(),
            fire=self._fire_agent_wake,
            schedule=lambda delay, cb: self.set_timer(delay, cb),
            cancel_timer=lambda h: h.stop(),
            debounce_s=debounce_ms / 1000.0,
        )
```
and the methods:
```python
    def _result_inline_limit(self) -> int:
        return getattr(self.config, "agent_result_inline_limit", 24000)

    def _fire_agent_wake(self) -> None:
        """Debouncer fired while idle: drain ready results, enqueue a turn if any (F6: skip if empty)."""
        if not self._agent_registry:
            return
        n = inject_agent_results(self._agent_registry, self.messages, self._result_inline_limit())
        if n > 0:
            self.request_turn()                # run a turn over the freshly injected results
```

- [ ] **Step 6: Start the engine in `on_mount`** (event loop is running there):
```python
        self._engine_task = asyncio.create_task(self._turn_engine())
```
Also delete any `self._is_processing = ...` init and add a compatibility property:
```python
    @property
    def _is_processing(self) -> bool:
        return self.is_turn_running
```

- [ ] **Step 7: User input path — `handle_input_submitted` + `_process_next_message`** (F9 ordering inside `prepare`):
```python
        # handle_input_submitted (after appending to _pending_messages):
        if not self.is_turn_running:
            self._process_next_message()

    def _process_next_message(self) -> None:
        if not self._pending_messages:
            return
        text = self._pending_messages.pop(0)

        def _prepare(text=text):
            try:
                self.query_one("#chat-view", ChatView).add_user_message(text)
            except Exception:
                pass
            if self._agent_registry:           # F9: results (context) BEFORE the user instruction
                inject_agent_results(self._agent_registry, self.messages, self._result_inline_limit())
            self.messages.append({"role": "user", "content": text})

        self.request_turn(prepare=_prepare, no_tools=False)
```

- [ ] **Step 8: `_agent_complete` → debouncer**:
```python
            def _agent_complete(run_id, result):
                try:
                    panel = self.query_one("#agent-panel", AgentPanel)
                    self.call_later(lambda: panel.complete_agent(run_id, result.content, result.status))
                except Exception:
                    pass
                try:
                    activity = self.query_one("#activity-bar", ActivityBar)
                    count = self._agent_registry.active_count if self._agent_registry else 0
                    self.call_later(lambda: activity.set_agents_running(count))
                except Exception:
                    pass
                self._debouncer.request_wake()
```

- [ ] **Step 9: `action_cancel` + `_new_conversation_cycle`**:
```python
    # action_cancel — replace the worker-cancel/_is_processing lines with:
        if self._run_task is not None:
            self._run_task.cancel()            # cancel the active turn (engine awaits its teardown)
        self._debouncer.cancel()
        self._pending_messages.clear()
        self._new_conversation_cycle()

    def _new_conversation_cycle(self) -> None:
        """Invalidate in-flight agent results when the conversation is REPLACED
        (clear / compact / skill / provider or model switch). A prior-cycle result
        cannot then inject into the new conversation.
        """
        if self._agent_registry:
            self._agent_registry.new_cycle()
            self._agent_registry.drain_results()
```

- [ ] **Step 10: Fix `inject_skill` to mutate in place (F3)** — `src/ayder_cli/tui/app.py:427`:
```python
        # was: self.messages = [ ... ]
        self.messages[:] = [ ... ]             # in-place — keeps chat_loop.messages connected
```
(The identity test `app.chat_loop.messages is app.messages` lives in Task 8.)

- [ ] **Step 11: Command-transition API** — `src/ayder_cli/tui/commands.py`. Breaking commands stop mutating inline + calling `start_llm_processing`; they defer the mutation into `prepare` and pass `interrupt=True`.

`INTERRUPT_AND_RUN` example — `handle_ask`:
```python
def handle_ask(app, args, chat_view):
    q = args.strip()
    if not q:
        chat_view.add_system_message("Usage: /ask <question>")
        return

    def _prepare():
        app.messages.append({"role": "user", "content": q})
        chat_view.add_user_message(q)

    app.request_turn(prepare=_prepare, no_tools=True, interrupt=True)
```

`INTERRUPT_AND_RUN` with conversation reset — `handle_compact`:
```python
def handle_compact(app, args, chat_view):
    def _prepare():
        # ... existing surgery: build conversation_text, clear, append compact_prompt ...
        app._new_conversation_cycle()          # invalidate in-flight agent results
        chat_view.add_system_message("Compacting: summarize → save → clear → load")

    app.request_turn(prepare=_prepare, no_tools=False, interrupt=True)
```

`INTERRUPT_AND_MUTATE` — `handle_provider` (and `handle_model`): cancel the turn, apply runtime change when quiescent, start NO new turn:
```python
def handle_provider(app, args, chat_view):
    # ... resolve target provider (or open the selection screen; its callback uses this same path) ...
    def _prepare():
        app._apply_provider(target)            # rebuild llm/chat_loop/system prompt;
                                               # MUST keep chat_loop.messages is app.messages (mutate in place)
        app._new_conversation_cycle()
        chat_view.add_system_message(f"Provider → {target}")

    app.request_turn(prepare=_prepare, run_loop=False, interrupt=True)
```

Apply the matching shape to the rest:

| Command | Policy | Notes |
|---------|--------|-------|
| `/ask`, `/plan`, `/implement` | INTERRUPT_AND_RUN | defer the prompt append into `prepare` |
| `/skill <name> <cmd>` | INTERRUPT_AND_RUN | `prepare` does the in-place skill replacement (Step 10) + `_new_conversation_cycle()` |
| `/compact` | INTERRUPT_AND_RUN | `prepare` does message surgery + `_new_conversation_cycle()` |
| `/provider`, `/model` (incl. selection-screen callbacks) | INTERRUPT_AND_MUTATE | `run_loop=False`; rebuild runtime in `prepare` + `_new_conversation_cycle()` |
| `/clear` (`do_clear`) | — | in-place `app.messages.clear()` + `_new_conversation_cycle()`; if a turn runs, `app._run_task.cancel()` |
| `/load-context` | SOFT-append | **APPENDS** a user message (`commands.py:886`) → **NO** cycle bump (prior-cycle results stay valid) |
| `/notes`, `/tasks`, `/permission`, `/save-context` | SOFT | no `request_turn`, no cycle bump |

- [ ] **Step 12: Corrected cycle-invalidation map (F5)** — `apply_pending_compact` is in **`src/ayder_cli/tui/app.py:808`** (not `application/`); after it reconstructs history, call `self._new_conversation_cycle()`. Confirm the only cycle-bump sites are: `action_cancel`, `do_clear`, `handle_compact`, `apply_pending_compact`, `handle_skill`, `handle_provider`, `handle_model` (and the provider/model selection-screen callbacks). **`/load-context` must NOT bump** (append semantics).

- [ ] **Step 13: Run the injection + agent + tui regressions**

Run: `uv run pytest tests/ui/ tests/tui/ tests/agents/ -v`
Expected: PASS. Update any test referencing `_wake_for_pending_agents`, `.summary`, `_is_processing` writes, or `start_llm_processing`.

- [ ] **Step 14: Commit**

```bash
git add src/ayder_cli/tui/app.py src/ayder_cli/tui/commands.py tests/ui/test_agent_wake_injection.py
git commit -m "feat(tui): serial TurnEngine + command-transition API; user-role injection; cycle invalidation"
```

---

### Task 7: Capability prompt — push semantics + structure contract + "as soon as"

**Files:**
- Modify: `src/ayder_cli/agents/registry.py:99-119` (`get_capability_prompts`)
- Test: `tests/agents/test_registry.py`

- [ ] **Step 1: Update the test** — replace `test_get_capability_prompts` in `tests/agents/test_registry.py`:

```python
    def test_get_capability_prompts_push_and_structure(self, registry):
        p = registry.get_capability_prompts()
        assert "list_agents" in p and "call_agent" in p
        assert "reviewer" not in p and "writer" not in p
        assert "[agent-result]" in p                       # delivery format named
        assert "after all agents complete" not in p        # no batch language
        assert "Batch behavior" not in p
        assert "structure" in p.lower()                    # caller specifies structure
        assert "note=" in p                                # note path is referenced
        assert "best-effort" in p.lower()                  # F11: path is optional, not promised
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/agents/test_registry.py -k capability -v`
Expected: FAIL — batch language present / no structure language.

- [ ] **Step 3: Edit `get_capability_prompts`** — replace the `lines = [...]` block:

```python
        lines = [
            "\n## Agent Delegation",
            "",
            "Configured specialized agents may be available.",
            "Use `list_agents` to discover exact names/descriptions before `call_agent`.",
            "Each agent runs in the background with its own LLM and tools.",
            "",
            "**Specify the structure you need.** In the task, state the exact output "
            "structure/format the agent must return. The agent returns ONLY its final "
            "message. When the result arrives, verify it matches the requested structure; "
            "if it does not, treat that dispatch as failed and handle the work yourself.",
            "",
            "**Delivery (push):** each agent's final result arrives as an `[agent-result]` "
            "block as soon as that agent finishes (within a short coalescing window, or at "
            "the next safe step of your current turn) — you may receive them one at a time. "
            "Act on each as it arrives; do NOT wait for all agents.",
            "",
            "Each `[agent-result]` block MAY carry a `note=\"…\"` path to the agent's full "
            "saved deliverable (note writing is best-effort, so a block may have none). "
            "When a path is present and the deliverable has scrolled out of context, read "
            "that file with `read_file` instead of re-dispatching the agent.",
            "",
            "**Rules:**",
            "- You CAN dispatch the same agent multiple times with different tasks.",
            "- Only use the agent whose specialty matches the task.",
            "- On agent failure, handle the task yourself. Do NOT re-dispatch failed agents.",
        ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/agents/test_registry.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/agents/registry.py tests/agents/test_registry.py
git commit -m "docs(agents): capability prompt — push delivery + caller-specified structure contract"
```

---

### Task 8: TurnEngine lifecycle + wiring tests + CLI scope note

**Coverage split:** debounce coalescing is proven in `tests/agents/test_wake_debouncer.py` (Task 5); delimiter safety in `test_summary.py` (Task 1); provider role/order in `test_agent_result_roundtrip.py` (Task 4). **This task** proves the engine itself: (F7) a real async test that an interrupt is **serialized** — the cancelled turn fully exits before the replacement starts; (F3) skill replacement keeps `chat_loop.messages is app.messages`; (F9) results precede the user instruction; (F5) cycle reset purges. The app is constructed with `create_runtime` patched and `query_one`/`set_timer`/`call_later` stubbed; the engine is started manually and `chat_loop` swapped for a controllable fake.

**Files:**
- Test: `tests/tui/test_agent_wake_integration.py` (new)
- Modify: `src/ayder_cli/cli_runner.py` (comment only — document TUI-only push scope)

**Interfaces:**
- Consumes: `AyderApp` (`request_turn`, `_turn_engine`, `is_turn_running`, `_process_next_message`, `_new_conversation_cycle`, `inject_skill`), `AgentResult` (Task 1).

**Note on backend:** these async tests assume the asyncio anyio backend (`asyncio.create_task`/`Queue`). If the project's `anyio_backend` fixture also yields `trio`, restrict with `@pytest.mark.anyio` + an `anyio_backend` of `"asyncio"` for this module.

- [ ] **Step 1: Write the failing tests** — create `tests/tui/test_agent_wake_integration.py`:

```python
"""AyderApp TurnEngine lifecycle + wiring tests.

Debounce coalescing is proven in tests/agents/test_wake_debouncer.py. Here we
drive the REAL engine: serialization on interrupt (F7), skill list identity
(F3), result-before-user ordering (F9), and cycle invalidation (F5).
"""

import asyncio
import contextlib
from unittest.mock import MagicMock

import pytest

from ayder_cli.agents.summary import AgentResult


class FakeRegistry:
    def __init__(self):
        self._q = []
        self.current_cycle = 1
    def has_pending_results(self):
        return bool(self._q)
    def drain_results(self):
        out, self._q = self._q, []
        return out
    def new_cycle(self):
        self.current_cycle += 1
        return self.current_cycle
    def complete(self, result):
        self._q.append(result)


def _fake_rt():
    from ayder_cli.core.config import Config
    rt = MagicMock()
    rt.config = Config()                 # real config (defaults incl. inline_limit/debounce)
    rt.tool_registry.get_schemas.return_value = []
    rt.system_prompt = "system"
    return rt


def _build_app(monkeypatch):
    from ayder_cli.application import runtime_factory  # noqa: F401 (patched below)
    from ayder_cli.tui import app as app_mod
    monkeypatch.setattr(app_mod, "create_runtime", lambda **k: _fake_rt())
    app = app_mod.AyderApp()             # builds _requests, _debouncer; engine NOT started
    monkeypatch.setattr(app, "query_one", lambda *a, **k: MagicMock())
    monkeypatch.setattr(app, "call_later", lambda fn, *a, **k: fn(*a, **k))
    monkeypatch.setattr(app, "set_timer", lambda delay, cb: {"delay": delay, "cb": cb})
    return app


async def _drain_engine(app):
    app._engine_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await app._engine_task


@pytest.mark.anyio
async def test_interrupt_is_serialized(monkeypatch):
    # F7: the cancelled turn must FULLY exit before the replacement turn starts.
    app = _build_app(monkeypatch)
    order = []
    a_in = asyncio.Event()

    class FakeLoop:
        def __init__(self):
            self.messages = app.messages
        async def run(self, *, no_tools=False):
            if not a_in.is_set():
                a_in.set()
                order.append("A-start")
                try:
                    await asyncio.sleep(3600)      # block until cancelled
                finally:
                    order.append("A-exit")
            else:
                order.append("B-start")

    app.chat_loop = FakeLoop()
    app._engine_task = asyncio.create_task(app._turn_engine())
    app.request_turn()                             # turn A
    await asyncio.wait_for(a_in.wait(), 1)
    app.request_turn(interrupt=True)               # turn B interrupts A
    for _ in range(50):
        await asyncio.sleep(0)
        if order[-1:] == ["B-start"]:
            break
    assert order == ["A-start", "A-exit", "B-start"]   # A fully exits BEFORE B starts
    await _drain_engine(app)


def test_skill_replacement_keeps_chat_loop_messages_connected(monkeypatch):
    # F3: inject_skill must mutate in place so chat_loop keeps the same list.
    app = _build_app(monkeypatch)
    assert app.chat_loop.messages is app.messages      # connected at construction
    app.inject_skill("demo", "skill content")
    assert app.chat_loop.messages is app.messages      # STILL the same list (in-place)


@pytest.mark.anyio
async def test_results_precede_user_message_in_turn(monkeypatch):
    # F9: results (context) are injected before the user's instruction, inside the turn.
    app = _build_app(monkeypatch)
    reg = FakeRegistry()
    reg.complete(AgentResult(1, 1, "a", "completed", "RESULT-BODY", None))
    app._agent_registry = reg
    app.messages = []
    ran = asyncio.Event()

    class FakeLoop:
        def __init__(self):
            self.messages = app.messages
        async def run(self, *, no_tools=False):
            ran.set()

    app.chat_loop = FakeLoop()
    app._engine_task = asyncio.create_task(app._turn_engine())
    app._pending_messages = ["USER ASK"]
    app._process_next_message()                        # enqueues request_turn(prepare=inject+append)
    await asyncio.wait_for(ran.wait(), 1)
    assert "RESULT-BODY" in app.messages[0]["content"]
    assert app.messages[1] == {"role": "user", "content": "USER ASK"}
    await _drain_engine(app)


def test_new_conversation_cycle_invalidates_and_purges(monkeypatch):
    # F5: a conversation reset bumps the cycle and drops queued results.
    app = _build_app(monkeypatch)
    reg = FakeRegistry()
    reg.complete(AgentResult(1, 1, "a", "completed", "STALE", None))
    app._agent_registry = reg
    app._new_conversation_cycle()
    assert reg.current_cycle == 2
    assert reg.drain_results() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/tui/test_agent_wake_integration.py -v`
Expected: FAIL — engine/methods not yet implemented (Tasks 5/6). (If `AyderApp()` needs an extra `rt` attribute, set it in `_fake_rt`; the constructor reads `config`, `llm_provider`, `tool_registry`, `process_manager`, `project_ctx`, `system_prompt`, `context_manager` — all MagicMock-satisfiable except `config`, a real `Config()`.)

- [ ] **Step 3: Run after Tasks 5/6 are implemented**

Run: `uv run pytest tests/tui/test_agent_wake_integration.py -v`
Expected: PASS (4 tests).

- [ ] **Step 4: Document CLI scope** — add to `src/ayder_cli/cli_runner.py` near the agent-registry wiring (line ~56):
```python
        # NOTE: the TurnEngine/debouncer push model is a TUI concern. In single-shot
        # CLI mode the call_agent result is consumed by the same blocking run; if
        # interactive CLI gains background agents, lift the engine above this adapter.
```

- [ ] **Step 5: Commit**

```bash
git add tests/tui/test_agent_wake_integration.py src/ayder_cli/cli_runner.py
git commit -m "test(tui): engine serialization (F7) + skill identity (F3) + ordering/cycle; CLI scope note"
```

---

### Task 9: Full-suite verification

- [ ] **Step 1: Run both suites** (`check-all` alone does not cover the new config tests — `pyproject.toml:72`):

Run: `uv run poe check-all && uv run poe test-all`
Expected: ruff clean, mypy clean, all tests pass.

- [ ] **Step 2: Straggler grep** — confirm old names/gates are gone:

Run: `grep -rn "AgentSummary\|_parse_summary\|_wake_for_pending_agents\|drain_summaries\|has_pending_summaries\|active_count == 0\|active_count != 0\|self\._is_processing = " src/`
Expected: no matches (the `active_count` *property* for UI counts may remain; only the two gate comparisons and `_is_processing` *assignments* must be gone — reads via the property are fine).

- [ ] **Step 3: Commit any fixups**

```bash
git add -A && git commit -m "chore: full-suite green for agent-result push delivery"
```

---

## Self-Review

**1. Spec / review coverage**
- F1 single turn → serial `TurnEngine` (Task 6); every start goes through `request_turn`; `test_interrupt_is_serialized` (Task 8). ✓
- F2 stale finish on cancel/clear → engine awaits teardown; `action_cancel` cancels `_run_task`; `_new_conversation_cycle()` purges (Task 6). ✓
- F3 `last_content` ≠ final → Task 1 `_final_message` from history + runner test with tool-then-final. ✓
- F4 system authority → resolved by decision: user-role block + delimiter/name sanitization (Tasks 1/6). ✓
- F5 provider semantics → user role + Task 4 Claude/Gemini round-trip test. ✓
- F6 failure paths → engine `try/finally`; `_fire_agent_wake` skips when zero injected (Tasks 5/6). ✓
- F7 user priority → user text queues while `is_turn_running`; debouncer stays out while running (Task 5 `test_no_wake_while_running`, Task 6). ✓
- F8 tests → debouncer unit (Task 5) + Task 8 async lifecycle + Task 4 (provider) + Task 1 (delimiter). ✓
- cycle ownership → Task 1 `cycle_id` + registry `new_cycle`/stamp/drop; Task 6 filter + bump sites. ✓
- "as soon as" wording, completion-order semantics, error-as-metadata → Task 7 prompt + Task 1 format. ✓
- naming migration → Task 1 `drain_results`/`has_pending_results`/`_result_queue`. ✓
- ignored config test → Task 3 new module + Task 9 `test-all`. ✓
- `tests/tui/` regression → Task 6 Step 8/10 + Task 8. ✓
- green intermediate commits → Task 1 makes the rename atomic. ✓
- TUI-only scope → Task 8 Step 4 CLI note. ✓
- Agent cancellation → explicitly next phase (Global Constraints). ✓
- Agent notes (spec `2026-06-18-agent-notes-design.md`) → `AgentResult.note_path` + `format_for_injection` `note=` (Task 1); `write_agent_note` + `_write_note` extraction + runner `_persist_note` wiring (Task 2b); capability `note=` line (Task 7); best-effort, all statuses, never fails the run; reuses existing `/notes` browser. ✓

**Review v3 findings — carried into rev. 5:**
- F1/F2 single-turn / stale finish → now solved by the **serial `TurnEngine`** (awaits each turn's teardown before the next), which supersedes the lease. ✓
- F3 no-agent coordination → engine + debouncer always constructed (Task 6 Steps 4-6). ✓
- F4 failure handling → engine `try/finally` + debouncer schedule-rollback (Tasks 5/6). ✓
- F5 cycle invalidation → `_new_conversation_cycle()` (Task 6 Steps 9/12). ✓
- F6 note collisions → exclusive create + suffix (Task 2b). ✓
- F7 YAML safety → `json.dumps` scalars (Task 2b). ✓
- F8 error classification → `error` on `last_system_error` (Task 1). ✓
- F9 ordering → results before user message (Tasks 6/8). ✓
- F10 oversized → path-only cap (Tasks 1/3/6). ✓
- F11 optional note → prompt wording (Task 7). ✓

**Re-review v4 findings (rev. 5):**
- v4-F1 serialized interrupt → serial `TurnEngine` awaits teardown before replacement; `test_interrupt_is_serialized` (Task 8). ✓
- v4-F2 quiescent mutation → command-transition API; breaking commands mutate inside `prepare` (Task 6 Step 11). ✓
- v4-F3 skill list identity → in-place `self.messages[:]`; `test_skill_replacement_keeps_chat_loop_messages_connected` (Tasks 6/8). ✓
- v4-F4 worker-start rollback → dissolved by the single-consumer engine `try/finally` (no lease) (Task 6 Step 4). ✓
- v4-F5 cycle map → corrected: `/load-context` appends (no bump), `apply_pending_compact` in `tui/app.py` (Task 6 Step 12). ✓
- v4-F6 YAML tabs/controls → `json.dumps`; tab test (Task 2b). ✓
- v4-F7 lifecycle test → real async serialization test (Task 8). ✓
- Provider/model policy → `INTERRUPT_AND_MUTATE` (product decision). ✓

**2. Placeholder scan** — clean. Task 8 contains complete, runnable tests, incl. a real async serialization lifecycle test (engine started manually, `chat_loop` swapped for a controllable fake). No `...`.

**3. Type consistency** — `AgentResult(run_id, cycle_id, agent_name, status, content, error, note_path=None)` identical across Tasks 1/4/6/8; `render_for_injection(inline_limit=None)` (Task 1) consumed by `inject_agent_results(registry, messages, inline_limit=None) -> int` (Task 6); `write_agent_note(...) -> str | None` (Task 2b) → `AgentResult.note_path`; **`WakeDebouncer(*, is_running, has_pending, fire, schedule, cancel_timer, debounce_s)`** (Task 5) constructed in Task 6 Step 5; **`TurnRequest`** + **`request_turn(prepare=None, *, no_tools=False, run_loop=True, interrupt=False)`** + `is_turn_running` + `_turn_engine`/`_run_task`/`_finish_turn`/`_fire_agent_wake` (Task 6) used by the command-transition API (Step 11) and Task 8; `drain_results`/`has_pending_results`/`current_cycle`/`new_cycle` (Task 1) consumed Tasks 5/6/8; `_new_conversation_cycle()` defined Task 6 Step 9, called Steps 11-12.
