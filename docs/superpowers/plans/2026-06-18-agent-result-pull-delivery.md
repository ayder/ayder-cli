# Agent-Result Pull Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-06-18-agent-result-pull-delivery-design.md` (rev. 2). **Supersedes:** the push plan `2026-06-17-agent-result-push-delivery.md`.

**Goal:** Let the main LLM **pull** each agent's deliverable on its own schedule (`agent_status()` + `read_agent_result()`), nudged once when it leaves a result unread, with one serialized turn at a time — deleting the push-injection/wake/`cycle_id` layer.

**Architecture:** An agent dispatch becomes a stateful `AgentRun` record owned solely by the event loop. The LLM polls/drains it via two new tools; results never inject themselves (no second writer). A 1 s timer + completion/turn-finished events nudge the LLM when idle with an unread result. A single app-owned turn consumer replaces Textual's non-awaiting `exclusive=True` worker, eliminating the observed overlap. Done in two phases: **A** delivers pull on the existing worker turn-model; **B** swaps in the serial consumer.

**Tech Stack:** Python 3.12, Pydantic v2, Textual TUI, asyncio, pytest (+ `anyio`), ruff, mypy.

**rev. 2 — plan-review corrections:** (1) `read_result`/`await_run` only drain **terminal** runs (a working-run read leaves `drained=False`, so the later completion still nudges) + regression test; (2) full `commands.py` audit — *every* state-mutating command (and conversation *reads* in `/compact`/`/save-context`) defers into `prepare`; `/clear`,`/load-context`,`/tools`,`/permission` use `run_loop=False`; (3) `_on_loop` **raises** if the loop is unset and `list_agents` marshals; (4) Ctrl+C cancels only the active turn — **queued requests preserved** (single `_requests` queue replaces `_pending_messages`); (5) `reset_settled()` deferred into the user request's `prepare`; (6) Phase-A tests migrated off `_is_processing` assignment.

## Global Constraints

- Target Python **3.12**. Every task passes `uv run poe check-all` **and** `uv run poe test-all` (the latter is required — `poe test` ignores `tests/core/test_config.py`, `pyproject.toml:72`).
- Async tests use `@pytest.mark.anyio` (pattern: `tests/loops/test_chat_loop_hook.py`).
- **Registry state is owned solely by the event loop.** On-loop callers (`_run_and_queue`, the nudge timer, turn-finished) call registry methods directly; worker-thread tool handlers marshal via `run_coroutine_threadsafe(coro, loop).result(...)` (spec §4).
- Model-facing status is exactly `working | done | error` (timeout → `error` with a timeout message).
- `read_agent_result`'s `timeout_s` is validated and **capped to `[0, agent_timeout]`**; the blocking wait is not cancellable mid-wait (spec §5, finding B).
- Nudges are event-driven (completion + turn-finished) with the 1 s timer as a recovery fallback. `nudged` is distinct from `drained` and set **only after the wake turn is enqueued** (spec §7, finding A).
- A note is a durable **copy** of the agent's final message — never more than the model produced (spec §10, finding C).
- v1 interrupt policy = **queue**; **Ctrl+C** (`action_cancel`) cancels the active turn (spec §12).

## File Structure

- `src/ayder_cli/tools/builtins/notes.py` — add `_yaml_scalar`, `_write_note` (shared, collision-proof), `write_agent_note`.
- `src/ayder_cli/agents/runner.py` — `AgentRunOutcome`; `_final_message`; note persistence; drop `_parse_summary`/`_SUMMARY_PATTERN`; `run() -> AgentRunOutcome`.
- `src/ayder_cli/agents/run.py` — **new** `AgentRun` dataclass.
- `src/ayder_cli/agents/registry.py` — pull API + generation + single-loop ownership; delete summary-queue API.
- `src/ayder_cli/agents/summary.py` — **deleted** (replaced by `AgentRun`/`AgentRunOutcome`); `__init__.py` updated.
- `src/ayder_cli/agents/tool.py` — `agent_status` + `read_agent_result` tools; `call_agent` return change.
- `src/ayder_cli/application/runtime_factory.py:183-194` — deliverable directive replaces `summary_suffix`.
- `src/ayder_cli/tui/app.py` — delivery rewiring (Phase A); serial turn consumer (Phase B).
- `src/ayder_cli/tui/commands.py` — `new_generation()` call sites; command `prepare`-deferral (Phase B).
- `src/ayder_cli/cli_runner.py:64-67` — register the two pull tools.
- Tests: `tests/tools/test_agent_notes.py`, `tests/agents/test_runner.py`, `tests/agents/test_run.py`, `tests/agents/test_registry.py`, `tests/agents/test_agent_tools.py`, `tests/application/test_runtime_factory.py`, `tests/tui/test_pull_delivery.py`, `tests/tui/test_turn_consumer.py`.

---

# Phase A — Pull delivery on the existing turn model

### Task 1: `write_agent_note` — durable deliverable notes

**Files:**
- Modify: `src/ayder_cli/tools/builtins/notes.py`
- Test: `tests/tools/test_agent_notes.py` (new)

**Interfaces:**
- Produces: `write_agent_note(project_ctx, *, agent_name: str, run_id: int, generation: int, status: str, task: str, content: str, timestamp: str, error: str | None = None) -> str | None` (project-relative path, or `None` on write failure); `_write_note(notes_dir, filename, frontmatter: list[str], body, *, exclusive=False) -> Path`.

- [ ] **Step 1: Write the failing tests** — create `tests/tools/test_agent_notes.py`:

```python
"""Tests for write_agent_note — durable, deterministic agent deliverable notes."""

from ayder_cli.core.context import ProjectContext
from ayder_cli.tools.builtins.notes import write_agent_note


def test_writes_note_with_frontmatter_and_sections(tmp_path):
    ctx = ProjectContext(str(tmp_path))
    rel = write_agent_note(
        ctx, agent_name="reviewer", run_id=3, generation=1, status="done",
        task="Review the auth module", content="# Findings\nAll good.",
        timestamp="20260618-143022",
    )
    assert rel == ".ayder/notes/20260618-143022-reviewer-run3.md"
    text = (tmp_path / rel).read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert 'agent: "reviewer"' in text and "run_id: 3" in text and 'status: "done"' in text
    assert "tags: [agent-result]" in text
    assert "## Task\nReview the auth module" in text
    assert "## Result\n# Findings\nAll good." in text


def test_error_status_appends_error_section(tmp_path):
    ctx = ProjectContext(str(tmp_path))
    rel = write_agent_note(
        ctx, agent_name="writer", run_id=1, generation=2, status="error",
        task="t", content="partial", timestamp="20260618-090000", error="boom",
    )
    text = (tmp_path / rel).read_text(encoding="utf-8")
    assert 'status: "error"' in text
    assert "## Error\nboom" in text


def test_same_run_does_not_overwrite(tmp_path):
    ctx = ProjectContext(str(tmp_path))
    a = write_agent_note(ctx, agent_name="x", run_id=1, generation=1, status="done",
                         task="t", content="FIRST", timestamp="20260618-120000")
    b = write_agent_note(ctx, agent_name="x", run_id=1, generation=1, status="done",
                         task="t", content="SECOND", timestamp="20260618-120000")
    assert a != b
    assert (tmp_path / a).read_text().endswith("FIRST\n")
    assert (tmp_path / b).read_text().endswith("SECOND\n")


def test_frontmatter_escapes_unsafe_agent_name(tmp_path):
    ctx = ProjectContext(str(tmp_path))
    rel = write_agent_note(ctx, agent_name='weird:\t"name"\ninjected: true',
                           run_id=1, generation=1, status="done",
                           task="t", content="c", timestamp="20260618-120000")
    frontmatter = (tmp_path / rel).read_text(encoding="utf-8").split("---", 2)[1]
    assert "\ninjected: true" not in frontmatter   # newline did not create a new key
    assert "\t" not in frontmatter                 # tab escaped, not embedded
    assert 'agent: "weird:' in frontmatter


def test_write_failure_returns_none(tmp_path, monkeypatch):
    ctx = ProjectContext(str(tmp_path))
    import ayder_cli.tools.builtins.notes as notes_mod

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(notes_mod, "_write_note", boom)
    rel = write_agent_note(ctx, agent_name="x", run_id=1, generation=1, status="done",
                           task="t", content="c", timestamp="20260618-120000")
    assert rel is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/tools/test_agent_notes.py -v`
Expected: FAIL — `ImportError: cannot import name 'write_agent_note'`.

- [ ] **Step 3: Edit `src/ayder_cli/tools/builtins/notes.py`**

Add after the imports (top of file):
```python
import json
import logging

logger = logging.getLogger(__name__)
```
Add after `_title_to_slug`:
```python
def _yaml_scalar(value: object) -> str:
    """Render a value as a safely double-quoted YAML scalar.

    json.dumps escapes quotes, backslashes, newlines, tabs, and control
    characters, and a JSON string is a valid YAML 1.2 flow scalar.
    """
    return json.dumps(str(value), ensure_ascii=False)


def _write_note(
    notes_dir: Path, filename: str, frontmatter: list[str], body: str, *, exclusive: bool = False
) -> Path:
    """Write YAML frontmatter + body. When exclusive, never overwrite —
    append a numeric suffix on collision. Returns the written path.
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
            with open(candidate, "x", encoding="utf-8") as f:  # exclusive create
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
    generation: int,
    status: str,
    task: str,
    content: str,
    timestamp: str,
    error: str | None = None,
) -> str | None:
    """Persist an agent's final deliverable to .ayder/notes/. Best-effort.

    Non-overwriting and YAML-safe. Returns the project-relative path, or None
    if writing fails (a note failure must never fail the agent run).
    """
    try:
        notes_dir = _get_notes_dir(project_ctx)
        slug = _title_to_slug(agent_name)
        filename = f"{timestamp}-{slug}-run{run_id}.md"
        frontmatter = [
            f"title: {_yaml_scalar(f'{agent_name} run {run_id}')}",
            f"date: {_yaml_scalar(timestamp)}",
            f"agent: {_yaml_scalar(agent_name)}",
            f"run_id: {run_id}",
            f"generation: {generation}",
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

- [ ] **Step 4: Run to verify pass (incl. existing notes tests)**

Run: `uv run pytest tests/tools/test_agent_notes.py -v && uv run pytest tests/tools -k note -v`
Expected: PASS — new tests pass; existing `create_note` tests unaffected.

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/tools/builtins/notes.py tests/tools/test_agent_notes.py
git commit -m "feat(notes): write_agent_note — durable, collision-proof, YAML-safe agent notes"
```

---

### Task 2: Runner — final-message capture + note + `AgentRunOutcome`

**Files:**
- Modify: `src/ayder_cli/agents/runner.py`
- Test: `tests/agents/test_runner.py`

**Interfaces:**
- Consumes: `write_agent_note` (Task 1).
- Produces: `AgentRunOutcome(status: str, content: str, error: str | None, note_path: str | None)`; `AgentRunner.run(task) -> AgentRunOutcome`; `AgentRunner._final_message(messages: list[dict]) -> str` (static). `AgentRunner.__init__` gains `generation: int = 0`.

- [ ] **Step 1: Write the failing tests** — append to `tests/agents/test_runner.py`:

```python
import pytest
from unittest.mock import MagicMock, patch

from ayder_cli.agents.config import AgentConfig
from ayder_cli.agents.runner import AgentRunner, AgentRunOutcome


def _fake_rt():
    rt = MagicMock()
    rt.system_prompt = "sys"
    rt.config = MagicMock(model="m", provider="p", num_ctx=1, max_output_tokens=1,
                          stop_sequences=[], tool_tags=None, max_history_messages=30)
    return rt


@pytest.mark.anyio
async def test_run_returns_final_message_not_transcript(tmp_path):
    from ayder_cli.core.context import ProjectContext
    cfg = AgentConfig(name="reporter", system_prompt="Write a report.")
    runner = AgentRunner(
        agent_config=cfg, parent_config=MagicMock(), project_ctx=ProjectContext(str(tmp_path)),
        process_manager=MagicMock(), permissions=set(), timeout=5, run_id=42, generation=3,
    )

    def loop_ctor(**kwargs):
        msgs = kwargs["messages"]
        m = MagicMock()
        async def _run(*a, **k):
            msgs.append({"role": "assistant", "content": "Let me check the files."})
            msgs.append({"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]})
            msgs.append({"role": "tool", "content": "file contents"})
            msgs.append({"role": "assistant", "content": "# Final Report\nAll done."})
        m.run = _run
        return m

    import ayder_cli.agents.runner as rm
    with patch.object(rm, "create_agent_runtime", return_value=_fake_rt()), \
         patch.object(rm, "ChatLoop", side_effect=loop_ctor):
        out = await runner.run("Write the report")

    assert isinstance(out, AgentRunOutcome)
    assert out.status == "done"
    assert out.content == "# Final Report\nAll done."
    assert "Let me check the files." not in out.content
    assert out.note_path is not None
    assert (tmp_path / out.note_path).read_text(encoding="utf-8").count("# Final Report") == 1


@pytest.mark.anyio
async def test_run_reports_error_when_stream_fails_after_text():
    cfg = AgentConfig(name="x", system_prompt="s")
    runner = AgentRunner(
        agent_config=cfg, parent_config=MagicMock(), project_ctx=MagicMock(),
        process_manager=MagicMock(), permissions=set(), timeout=5, run_id=1, generation=1,
    )

    def loop_ctor(**kwargs):
        cb = kwargs["callbacks"]; msgs = kwargs["messages"]
        m = MagicMock()
        async def _run(*a, **k):
            msgs.append({"role": "assistant", "content": "intermediate text"})
            cb.last_content = "intermediate text"          # cumulative, non-empty
            cb.last_system_error = "Error: stream failed"  # late failure
        m.run = _run
        return m

    import ayder_cli.agents.runner as rm
    with patch.object(rm, "create_agent_runtime", return_value=_fake_rt()), \
         patch.object(rm, "ChatLoop", side_effect=loop_ctor):
        out = await runner.run("t")

    assert out.status == "error"               # NOT "done"
    assert out.error == "Error: stream failed"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/agents/test_runner.py -k "final_message or stream_fails" -v`
Expected: FAIL — `cannot import name 'AgentRunOutcome'`.

- [ ] **Step 3: Edit `src/ayder_cli/agents/runner.py`**

3a. Remove `import re`, `_SUMMARY_PATTERN`, and the `_parse_summary` method. Replace the `AgentSummary` import with:
```python
from dataclasses import dataclass
from datetime import datetime
```
3b. Add the outcome type (module level) and a `generation` param:
```python
@dataclass
class AgentRunOutcome:
    """What an AgentRunner produces; the registry applies it to its AgentRun."""
    status: str          # "done" | "error"
    content: str
    error: str | None
    note_path: str | None
```
In `__init__`, add `generation: int = 0,` (after `run_id`) and store `self._generation = generation`.

3c. Add the final-message extractor and note helper:
```python
    @staticmethod
    def _final_message(messages: list[dict]) -> str:
        """Last assistant message with real text — the deliverable.

        Skips pure <think> blocks and tool-only (empty-content) messages.
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

    def _persist_note(self, task: str, status: str, content: str, error: str | None) -> str | None:
        from ayder_cli.tools.builtins.notes import write_agent_note
        return write_agent_note(
            self._project_ctx, agent_name=self.agent_name, run_id=self.run_id,
            generation=self._generation, status=status, task=task, content=content,
            timestamp=datetime.now().strftime("%Y%m%d-%H%M%S"), error=error,
        )
```

3d. Change `run`'s return type to `-> AgentRunOutcome`. Keep the local `messages` list. Replace each terminal branch:

- timeout:
```python
            except asyncio.TimeoutError:
                self._cancel_event.set()
                self.status = "timeout"
                content = self._final_message(messages) or "Agent timed out before producing output."
                err = f"Agent exceeded {self._timeout}s timeout"
                return AgentRunOutcome("error", content, err, self._persist_note(task, "error", content, err))
```
- error (F8 — drop the `and not last_content.strip()` guard):
```python
            if callbacks.last_system_error:
                self.status = "error"
                content = self._final_message(messages)
                err = callbacks.last_system_error
                return AgentRunOutcome("error", content, err, self._persist_note(task, "error", content, err))
```
- success:
```python
            self.status = "completed"
            content = self._final_message(messages) or "Agent completed without producing output."
            return AgentRunOutcome("done", content, None, self._persist_note(task, "done", content, None))
```
- exception:
```python
        except Exception as e:
            self.status = "error"
            logger.exception(f"Agent '{self.agent_name}' failed: {e}")
            return AgentRunOutcome("error", "Agent encountered an error.", str(e),
                                   self._persist_note(task, "error", "Agent encountered an error.", str(e)))
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/agents/test_runner.py -v`
Expected: PASS. (Update/remove any old test asserting `AgentSummary`/`_parse_summary`.)

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/agents/runner.py tests/agents/test_runner.py
git commit -m "feat(agents): runner emits AgentRunOutcome (final message + persisted note)"
```

---

### Task 3: `AgentRun` + registry pull API + app delivery rewiring (atomic)

The shared result type and its consumers change together so the commit stays green (app.py uses the old `drain_summaries`/`AgentSummary` today).

**Files:**
- Create: `src/ayder_cli/agents/run.py`
- Modify: `src/ayder_cli/agents/registry.py`, `src/ayder_cli/agents/__init__.py`, `src/ayder_cli/tui/app.py`
- Delete: `src/ayder_cli/agents/summary.py`
- Test: `tests/agents/test_run.py` (new), `tests/agents/test_registry.py`, `tests/tui/test_pull_delivery.py` (new)

**Interfaces:**
- Consumes: `AgentRunOutcome` (Task 2).
- Produces: `AgentRun` (below); registry: `create_run(name, task) -> int | str`, `snapshot() -> list[dict]`, `read_result(run_id) -> dict | None`, `await_run(run_id, timeout_s) -> dict | None` (coroutine), `pending_nudge() -> list[AgentRun]`, `mark_nudged(runs)`, `new_generation() -> int`, `current_generation` (property), `active_count` (property), `_on_loop(fn)`. App: `_maybe_nudge()`.

- [ ] **Step 1: Write `AgentRun` test** — create `tests/agents/test_run.py`:

```python
from ayder_cli.agents.run import AgentRun


def test_working_time_uses_now_until_finished():
    r = AgentRun(run_id=1, generation=1, agent_name="x", started_at=100.0)
    assert r.working_time(now=142.0) == 42
    r.finished_at = 130.0
    assert r.working_time(now=999.0) == 30  # frozen at finish


def test_to_status_dict_hides_result_body():
    r = AgentRun(run_id=2, generation=1, agent_name="rev", started_at=0.0,
                 status="done", result="SECRET", note_path=".ayder/notes/n.md")
    d = r.to_status_dict(now=5.0)
    assert d == {"run_id": 2, "name": "rev", "status": "done", "working_time_s": 5,
                 "has_unread_result": True, "note_path": ".ayder/notes/n.md"}
    assert "SECRET" not in str(d)


def test_has_unread_result_false_when_working_or_drained():
    r = AgentRun(run_id=1, generation=1, agent_name="x", started_at=0.0, status="working")
    assert r.to_status_dict(now=0.0)["has_unread_result"] is False
    r.status, r.drained = "done", True
    assert r.to_status_dict(now=0.0)["has_unread_result"] is False
```

- [ ] **Step 2: Create `src/ayder_cli/agents/run.py`**

```python
"""AgentRun — the per-dispatch state record the main LLM polls and drains."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class AgentRun:
    run_id: int
    generation: int
    agent_name: str
    started_at: float                       # monotonic() at dispatch
    status: str = "working"                 # "working" | "done" | "error"
    result: str = ""                        # final message; "" until finished
    error: str | None = None
    note_path: str | None = None
    finished_at: float | None = None
    drained: bool = False
    nudged: bool = False
    done_event: asyncio.Event = field(default_factory=asyncio.Event)

    def working_time(self, *, now: float) -> int:
        return int((self.finished_at if self.finished_at is not None else now) - self.started_at)

    @property
    def has_unread_result(self) -> bool:
        return self.status in ("done", "error") and not self.drained

    def to_status_dict(self, *, now: float) -> dict:
        return {
            "run_id": self.run_id, "name": self.agent_name, "status": self.status,
            "working_time_s": self.working_time(now=now),
            "has_unread_result": self.has_unread_result, "note_path": self.note_path,
        }
```

- [ ] **Step 3: Run** `uv run pytest tests/agents/test_run.py -v` → PASS.

- [ ] **Step 4: Rewrite the registry result API** — edit `src/ayder_cli/agents/registry.py`:

4a. Imports: drop `from ayder_cli.agents.summary import AgentSummary`; add:
```python
import time
from ayder_cli.agents.run import AgentRun
from ayder_cli.agents.runner import AgentRunner, AgentRunOutcome
```
Change the `on_complete` type hint to `Callable[[int, AgentRun], None] | None`.

4b. In `__init__`, replace `self._summary_queue = ...` with:
```python
        self._runs: dict[int, AgentRun] = {}
        self._current_generation: int = 0
```
(Keep `self._active`, `self._run_counter`, `self._settled`, `self._loop`.)

4c. Replace `active_count` to derive from runs, and add accessors + the marshal helper:
```python
    @property
    def active_count(self) -> int:
        return sum(1 for r in self._runs.values() if r.status == "working")

    @property
    def current_generation(self) -> int:
        return self._current_generation

    def new_generation(self) -> int:
        """Bump the conversation generation and reset the re-dispatch guard.
        Does NOT drop _runs: active agents keep running and are simply filtered
        out of delivery (snapshot/read/nudge) for the new conversation."""
        self._current_generation += 1
        self._settled = {}
        return self._current_generation

    async def _on_loop_coro(self, fn):
        return fn()

    def _on_loop(self, fn):
        """Run fn() on the owning event loop from a worker thread; return its result.

        Fails explicitly if the loop is unset — registry state is loop-owned, so a
        worker thread must never read/mutate it directly (single-loop invariant, §4).
        """
        if self._loop is None:
            raise RuntimeError("AgentRegistry loop not set (call set_loop first)")
        return asyncio.run_coroutine_threadsafe(self._on_loop_coro(fn), self._loop).result()
```

4d. Replace `dispatch` with `create_run` (runs on the loop; no more worker-thread mutation):
```python
    def create_run(self, name: str, task: str) -> int | str:
        """Create an AgentRun and schedule it. MUST run on the event loop.
        Returns run_id (int) or an error string."""
        if name not in self.agents:
            available = ", ".join(sorted(self.agents))
            return (f"Error: Agent '{name}' not found. Available: {available}. Call list_agents."
                    if available else
                    "Error: Agent '{name}' not found. No agents configured.".format(name=name))
        if name in self._settled and self._settled[name] in ("error", "timeout"):
            return (f"Error: Agent '{name}' failed in this cycle "
                    f"(status: {self._settled[name]}). Handle the task directly.")
        if self._loop is None:
            return "Error: Agent registry not initialized (event loop not set)"

        self._run_counter += 1
        run_id = self._run_counter
        runner = AgentRunner(
            agent_config=self.agents[name], parent_config=self._parent_config,
            project_ctx=self._project_ctx, process_manager=self._process_manager,
            permissions=self._permissions, timeout=self._agent_timeout,
            run_id=run_id, generation=self._current_generation, on_progress=self._on_progress,
        )
        run = AgentRun(run_id=run_id, generation=self._current_generation,
                       agent_name=name, started_at=time.monotonic())
        self._runs[run_id] = run
        self._active[run_id] = runner
        asyncio.create_task(self._run_and_queue(run, runner, task))
        return run_id

    async def _run_and_queue(self, run: AgentRun, runner: AgentRunner, task: str) -> None:
        outcome: AgentRunOutcome | None = None
        try:
            outcome = await runner.run(task)
        except Exception:
            logger.exception("agent run crashed: run_id=%d", run.run_id)
            outcome = AgentRunOutcome("error", "Agent encountered an error.", "internal error", None)
        finally:
            self._active.pop(run.run_id, None)
            if outcome is not None:
                run.status = outcome.status
                run.result = outcome.content
                run.error = outcome.error
                run.note_path = outcome.note_path
            run.finished_at = time.monotonic()
            run.done_event.set()
            if run.generation == self._current_generation and outcome is not None:
                self._settled[run.agent_name] = outcome.status
            if self._on_complete is not None:
                try:
                    self._on_complete(run.run_id, run)
                except Exception:
                    logger.exception("on_complete callback failed")
```

4e. Replace `drain_summaries`/`has_pending_summaries` with the pull/nudge methods:
```python
    def snapshot(self) -> list[dict]:
        now = time.monotonic()
        runs = [r for r in self._runs.values() if r.generation == self._current_generation]
        runs.sort(key=lambda r: r.run_id, reverse=True)
        return [r.to_status_dict(now=now) for r in runs]

    def _result_payload(self, run: AgentRun) -> dict:
        """Full payload for a TERMINAL run; marks it drained. Never call on a working run."""
        run.drained = True
        return {"run_id": run.run_id, "name": run.agent_name, "status": run.status,
                "result": run.result, "note_path": run.note_path,
                "working_time_s": run.working_time(now=time.monotonic()), "error": run.error}

    def read_result(self, run_id: int) -> dict | None:
        run = self._runs.get(run_id)
        if run is None or run.generation != self._current_generation:
            return None
        if run.status == "working":
            return run.to_status_dict(now=time.monotonic())   # NOT drained (finding 1)
        return self._result_payload(run)                       # terminal -> drains

    async def await_run(self, run_id: int, timeout_s: float) -> dict | None:
        run = self._runs.get(run_id)
        if run is None or run.generation != self._current_generation:
            return None
        if run.status == "working":
            capped = max(0.0, min(float(timeout_s), float(self._agent_timeout)))
            try:
                await asyncio.wait_for(run.done_event.wait(), timeout=capped)
            except asyncio.TimeoutError:
                return run.to_status_dict(now=time.monotonic())  # still working, NOT drained
        if run.status == "working":
            return run.to_status_dict(now=time.monotonic())      # spurious wake; NOT drained
        return self._result_payload(run)                          # terminal -> drains

    def pending_nudge(self) -> list[AgentRun]:
        return [r for r in self._runs.values()
                if r.generation == self._current_generation
                and r.status in ("done", "error") and not r.drained and not r.nudged]

    def mark_nudged(self, runs: list[AgentRun]) -> None:
        for r in runs:
            r.nudged = True
```
Keep `cancel`, `get_status`, `get_running_count`, `list_agents`, `reset_settled`. In `get_status`, the running check still reads `self._active`; the settled branch is unchanged.

- [ ] **Step 5: Update `src/ayder_cli/agents/__init__.py`** — remove the `AgentSummary` export; add `from ayder_cli.agents.run import AgentRun` and `from ayder_cli.agents.runner import AgentRunOutcome` to `__all__` if it lists agent types. Then `git rm src/ayder_cli/agents/summary.py`.

- [ ] **Step 6: Rewrite the registry tests** — in `tests/agents/test_registry.py`, replace summary-queue tests. Add (keep existing dispatch-validation tests, renaming `dispatch`→`create_run`):

```python
import asyncio
import pytest


@pytest.mark.anyio
async def test_create_run_then_snapshot_and_read(registry):
    registry.set_loop(asyncio.get_running_loop())
    rid = registry.create_run("reviewer", "do it")
    assert isinstance(rid, int)
    # simulate completion
    run = registry._runs[rid]
    run.status, run.result, run.drained = "done", "THE RESULT", False
    run.done_event.set()
    snap = registry.snapshot()
    assert snap[0]["run_id"] == rid and snap[0]["has_unread_result"] is True
    assert "result" not in snap[0]                 # status omits the body
    payload = registry.read_result(rid)
    assert payload["result"] == "THE RESULT"
    assert registry._runs[rid].drained is True     # read marks drained
    assert registry.read_result(rid)["result"] == "THE RESULT"  # idempotent read


def test_new_generation_keeps_runs_but_filters(registry):
    from ayder_cli.agents.run import AgentRun
    registry._runs[1] = AgentRun(run_id=1, generation=0, agent_name="x", started_at=0.0,
                                 status="done", result="STALE")
    registry._current_generation = 0
    registry._run_counter = 1
    registry.new_generation()
    assert registry.snapshot() == []               # old-gen filtered out
    assert registry.read_result(1) is None
    assert registry.pending_nudge() == []
    assert 1 in registry._runs                      # but NOT dropped


def test_pending_nudge_excludes_drained_and_nudged(registry):
    from ayder_cli.agents.run import AgentRun
    registry._current_generation = 1
    registry._runs = {
        1: AgentRun(1, 1, "a", 0.0, status="done"),
        2: AgentRun(2, 1, "b", 0.0, status="done", drained=True),
        3: AgentRun(3, 1, "c", 0.0, status="done", nudged=True),
        4: AgentRun(4, 1, "d", 0.0, status="working"),
    }
    ids = [r.run_id for r in registry.pending_nudge()]
    assert ids == [1]
    registry.mark_nudged(registry.pending_nudge())
    assert registry.pending_nudge() == []


def test_read_while_working_does_not_drain_then_completion_still_nudges(registry):
    # finding 1 regression: a non-blocking read of a WORKING run must not drain it,
    # or the later completion would have no unread result and never nudge.
    from ayder_cli.agents.run import AgentRun
    registry._current_generation = 1
    run = AgentRun(run_id=5, generation=1, agent_name="x", started_at=0.0, status="working")
    registry._runs[5] = run
    payload = registry.read_result(5)
    assert payload["status"] == "working"
    assert run.drained is False                       # NOT drained while working
    # agent completes:
    run.status, run.result = "done", "DELIVERABLE"
    assert [r.run_id for r in registry.pending_nudge()] == [5]   # still nudge-eligible
    assert registry.read_result(5)["result"] == "DELIVERABLE"
    assert run.drained is True                          # terminal read drains
```
(If the `registry` fixture passed `on_complete`/`drain` assertions, update them. Construct `AgentRun` positionally as `AgentRun(run_id, generation, agent_name, started_at, ...)`.)

- [ ] **Step 7: Rewire app.py delivery** — edit `src/ayder_cli/tui/app.py`:

7a. Replace the `_agent_complete` closure (lines ~259-283) body with UI-only + nudge:
```python
            def _agent_complete(run_id, run):
                try:
                    panel = self.query_one("#agent-panel", AgentPanel)
                    self.call_later(lambda: panel.complete_agent(run_id, run.result, run.status))
                except Exception:
                    pass
                try:
                    activity = self.query_one("#activity-bar", ActivityBar)
                    count = self._agent_registry.active_count if self._agent_registry else 0
                    self.call_later(lambda: activity.set_agents_running(count))
                except Exception:
                    pass
                self._maybe_nudge()                 # event-driven nudge (spec §7)
```

7b. In `_composed_pre_iteration` (lines ~359-377), **delete** the agent-drain block (the `if self._agent_registry: summaries = ... drain_summaries() ...` lines). Keep `apply_pending_compact` and the existing-hook tail.

7c. Delete the module-level `_wake_for_pending_agents` function (lines ~50-72) and its use in `_finish_processing`. Replace the `elif self._agent_registry:` branch of `_finish_processing` (lines ~702-708) with:
```python
        self._is_processing = False
        if self._agent_registry:
            self._maybe_nudge()                     # turn-finished nudge
```

7d. Add the nudge method + the 1 s fallback timer. Add this method to `AyderApp`:
```python
    def _maybe_nudge(self) -> None:
        """Wake the LLM once when it left a finished agent result unread while idle."""
        if self._is_processing or not self._agent_registry:
            return
        pending = self._agent_registry.pending_nudge()
        if not pending:
            return
        n = len(pending)
        self.messages.append({"role": "user", "content":
            f"[system] {n} agent result(s) are ready and unread. "
            f"Call agent_status() then read_agent_result(run_id) to collect."})
        self.start_llm_processing()                 # Phase B swaps this for request_turn
        self._agent_registry.mark_nudged(pending)   # finding A: AFTER enqueue
```
In `on_mount` (after line 589, the `set_loop`), add:
```python
        if self._agent_registry:
            self.set_interval(1.0, self._maybe_nudge)   # recovery fallback (spec §7)
```

- [ ] **Step 8: Write the delivery test** — create `tests/tui/test_pull_delivery.py`:

```python
"""_maybe_nudge: nudges once when idle with an unread result; never while busy/looping."""

from unittest.mock import MagicMock

from ayder_cli.agents.run import AgentRun


class FakeReg:
    def __init__(self, runs): self._runs = runs
    def pending_nudge(self):
        return [r for r in self._runs if r.status in ("done", "error") and not r.drained and not r.nudged]
    def mark_nudged(self, runs):
        for r in runs: r.nudged = True


def _app(reg, processing=False):
    from ayder_cli.tui.app import AyderApp
    app = AyderApp.__new__(AyderApp)            # bypass __init__/Textual
    app._agent_registry = reg
    app._is_processing = processing
    app.messages = []
    app.start_llm_processing = MagicMock()
    return app


def test_nudges_once_when_idle_with_unread():
    run = AgentRun(1, 1, "a", 0.0, status="done", result="R")
    app = _app(FakeReg([run]))
    app._maybe_nudge()
    assert app.start_llm_processing.call_count == 1
    assert "unread" in app.messages[0]["content"]
    app._maybe_nudge()                          # already nudged -> no second wake (no loop)
    assert app.start_llm_processing.call_count == 1


def test_no_nudge_while_processing():
    run = AgentRun(1, 1, "a", 0.0, status="done", result="R")
    app = _app(FakeReg([run]), processing=True)
    app._maybe_nudge()
    app.start_llm_processing.assert_not_called()


def test_no_nudge_without_pending():
    app = _app(FakeReg([AgentRun(1, 1, "a", 0.0, status="working")]))
    app._maybe_nudge()
    app.start_llm_processing.assert_not_called()
```

- [ ] **Step 9: Run agent + tui suites**

Run: `uv run pytest tests/agents/ tests/tui/test_pull_delivery.py -v`
Expected: PASS. Fix any remaining references to `AgentSummary`/`drain_summaries`/`has_pending_summaries`/`_wake_for_pending_agents` (grep `src/` and `tests/`).

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "feat(agents): AgentRun pull model + single-loop registry; rewire TUI delivery to nudge"
```

---

### Task 4: Pull tools — `agent_status`, `read_agent_result`, `call_agent` return

**Files:**
- Modify: `src/ayder_cli/agents/tool.py`
- Test: `tests/agents/test_agent_tools.py` (new)

**Interfaces:**
- Consumes: `registry.create_run`, `snapshot`, `read_result`, `await_run`, `_on_loop` (Task 3).
- Produces: `AGENT_STATUS_TOOL_DEFINITION`, `READ_AGENT_RESULT_TOOL_DEFINITION`, `create_agent_status_handler(registry)`, `create_read_agent_result_handler(registry)`.

- [ ] **Step 1: Write the failing tests** — create `tests/agents/test_agent_tools.py`:

```python
import asyncio
import json
import pytest
from unittest.mock import MagicMock

from ayder_cli.agents.run import AgentRun
from ayder_cli.agents.tool import (
    create_call_agent_handler, create_agent_status_handler, create_read_agent_result_handler,
)


def _reg_on_loop(reg):
    reg._on_loop = lambda fn: fn()  # synchronous for unit tests


def test_call_agent_return_leads_with_run_id():
    reg = MagicMock()
    reg.create_run.return_value = 7
    _reg_on_loop(reg)
    out = create_call_agent_handler(reg)(name="reviewer", task="do it")
    assert "run #7" in out and "read_agent_result" in out


def test_agent_status_returns_snapshot_json():
    reg = MagicMock()
    reg.snapshot.return_value = [{"run_id": 7, "name": "r", "status": "done",
                                  "working_time_s": 1, "has_unread_result": True, "note_path": None}]
    _reg_on_loop(reg)
    data = json.loads(create_agent_status_handler(reg)())
    assert data["agents"][0]["run_id"] == 7


def test_list_agents_marshals_through_loop():
    # finding 3: list_agents reads _active/_settled, so it must go through _on_loop.
    from ayder_cli.agents.tool import create_list_agents_handler
    reg = MagicMock()
    reg.list_agents.return_value = [{"name": "r"}]
    calls = []
    reg._on_loop = lambda fn: (calls.append("on_loop"), fn())[1]
    data = json.loads(create_list_agents_handler(reg)())
    assert calls == ["on_loop"]                 # marshalled, not a direct read
    assert data["agents"][0]["name"] == "r"


@pytest.mark.anyio
async def test_read_agent_result_wait_blocks_then_returns():
    from ayder_cli.agents.registry import AgentRegistry
    reg = AgentRegistry(agents={}, parent_config=MagicMock(), project_ctx=MagicMock(),
                        process_manager=MagicMock(), permissions=set())
    reg.set_loop(asyncio.get_running_loop())
    run = AgentRun(3, 0, "x", 0.0, status="working")
    reg._runs[3] = run
    handler = create_read_agent_result_handler(reg)

    async def finish():
        await asyncio.sleep(0.01)
        run.status, run.result = "done", "DONE"
        run.done_event.set()

    asyncio.create_task(finish())
    out = await asyncio.to_thread(handler, run_id=3, wait=True, timeout_s=5)
    assert json.loads(out)["result"] == "DONE"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/agents/test_agent_tools.py -v`
Expected: FAIL — missing tool factories.

- [ ] **Step 3: Edit `src/ayder_cli/agents/tool.py`**

3a. Change `call_agent` handler return (replace the success branch in `handle_call_agent`):
```python
    def handle_call_agent(*, name: str, task: str) -> str:
        result = registry._on_loop(lambda: registry.create_run(name, task))
        if isinstance(result, int):
            return (f"Dispatched '{name}' as run #{result} (working). "
                    f"Poll with agent_status; collect with read_agent_result({result}).")
        return result  # error string
```
Update `AGENT_TOOL_DEFINITION.description` to the pull contract (drop "You will receive its summary"):
> "Delegate a task to a specialized agent that runs in the background. Returns a run id immediately; poll agent_status and collect with read_agent_result. Use list_agents to discover names first."

3b. Add the two tool definitions + handlers:
```python
AGENT_STATUS_TOOL_DEFINITION = ToolDefinition(
    name="agent_status",
    description=("Show all agent runs you dispatched this conversation with their status "
                 "(working/done/error), elapsed seconds, and whether a result is unread. "
                 "Use read_agent_result(run_id) to collect a finished one."),
    parameters={"type": "object", "properties": {}, "required": []},
    permission="r", tags=("core", "agents"), system_prompt="",
)

READ_AGENT_RESULT_TOOL_DEFINITION = ToolDefinition(
    name="read_agent_result",
    description=("Collect a dispatched agent's deliverable by run id. Marks it read. "
                 "Set wait=true to block until it finishes (up to timeout_s seconds)."),
    parameters={"type": "object", "properties": {
        "run_id": {"type": "integer", "description": "The run id from call_agent / agent_status"},
        "wait": {"type": "boolean", "description": "Block until the agent finishes (default false)"},
        "timeout_s": {"type": "integer", "description": "Max seconds to block when wait=true (default 60)"},
    }, "required": ["run_id"]},
    permission="r", tags=("core", "agents"), system_prompt="",
)


def create_agent_status_handler(registry: AgentRegistry) -> Callable[..., str]:
    def handle_agent_status() -> str:
        return json.dumps({"agents": registry._on_loop(lambda: registry.snapshot())}, indent=2)
    return handle_agent_status


def create_read_agent_result_handler(registry: AgentRegistry) -> Callable[..., str]:
    def handle_read_agent_result(*, run_id: int, wait: bool = False, timeout_s: int = 60) -> str:
        if wait:
            payload = asyncio.run_coroutine_threadsafe(
                registry.await_run(run_id, timeout_s), registry._loop
            ).result() if registry._loop else None
        else:
            payload = registry._on_loop(lambda: registry.read_result(run_id))
        if payload is None:
            return json.dumps({"error": f"No agent run #{run_id} in this conversation."})
        return json.dumps(payload, indent=2)
    return handle_read_agent_result
```
Add `import asyncio` at the top of `tool.py`.

3c. **Marshal `list_agents` through the loop (finding 3).** It reads `_active`/`_settled`, so the existing direct call from the worker-thread handler races. Change `handle_list_agents` in `create_list_agents_handler`:
```python
    def handle_list_agents() -> str:
        return json.dumps({"agents": registry._on_loop(lambda: registry.list_agents())}, indent=2)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/agents/test_agent_tools.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/agents/tool.py tests/agents/test_agent_tools.py
git commit -m "feat(agents): agent_status + read_agent_result pull tools; call_agent returns run id"
```

---

### Task 5: Register pull tools in TUI and CLI

**Files:**
- Modify: `src/ayder_cli/tui/app.py` (~298-300), `src/ayder_cli/cli_runner.py` (64-67)
- Test: `tests/agents/test_agent_tools.py`

**Interfaces:** Consumes the Task 4 definitions/handlers.

- [ ] **Step 1: Add a CLI registration test** — append to `tests/agents/test_agent_tools.py`:

```python
def test_cli_registers_pull_tools(tmp_path, monkeypatch):
    import ayder_cli.cli_runner as cli
    registered = []
    fake_reg = MagicMock()
    fake_reg.get_capability_prompts.return_value = ""
    fake_registry_obj = MagicMock()
    fake_registry_obj.register_dynamic_tool = lambda defn, h: registered.append(defn.name)
    rt = MagicMock()
    rt.config = MagicMock(agents={"r": object()}, model="m", provider="p", num_ctx=1,
                          max_output_tokens=1, stop_sequences=[], tool_tags=None, max_history_messages=30,
                          verbose=False)
    rt.tool_registry = fake_registry_obj
    monkeypatch.setattr(cli, "create_runtime", lambda: rt)
    monkeypatch.setattr(cli, "AgentRegistry", lambda **k: fake_reg)
    monkeypatch.setattr(cli, "ChatLoop", MagicMock())
    monkeypatch.setattr(cli.asyncio, "run", lambda coro: coro.close())
    cli._run_loop("hi", permissions={"r"})
    assert {"call_agent", "list_agents", "agent_status", "read_agent_result"} <= set(registered)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/agents/test_agent_tools.py::test_cli_registers_pull_tools -v`
Expected: FAIL — only `call_agent`/`list_agents` registered.

- [ ] **Step 3: Register in the TUI** — in `src/ayder_cli/tui/app.py` after line ~300 (the `register_dynamic_tool(AGENT_TOOL_DEFINITION, handler)` line) add:
```python
            self.registry.register_dynamic_tool(
                AGENT_STATUS_TOOL_DEFINITION, create_agent_status_handler(self._agent_registry))
            self.registry.register_dynamic_tool(
                READ_AGENT_RESULT_TOOL_DEFINITION, create_read_agent_result_handler(self._agent_registry))
```
Extend the `from ayder_cli.agents.tool import (...)` import to include the two new definitions and handlers.

- [ ] **Step 4: Register in the CLI** — in `src/ayder_cli/cli_runner.py` after line 67, add the same two `register_dynamic_tool` calls (using `agent_registry`), and extend the import at lines 17-22.

- [ ] **Step 5: Run** `uv run pytest tests/agents/test_agent_tools.py -v` → PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ayder_cli/tui/app.py src/ayder_cli/cli_runner.py tests/agents/test_agent_tools.py
git commit -m "feat(agents): register agent_status + read_agent_result in TUI and CLI"
```

---

### Task 6: Capability prompt — pull contract

**Files:**
- Modify: `src/ayder_cli/agents/registry.py` (`get_capability_prompts`, ~99-119)
- Test: `tests/agents/test_registry.py`

- [ ] **Step 1: Replace the capability test** — in `tests/agents/test_registry.py`:

```python
    def test_capability_prompt_is_pull(self, registry):
        p = registry.get_capability_prompts()
        assert "agent_status" in p and "read_agent_result" in p
        assert "after all agents complete" not in p
        assert "Batch behavior" not in p
        assert "pull" in p.lower()
        assert "note" in p.lower()
```

- [ ] **Step 2: Run** `uv run pytest tests/agents/test_registry.py -k capability -v` → FAIL.

- [ ] **Step 3: Edit `get_capability_prompts`** — replace the `lines = [...]` block:
```python
        lines = [
            "\n## Agent Delegation",
            "",
            "Configured specialized agents may be available. Use `list_agents` to discover "
            "exact names before `call_agent`. Each runs in the background with its own LLM.",
            "",
            "**You pull results — they are not delivered automatically.** `call_agent` returns "
            "a run id. Use `agent_status()` to see what is working/done, and "
            "`read_agent_result(run_id)` to collect a finished one. To wait for an agent, call "
            "`read_agent_result(run_id, wait=true, timeout_s=…)` instead of polling in a loop.",
            "",
            "Each finished run has a best-effort `note_path` to its full saved deliverable; if a "
            "result has scrolled out of context, `read_file` that path instead of re-dispatching.",
            "If you end your turn with results unread, you will be nudged once to collect them.",
            "",
            "**Rules:** dispatch the same agent multiple times if useful; only use an agent whose "
            "specialty matches; on failure, handle the task yourself — do not re-dispatch a failed agent.",
        ]
```

- [ ] **Step 4: Run** `uv run pytest tests/agents/test_registry.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/agents/registry.py tests/agents/test_registry.py
git commit -m "docs(agents): capability prompt — pull contract (agent_status/read_agent_result)"
```

---

### Task 7: Agent prompt — deliverable directive

**Files:**
- Modify: `src/ayder_cli/application/runtime_factory.py:183-194`
- Test: `tests/application/test_runtime_factory.py`

- [ ] **Step 1: Write the failing test** — append:
```python
def test_agent_prompt_uses_final_message_contract_not_summary_block():
    from unittest.mock import MagicMock, patch
    from ayder_cli.agents.config import AgentConfig
    from ayder_cli.application import runtime_factory
    agent_cfg = AgentConfig(name="reporter", system_prompt="Produce a document.")
    parent = MagicMock(provider="ollama", tool_tags=None, retry=MagicMock(enabled=False))
    fake_reg = MagicMock(); fake_reg.get_system_prompts.return_value = "\n[tools]\n"; fake_reg.get_schemas.return_value = []
    with patch.object(runtime_factory.provider_orchestrator, "create", return_value=MagicMock()), \
         patch.object(runtime_factory.context_manager_factory, "create", return_value=MagicMock()), \
         patch.object(runtime_factory, "create_default_registry", return_value=fake_reg):
        rt = runtime_factory.create_agent_runtime(
            agent_config=agent_cfg, parent_config=parent, project_ctx=MagicMock(),
            process_manager=MagicMock(), permissions=set())
    assert "Produce a document." in rt.system_prompt
    assert "<agent-summary>" not in rt.system_prompt
    assert "final message" in rt.system_prompt.lower()
```

- [ ] **Step 2: Run** → FAIL (`<agent-summary>` present).

- [ ] **Step 3: Edit `runtime_factory.py`** — replace `summary_suffix = (...)` (183-191) with:
```python
    deliverable_directive = (
        "\n\n---\n"
        "Put your COMPLETE deliverable in your FINAL message, formatted exactly as the task "
        "requests. Only your final message is returned to the caller — intermediate messages and "
        "tool output are not. Do not truncate it and do not add a separate summary block."
    )
```
and line 194:
```python
    system_prompt = identity_prefix + agent_config.system_prompt + tool_prompts + deliverable_directive
```

- [ ] **Step 4: Run** `uv run pytest tests/application/test_runtime_factory.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/application/runtime_factory.py tests/application/test_runtime_factory.py
git commit -m "feat(agents): agent prompt — final-message deliverable directive"
```

---

### Task 8: Generation invalidation call sites

Bumps the generation on conversation replacement so prior-conversation results aren't pulled into a new one. Append semantics (`/load-context`) do **not** bump.

**Files:**
- Modify: `src/ayder_cli/tui/commands.py` (`do_clear`, `handle_compact`, `handle_skill`, `handle_provider`, `handle_model`), `src/ayder_cli/tui/app.py` (`apply_pending_compact`, ~808)
- Test: `tests/tui/test_pull_delivery.py`

- [ ] **Step 1: Add the test** — append to `tests/tui/test_pull_delivery.py`:
```python
def test_do_clear_bumps_generation():
    from unittest.mock import MagicMock
    from ayder_cli.tui.commands import do_clear
    app = MagicMock()
    app._agent_registry = MagicMock()
    do_clear(app, MagicMock())
    app._agent_registry.new_generation.assert_called_once()
```

- [ ] **Step 2: Run** → FAIL (no `new_generation` call).

- [ ] **Step 3: Add `new_generation()` calls.** In each of `do_clear`, `handle_compact`, `handle_skill`, `handle_provider`, `handle_model` (`commands.py`) and `apply_pending_compact` (`app.py`), after the conversation/messages are replaced, add:
```python
    if getattr(app, "_agent_registry", None):
        app._agent_registry.new_generation()
```
Do **not** add it to `/load-context` (append semantics). Confirm via grep that these are the only sites.

- [ ] **Step 4: Run** `uv run pytest tests/tui/test_pull_delivery.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/tui/commands.py src/ayder_cli/tui/app.py tests/tui/test_pull_delivery.py
git commit -m "feat(agents): bump generation on conversation replacement (pull staleness)"
```

- [ ] **Step 6: Phase-A gate** — `uv run poe check-all && uv run poe test-all`. Pull delivery now works end-to-end on the worker turn-model. Commit any fixups.

---

# Phase B — Serial turn consumer (overlap fix)

### Task 9: Single app-owned turn consumer + `request_turn`

Replaces Textual's non-awaiting `exclusive=True` worker with one consumer that **awaits each turn's teardown** before the next request, eliminating the observed overlap. Breaking commands defer their state mutation into a `prepare` callback that runs only when quiescent.

**Files:**
- Modify: `src/ayder_cli/tui/app.py`, `src/ayder_cli/tui/commands.py`
- Test: `tests/tui/test_turn_consumer.py` (new)

**Interfaces:**
- Produces: `TurnRequest(prepare, run_loop, no_tools)`; `AyderApp.request_turn(prepare=None, *, run_loop=True, no_tools=False, interrupt=False)`; `is_turn_running` (property); `_turn_consumer()`; `_after_turn_finished()`. `AppCallbacks` uses a cancel `asyncio.Event`.

- [ ] **Step 1: Write the failing serialization test** — create `tests/tui/test_turn_consumer.py`:

```python
"""The turn consumer runs one ChatLoop.run() at a time and awaits teardown on interrupt."""

import asyncio
import contextlib
from unittest.mock import MagicMock
import pytest


def _app(monkeypatch):
    from ayder_cli.tui.app import AyderApp
    app = AyderApp.__new__(AyderApp)
    app._requests = asyncio.Queue()
    app._run_task = None
    app._pending_messages = []
    app._agent_registry = None
    app.messages = []
    monkeypatch.setattr(app, "_after_turn_finished", lambda: None, raising=False)
    monkeypatch.setattr(app, "_report_turn_error", lambda e: None, raising=False)
    return app


@pytest.mark.anyio
async def test_interrupt_is_serialized(monkeypatch):
    app = _app(monkeypatch)
    order = []
    a_in = asyncio.Event()

    class FakeLoop:
        async def run(self, *, no_tools=False):
            if not a_in.is_set():
                a_in.set(); order.append("A-start")
                try: await asyncio.sleep(3600)
                finally: order.append("A-exit")
            else:
                order.append("B-start")

    app.chat_loop = FakeLoop()
    engine = asyncio.create_task(app._turn_consumer())
    app.request_turn()                                  # A
    await asyncio.wait_for(a_in.wait(), 1)
    app.request_turn(interrupt=True)                    # B interrupts A
    for _ in range(100):
        await asyncio.sleep(0)
        if order[-1:] == ["B-start"]: break
    assert order == ["A-start", "A-exit", "B-start"]    # A fully exits BEFORE B starts
    engine.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await engine


@pytest.mark.anyio
async def test_prepare_runs_only_when_quiescent(monkeypatch):
    app = _app(monkeypatch)
    events = []

    class FakeLoop:
        async def run(self, *, no_tools=False):
            events.append("run"); await asyncio.sleep(0)

    app.chat_loop = FakeLoop()
    engine = asyncio.create_task(app._turn_consumer())
    app.request_turn(prepare=lambda: events.append("prep1"))
    app.request_turn(prepare=lambda: events.append("prep2"))
    for _ in range(50):
        await asyncio.sleep(0)
        if events.count("run") == 2: break
    # each prepare immediately precedes its own run; prepares never interleave a run
    assert events == ["prep1", "run", "prep2", "run"]
    engine.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await engine


@pytest.mark.anyio
async def test_run_loop_false_mutates_without_starting_a_turn(monkeypatch):
    app = _app(monkeypatch)
    ran = []

    class FakeLoop:
        async def run(self, *, no_tools=False):
            ran.append(1)

    app.chat_loop = FakeLoop()
    engine = asyncio.create_task(app._turn_consumer())
    done = []
    app.request_turn(prepare=lambda: done.append("mutated"), run_loop=False)
    for _ in range(50):
        await asyncio.sleep(0)
        if done: break
    assert done == ["mutated"] and ran == []     # prepare ran; no ChatLoop.run
    engine.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await engine


@pytest.mark.anyio
async def test_ctrl_c_cancels_active_turn_but_preserves_queue(monkeypatch):
    # finding 4: action_cancel cancels only the active turn; queued requests survive.
    app = _app(monkeypatch)
    monkeypatch.setattr(app, "query_one", lambda *a, **k: MagicMock())
    app._activity_timer = None
    app._cancel_event = None
    started = []
    a_in = asyncio.Event()

    class FakeLoop:
        async def run(self, *, no_tools=False):
            started.append("turn")
            if len(started) == 1:
                a_in.set()
                await asyncio.sleep(3600)        # A blocks until cancelled

    app.chat_loop = FakeLoop()
    engine = asyncio.create_task(app._turn_consumer())
    app.request_turn()                            # A (runs, blocks)
    await asyncio.wait_for(a_in.wait(), 1)
    app.request_turn()                            # B queued behind A
    app.action_cancel()                           # Ctrl+C — must NOT drain B
    for _ in range(100):
        await asyncio.sleep(0)
        if len(started) == 2: break
    assert started == ["turn", "turn"]            # B still ran after A was cancelled
    engine.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await engine
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/tui/test_turn_consumer.py -v`
Expected: FAIL — `request_turn`/`_turn_consumer` undefined.

- [ ] **Step 3: Add the consumer to `AyderApp`** — in `src/ayder_cli/tui/app.py`. Add a module-level dataclass (near the top imports add `from dataclasses import dataclass` and `from collections.abc import Callable`):
```python
@dataclass
class TurnRequest:
    prepare: Callable[[], None] | None = None
    run_loop: bool = True
    no_tools: bool = False
```
In `__init__`, **remove** `self._pending_messages: list[str] = []` and `self._is_processing = False` (the single `_requests` queue replaces the user backlog); add:
```python
        self._requests: asyncio.Queue[TurnRequest] = asyncio.Queue()
        self._run_task: asyncio.Task | None = None
        self._cancel_event: asyncio.Event | None = None
```
Add a compatibility property so existing `self._is_processing` reads keep working, plus the consumer:
```python
    @property
    def _is_processing(self) -> bool:
        return self._run_task is not None

    @property
    def is_turn_running(self) -> bool:
        return self._run_task is not None

    async def _turn_consumer(self) -> None:
        while True:
            req = await self._requests.get()
            try:
                if req.prepare is not None:
                    req.prepare()                      # quiescent: no turn running here
            except Exception as e:
                self._report_turn_error(e)
                continue
            if not req.run_loop:
                continue
            self._cancel_event = asyncio.Event()
            self._callbacks._cancel_event = self._cancel_event
            self._run_task = asyncio.create_task(self.chat_loop.run(no_tools=req.no_tools))
            try:
                await self._run_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                self._report_turn_error(e)
            finally:
                self._run_task = None
                self._after_turn_finished()

    def request_turn(self, prepare=None, *, run_loop: bool = True,
                     no_tools: bool = False, interrupt: bool = False) -> None:
        self._requests.put_nowait(TurnRequest(prepare, run_loop, no_tools))
        if interrupt and self._run_task is not None:
            if getattr(self, "_cancel_event", None) is not None:
                self._cancel_event.set()
            self._run_task.cancel()

    def _report_turn_error(self, exc: Exception) -> None:
        try:
            self.query_one("#chat-view", ChatView).add_system_message(f"Error: {exc}")
        except Exception:
            pass
```
Replace `_finish_processing` with `_after_turn_finished` (UI teardown + nudge only; the consumer pulls the next queued request itself, so there is no `_pending_messages` pumping):
```python
    def _after_turn_finished(self) -> None:
        self._maybe_stop_activity_timer()
        try:
            self.query_one("#activity-bar", ActivityBar).clear()
            self.query_one("#input-bar", CLIInputBar).focus_input()
        except Exception:
            pass
        if self._agent_registry:
            self._maybe_nudge()
```
Delete `start_llm_processing` and `_run_chat_loop`. Start the consumer in `on_mount` (after `set_loop`):
```python
        self._engine_task = asyncio.create_task(self._turn_consumer())
```

- [ ] **Step 4: Update `AppCallbacks` cancellation** — in `AppCallbacks.__init__` replace `self._worker = None` with `self._cancel_event = None`. Replace `is_cancelled`:
```python
    def is_cancelled(self) -> bool:
        ev = self._cancel_event
        return ev is not None and ev.is_set()
```

- [ ] **Step 5: Route user input through `request_turn` (single queue)** — there is no separate `_pending_messages` backlog: every user message and command is a `TurnRequest`, so order across messages and commands is unambiguous and the consumer serializes them. The message is **echoed to the UI immediately** but appended to `self.messages` only in `prepare` (when quiescent). `reset_settled()` moves into `prepare` too (finding 5 — otherwise a racing completion repopulates `_settled` before the queued turn starts). Rewrite `handle_input_submitted` and **delete** `_process_next_message`:
```python
    @on(CLIInputBar.Submitted)
    def handle_input_submitted(self, event: CLIInputBar.Submitted) -> None:
        user_input = event.value
        if user_input.startswith("/"):
            self._handle_command(user_input)
            return
        try:
            self.query_one("#chat-view", ChatView).add_user_message(user_input)  # echo now
        except Exception:
            pass

        def _prepare(text=user_input):
            if self._agent_registry:
                self._agent_registry.reset_settled()   # finding 5: at turn-prep, not submit
            self.messages.append({"role": "user", "content": text})

        self.request_turn(prepare=_prepare)
```
Remove the old top-of-`handle_input_submitted` `reset_settled()` call (now in `_prepare`). In `_maybe_nudge` (Task 3), replace `self.start_llm_processing()` with `self.request_turn()`.

- [ ] **Step 6: Rewire `action_cancel`** — cancel the **active turn only**; queued requests survive and proceed (finding 4 / policy §12). Replace the `for worker in self.workers: worker.cancel()` block and remove the `self._pending_messages.clear()` and `self._is_processing = False` lines:
```python
        if getattr(self, "_cancel_event", None) is not None:
            self._cancel_event.set()
        if self._run_task is not None:
            self._run_task.cancel()          # active turn only — do NOT drain self._requests
```
Change the cancel message to `"Turn cancelled."` (drop the "N pending messages cleared" wording — queued requests are no longer discarded).

- [ ] **Step 7: Audit and convert every state-mutating command** (`src/ayder_cli/tui/commands.py`; `do_clear`/`apply_pending_compact` in `app.py`). Finding 2: *every* handler that mutates conversation/provider/model/prompt/tool-tags/permissions/context-manager/registry state — **not only those calling `start_llm_processing`** — defers that work into `prepare`. Handlers that *read* the conversation (`/compact`, `/save-context` build `conversation_text`) defer the **read** into `prepare` too, so a queued command sees post-turn state, not a stale snapshot. Echo any user-visible line via `chat_view` immediately; do all state work in `prepare`. Pattern (`/ask`):
```python
def handle_ask(app, args, chat_view):
    q = args.strip()
    if not q:
        chat_view.add_system_message("Usage: /ask <question>")
        return
    def _prepare():
        app.messages.append({"role": "user", "content": q})
    app.request_turn(prepare=_prepare, no_tools=True)
```
Full classification:

| Command(s) | `request_turn` | `prepare` body (deferred) |
|---|---|---|
| `/ask` | `no_tools=True` | append the question |
| `/plan`, `/implement` | `run_loop=True` | append the command's prompt |
| `/compact` (`handle_compact`) | `run_loop=True` | **read** `conversation_text` from `app.messages`, clear (keep system), append `compact_prompt`, `new_generation()` |
| `/save-context` (`handle_save_context`) | `run_loop=True` | **read** `conversation_text`, append the save prompt (no `new_generation`) |
| `/skill` (`handle_skill`/`_apply_skill`) | `run_loop=True` | `app.inject_skill(...)` (in-place, below), append command, `new_generation()` |
| `/provider` (`_apply_provider_switch`), `/model` (`handle_model`) | `run_loop=False` | rebuild runtime (existing body) + `update_system_prompt_model()` + `new_generation()`; start no turn |
| `/clear` (`do_clear`), `/load-context` (`handle_load_context`) | `run_loop=False` | `/clear`: clear messages (keep system) + `context_manager.clear()` + `new_generation()`. `/load-context`: append the context message (no `new_generation` — append semantics, §8) |
| `/tools`, `/permission`, `/verbose` | `run_loop=False` | mutate `chat_loop.config.tool_tags` / `permissions` / `verbose` |

Read-only / non-turn-state commands run **immediately** on the loop (no `request_turn`): `/help`, `/tasks`, `/notes`, `/list-contexts`, `/context-stats`, `/archive-completed-tasks`, `/logging`, `/plugin`, `/temporal`, `/agent`. (`/agent` reads/cancels registry state on the loop, safe under single-loop ownership — §4 — so no marshalling.)

Notes: `inject_skill` must mutate **in place** — change `self.messages = [...]` (app.py:427) to `self.messages[:] = [...]` so `chat_loop.messages` stays the same list. `do_clear` is called by both `/clear` and Ctrl+L (`action_clear`); wrap its body in the `_prepare` + `request_turn(run_loop=False)` shape so Ctrl+L is serialized too. `apply_pending_compact` already runs inside the chat-loop's pre-iteration hook (on-loop, during a turn) — leave it; its `new_generation()` from Task 8 stays.

- [ ] **Step 8: Migrate Phase-A tests to the property (finding 6)** — `tests/tui/test_pull_delivery.py`'s `_app` helper assigns `app._is_processing`, now a read-only property. Set the backing task instead:
```python
def _app(reg, processing=False):
    from ayder_cli.tui.app import AyderApp
    app = AyderApp.__new__(AyderApp)
    app._agent_registry = reg
    app._run_task = object() if processing else None   # property derives _is_processing
    app.messages = []
    app.request_turn = MagicMock()                      # nudge now calls request_turn
    return app
```
In `test_nudges_once_when_idle_with_unread`, assert on `app.request_turn` instead of `app.start_llm_processing` (and drop the `app.start_llm_processing = MagicMock()` line).

- [ ] **Step 9: Run consumer + tui suites**

Run: `uv run pytest tests/tui/ tests/agents/ -v`
Expected: PASS. Fix any remaining `start_llm_processing`/`_run_chat_loop`/`self.workers`/`_pending_messages`/`_process_next_message`/`_is_processing =` (assignment) references (grep `src/`).

- [ ] **Step 10: Commit**

```bash
git add src/ayder_cli/tui/app.py src/ayder_cli/tui/commands.py tests/tui/test_turn_consumer.py tests/tui/test_pull_delivery.py
git commit -m "feat(tui): serial turn consumer + request_turn; full command audit; Ctrl+C cancels active turn only"
```

---

### Task 10: Full-suite verification

- [ ] **Step 1: Both suites** — `uv run poe check-all && uv run poe test-all`. Expected: ruff clean, mypy clean, all tests pass.

- [ ] **Step 2: Straggler grep** — confirm the old model is gone:

Run: `grep -rnE "AgentSummary|_summary_queue|drain_summaries|has_pending_summaries|_wake_for_pending_agents|_parse_summary|start_llm_processing|_run_chat_loop|_pending_messages|_process_next_message|self\._is_processing\s*=" src/`
Expected: no matches (the `_is_processing` **property** definition is allowed; only assignments must be gone).

- [ ] **Step 3: Commit fixups**

```bash
git add -A && git commit -m "chore: full-suite green for agent-result pull delivery"
```

---

## Self-Review

**Spec coverage:** `AgentRun` + status vocab (Task 3 / §3). Single-loop ownership: `_on_loop`, `await_run`, loop-side mutation (Tasks 3-4 / §4). Pull tools + capped `timeout_s` + CLI/TUI registration (Tasks 4-5 / §5). Capability prompt (Task 6 / §5). Serial consumer + `prepare` deferral + Ctrl+C (Task 9 / §6, §12). Event+timer nudges, `nudged`-after-enqueue, no loop (Tasks 3/9 / §7, findings A/D). Generation filter, no run dropping (Tasks 3/8 / §8, finding 1). Data flow (Tasks 3-4 / §9). Notes = durable copy, auto-written (Tasks 1-2 / §10, finding C). Deletions (Tasks 3/9 / §11). CLI registration (Task 5 / finding 4). ✓

**rev. 2 finding coverage:** read-while-working no-drain (Task 3 `read_result`/`await_run` + regression test); full command audit incl. deferred reads (Task 9 Step 7 table); `_on_loop` raises + `list_agents` marshals (Tasks 3/4 + test); Ctrl+C preserves queue (Task 9 Step 6 + test); `reset_settled` at prepare time (Task 9 Step 5); Phase-A test migration (Task 9 Step 8). ✓

**Placeholder scan:** none — every code/edit step carries concrete content; command conversions enumerated in a table with the full pattern; no `_pending_messages`/`_process_next_message` survive (single `_requests` queue).

**Type consistency:** `AgentRunOutcome(status, content, error, note_path)` (Task 2) consumed by `_run_and_queue` (Task 3); `AgentRun(run_id, generation, agent_name, started_at, …)` constructed identically in tests/registry; `create_run`/`snapshot`/`read_result`/`await_run`/`pending_nudge`/`mark_nudged`/`new_generation`/`_on_loop` defined in Task 3, consumed in Tasks 4-5/9; `request_turn(prepare=None, *, run_loop=True, no_tools=False, interrupt=False)` defined Task 9, used by user-input/nudge/commands; `_maybe_nudge` defined Task 3, re-pointed to `request_turn` in Task 9; `write_agent_note(..., generation=…)` (Task 1) called by runner (Task 2).
