# Multi-Instance Agent Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow multiple concurrent instances of the same agent type by keying `_active` by run_id instead of agent name.

**Architecture:** Change flows bottom-up: callbacks → runner → registry → AgentPanel → app callbacks → commands/tool. Each layer adds `run_id` to its interface. Registry becomes the single source of run IDs. AgentPanel drops its internal counter and `_active_run` dict.

**Tech Stack:** Python 3.12, asyncio, pytest

**Spec:** `docs/superpowers/specs/2026-03-20-multi-instance-agents-design.md`

---

### File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/ayder_cli/agents/callbacks.py` | Modify | Add `run_id` to `__init__` and `_emit` |
| `src/ayder_cli/agents/runner.py` | Modify | Add `run_id` param, pass to callbacks |
| `src/ayder_cli/agents/registry.py` | Modify | Key `_active` by run_id, return int from dispatch, cancel-all-by-name, `get_running_count` |
| `src/ayder_cli/tui/widgets.py` | Modify | Drop `_active_run`/`_run_counter`, methods take `run_id` |
| `src/ayder_cli/tui/app.py` | Modify | Callbacks receive/pass `run_id` |
| `src/ayder_cli/tui/commands.py` | Modify | Handle int dispatch return, cancel-all, instance count display |
| `src/ayder_cli/agents/tool.py` | Modify | Handle int dispatch return |
| `tests/agents/test_callbacks.py` | Modify | Update for new `_emit` signature |
| `tests/agents/test_registry.py` | Modify | Rewrite dispatch/cancel/active tests for run_id keying |
| `tests/agents/test_runner.py` | Verify | No changes needed — `_make_runner()` uses defaults for `run_id` and `on_progress` |
| `tests/agents/test_integration.py` | Modify | Update batch wakeup test for run_id keying |
| `tests/tui/test_widgets.py` | Modify | Update AgentPanel tests for new signatures |

**Note:** Line numbers are approximate — search for the relevant code pattern if they shift after earlier tasks.

---

### Task 1: Callbacks — Add `run_id` to `AgentCallbacks`

**Files:**
- Modify: `src/ayder_cli/agents/callbacks.py:32-45`
- Test: `tests/agents/test_callbacks.py`

- [ ] **Step 1: Write failing test for new `_emit` signature**

```python
# tests/agents/test_callbacks.py — replace test_on_progress_callback (line 62-74)

    def test_on_progress_callback_includes_run_id(self):
        """on_progress receives (run_id, name, event, data)."""
        events = []
        cancel_event = asyncio.Event()
        cb = AgentCallbacks(
            agent_name="test",
            run_id=42,
            cancel_event=cancel_event,
            on_progress=lambda rid, name, event, data: events.append((rid, name, event, data)),
        )
        cb.on_tool_start("id1", "read_file", {"path": "test.py"})
        assert len(events) == 1
        assert events[0][0] == 42       # run_id
        assert events[0][1] == "test"   # agent_name
        assert events[0][2] == "tool_start"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python3 -m pytest tests/agents/test_callbacks.py::TestAgentCallbacks::test_on_progress_callback_includes_run_id -v --timeout=10`
Expected: FAIL — `__init__() got an unexpected keyword argument 'run_id'`

- [ ] **Step 3: Implement run_id in AgentCallbacks**

In `src/ayder_cli/agents/callbacks.py`, modify `__init__` and `_emit`:

```python
# __init__ (line 32-41) — add run_id parameter after agent_name
def __init__(
    self,
    agent_name: str,
    run_id: int,
    cancel_event: asyncio.Event,
    on_progress: Callable[[int, str, str, Any], None] | None = None,
) -> None:
    self.agent_name = agent_name
    self.run_id = run_id
    self._cancel_event = cancel_event
    self._on_progress = on_progress
    self.last_content: str = ""

# _emit (line 43-45) — pass run_id first
def _emit(self, event: str, data: Any = None) -> None:
    if self._on_progress:
        self._on_progress(self.run_id, self.agent_name, event, data)
```

- [ ] **Step 4: Fix existing tests that construct AgentCallbacks without run_id**

All existing tests in `test_callbacks.py` construct `AgentCallbacks(agent_name="test", cancel_event=cancel_event)`. Add `run_id=0` to every constructor call:

```python
# For every test in TestAgentCallbacks, change:
cb = AgentCallbacks(agent_name="test", cancel_event=cancel_event)
# to:
cb = AgentCallbacks(agent_name="test", run_id=0, cancel_event=cancel_event)
```

Also update the old `test_on_progress_callback` test: replace it with the new `test_on_progress_callback_includes_run_id` from Step 1. The old test asserts 3-element tuples `(name, event, data)` — the new signature produces 4-element tuples `(run_id, name, event, data)`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/agents/test_callbacks.py -v --timeout=10`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/ayder_cli/agents/callbacks.py tests/agents/test_callbacks.py
git commit -m "feat(agents): add run_id to AgentCallbacks and _emit"
```

---

### Task 2: Runner — Add `run_id` parameter to `AgentRunner`

**Files:**
- Modify: `src/ayder_cli/agents/runner.py:30-48,80-84`
- Test: `tests/agents/test_runner.py`

- [ ] **Step 1: Modify AgentRunner.__init__ to accept run_id**

In `src/ayder_cli/agents/runner.py`, add `run_id: int = 0` parameter after `timeout`:

```python
def __init__(
    self,
    agent_config: AgentConfig,
    parent_config: Any,
    project_ctx: Any,
    process_manager: Any,
    permissions: set[str],
    timeout: int = 300,
    run_id: int = 0,
    on_progress: Callable[[int, str, str, Any], None] | None = None,
) -> None:
    self._agent_config = agent_config
    self._parent_config = parent_config
    self._project_ctx = project_ctx
    self._process_manager = process_manager
    self._permissions = permissions
    self._timeout = timeout
    self.run_id = run_id
    self._on_progress = on_progress
    self._cancel_event = asyncio.Event()
    self.status: str = "idle"
```

- [ ] **Step 2: Pass run_id to AgentCallbacks in runner.run()**

In `runner.py`, update the `AgentCallbacks` constructor (line 80-84):

```python
callbacks = AgentCallbacks(
    agent_name=self.agent_name,
    run_id=self.run_id,
    cancel_event=self._cancel_event,
    on_progress=self._on_progress,
)
```

- [ ] **Step 3: Update on_progress type annotation in runner.py**

The `on_progress` type hint on line 38 changes from `Callable[[str, str, Any], None]` to `Callable[[int, str, str, Any], None]`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python3 -m pytest tests/agents/test_runner.py tests/agents/test_callbacks.py -v --timeout=10`
Expected: All PASS (runner tests don't directly test run_id yet, but shouldn't break)

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/agents/runner.py
git commit -m "feat(agents): add run_id parameter to AgentRunner"
```

---

### Task 3: Registry — Key `_active` by run_id, return int from dispatch

**Files:**
- Modify: `src/ayder_cli/agents/registry.py`
- Test: `tests/agents/test_registry.py`

- [ ] **Step 1: Write failing tests for new registry behavior**

Replace/update the following tests in `tests/agents/test_registry.py`:

```python
# REPLACE test_dispatch_returns_status_string (line 93-108)
def test_dispatch_returns_run_id(self, registry):
    """dispatch() returns int run_id on success."""
    mock_loop = MagicMock()
    registry.set_loop(mock_loop)

    with patch("ayder_cli.agents.registry.AgentRunner") as MockRunner, \
         patch("ayder_cli.agents.registry.asyncio.run_coroutine_threadsafe"):
        mock_runner = MockRunner.return_value
        mock_runner.agent_name = "reviewer"

        result = registry.dispatch("reviewer", "Review this")

    assert isinstance(result, int)
    assert result == 1  # first dispatch

# REPLACE test_dispatch_rejects_duplicate (line 110-114)
def test_dispatch_allows_same_agent_twice(self, registry):
    """Same agent can be dispatched concurrently — no duplicate guard."""
    mock_loop = MagicMock()
    registry.set_loop(mock_loop)

    with patch("ayder_cli.agents.registry.AgentRunner") as MockRunner, \
         patch("ayder_cli.agents.registry.asyncio.run_coroutine_threadsafe"):
        mock_runner = MockRunner.return_value
        mock_runner.agent_name = "reviewer"

        run1 = registry.dispatch("reviewer", "task 1")
        run2 = registry.dispatch("reviewer", "task 2")

    assert isinstance(run1, int)
    assert isinstance(run2, int)
    assert run1 != run2
    assert registry.active_count == 2

# REPLACE test_cancel (line 116-123)
def test_cancel_all_by_name(self, registry):
    """cancel() cancels all instances with the given name."""
    mock1 = MagicMock()
    mock1.agent_name = "reviewer"
    mock1.cancel.return_value = True
    mock2 = MagicMock()
    mock2.agent_name = "reviewer"
    mock2.cancel.return_value = True

    registry._active[1] = mock1
    registry._active[2] = mock2

    assert registry.cancel("reviewer") is True
    mock1.cancel.assert_called_once()
    mock2.cancel.assert_called_once()

# REPLACE test_active_count_with_runners (line 160-163)
def test_active_count_with_runners(self, registry):
    mock1 = MagicMock()
    mock1.agent_name = "reviewer"
    mock2 = MagicMock()
    mock2.agent_name = "writer"
    registry._active[1] = mock1
    registry._active[2] = mock2
    assert registry.active_count == 2

# ADD new test
def test_get_running_count(self, registry):
    """get_running_count returns count of active instances by name."""
    mock1 = MagicMock()
    mock1.agent_name = "reviewer"
    mock2 = MagicMock()
    mock2.agent_name = "reviewer"
    registry._active[1] = mock1
    registry._active[2] = mock2
    assert registry.get_running_count("reviewer") == 2
    assert registry.get_running_count("writer") == 0

# ADD new test
def test_get_status_running_aggregate(self, registry):
    """get_status returns 'running' if any instance is active."""
    mock1 = MagicMock()
    mock1.agent_name = "reviewer"
    registry._active[1] = mock1
    assert registry.get_status("reviewer") == "running"

# ADD new test
def test_get_status_settled(self, registry):
    """get_status returns settled status when not running."""
    registry._settled["reviewer"] = "error"
    assert registry.get_status("reviewer") == "error"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/agents/test_registry.py -v --timeout=10`
Expected: FAIL — `dispatch()` returns `str` not `int`, `_active` keyed by name, no `get_running_count`

- [ ] **Step 3: Implement registry changes**

In `src/ayder_cli/agents/registry.py`:

**A) Change `__init__` data model (line 36-50):**
```python
on_progress: Callable[[int, str, str, Any], None] | None = None,
on_complete: Callable[[int, AgentSummary], None] | None = None,
```
```python
self._active: dict[int, AgentRunner] = {}  # run_id -> runner
self._run_counter: int = 0
```

**B) Change `active_count` — no change needed** (still `len(self._active)`).

**C) Change `get_status` (line 64-71):**
```python
def get_status(self, name: str) -> str | None:
    """Get agent status: aggregate across all instances."""
    if name not in self.agents:
        return None
    # Check for any running instance
    for runner in self._active.values():
        if runner.agent_name == name:
            return "running"
    # Check settled status
    if name in self._settled:
        return self._settled[name]
    return "idle"
```

**D) Add `get_running_count` after `get_status`:**
```python
def get_running_count(self, name: str) -> int:
    """Count of currently active instances of the named agent."""
    return sum(1 for r in self._active.values() if r.agent_name == name)
```

**E) Change `dispatch` (line 98-154) — return `int | str`:**
```python
def dispatch(self, name: str, task: str) -> int | str:
    """Fire-and-forget agent dispatch. Thread-safe.

    Returns run_id (int) on success, error message (str) on failure.
    """
    if name not in self.agents:
        return f"Error: Agent '{name}' not found in configured agents"
    # Re-dispatch guard: block agents that failed in this cycle
    if name in self._settled and self._settled[name] in ("error", "timeout"):
        return (
            f"Error: Agent '{name}' failed in this cycle "
            f"(status: {self._settled[name]}). Handle the task directly."
        )

    self._run_counter += 1
    run_id = self._run_counter

    runner = AgentRunner(
        agent_config=self.agents[name],
        parent_config=self._parent_config,
        project_ctx=self._project_ctx,
        process_manager=self._process_manager,
        permissions=self._permissions,
        timeout=self._agent_timeout,
        run_id=run_id,
        on_progress=self._on_progress,
    )
    self._active[run_id] = runner

    async def _run_and_queue():
        result: AgentSummary | None = None
        try:
            result = await runner.run(task)
            await self._summary_queue.put(result)
        finally:
            self._active.pop(run_id, None)
            if result is not None:
                self._settled[name] = result.status
            if self._on_complete is not None and result is not None:
                try:
                    self._on_complete(run_id, result)
                except Exception:
                    logger.exception("on_complete callback failed")

    # Schedule on event loop (thread-safe)
    if self._loop is None:
        self._active.pop(run_id, None)
        return "Error: Agent registry not initialized (event loop not set)"
    asyncio.run_coroutine_threadsafe(_run_and_queue(), self._loop)

    return run_id
```

**F) Change `cancel` (line 156-161):**
```python
def cancel(self, name: str) -> bool:
    """Cancel all running instances of the named agent. Returns True if any cancelled."""
    to_cancel = [rid for rid, r in self._active.items() if r.agent_name == name]
    for rid in to_cancel:
        self._active[rid].cancel()
    return len(to_cancel) > 0
```

- [ ] **Step 4: Fix remaining test assertions**

Update `test_on_complete_called_after_agent_finishes` (line 166-197):
- The `on_complete` callback now receives `(run_id, summary)` instead of just `(summary)`.
- Change: `callback.assert_called_once_with(summary)` → `callback.assert_called_once_with(1, summary)`
- Change: `assert "reviewer" not in reg._active` → `assert 1 not in reg._active`

Update `test_settled_allows_completed_agent_redispatch` (line 211-221):
- `dispatch()` now returns `int` on success, not `str`. Change:
  `assert "dispatched" in result.lower()` → `assert isinstance(result, int)`

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/agents/test_registry.py -v --timeout=10`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/ayder_cli/agents/registry.py tests/agents/test_registry.py
git commit -m "feat(agents): key _active by run_id, return int from dispatch"
```

---

### Task 4: Integration Test — Update batch wakeup test

**Files:**
- Modify: `tests/agents/test_integration.py:115-157`

- [ ] **Step 1: Update batch wakeup test for run_id keying**

In `tests/agents/test_integration.py`, update `test_batch_wakeup_pattern_only_fires_when_all_agents_complete` (line 116-157):

```python
@pytest.mark.anyio
async def test_batch_wakeup_pattern_only_fires_when_all_agents_complete():
    """Validates the batch wake-up pattern: only trigger when active_count == 0."""
    from ayder_cli.agents.config import AgentConfig
    from ayder_cli.agents.registry import AgentRegistry
    from ayder_cli.agents.summary import AgentSummary
    from unittest.mock import MagicMock

    wakeup_calls = []

    def on_complete(run_id, summary):
        # This is the pattern app.py will use
        if reg.active_count == 0:
            wakeup_calls.append(summary)

    configs = {
        "a": AgentConfig(name="a", system_prompt="agent a"),
        "b": AgentConfig(name="b", system_prompt="agent b"),
    }
    reg = AgentRegistry(
        agents=configs,
        parent_config=MagicMock(),
        project_ctx=MagicMock(),
        process_manager=MagicMock(),
        permissions={"r"},
        on_complete=on_complete,
    )

    mock_a = MagicMock()
    mock_a.agent_name = "a"
    mock_b = MagicMock()
    mock_b.agent_name = "b"
    reg._active[1] = mock_a
    reg._active[2] = mock_b

    summary_a = AgentSummary(agent_name="a", status="completed", summary="done a", error=None)
    await reg._summary_queue.put(summary_a)
    reg._active.pop(1)
    on_complete(1, summary_a)
    assert len(wakeup_calls) == 0  # b is still running

    summary_b = AgentSummary(agent_name="b", status="completed", summary="done b", error=None)
    await reg._summary_queue.put(summary_b)
    reg._active.pop(2)
    on_complete(2, summary_b)
    assert len(wakeup_calls) == 1  # Now all done, wake up fires
```

**Do NOT update `test_config_to_dispatch_flow` here.** That test calls `handler()` from `tool.py`, which still wraps `dispatch()` and returns the raw result. At this point `dispatch()` returns `int`, so `handler()` also returns `int`. But Task 7 changes the handler to convert `int` → string. The integration test assertion must be updated in Task 7 together with the handler change, not here.

- [ ] **Step 2: Run tests**

Run: `.venv/bin/python3 -m pytest tests/agents/test_integration.py -v --timeout=10`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add tests/agents/test_integration.py
git commit -m "test(agents): update integration tests for run_id keying"
```

---

### Task 5: AgentPanel — Drop `_active_run`, methods take `run_id`

**Files:**
- Modify: `src/ayder_cli/tui/widgets.py:697-828`
- Test: `tests/tui/test_widgets.py`

- [ ] **Step 1: Update tests for new AgentPanel signatures**

In `tests/tui/test_widgets.py`, update the `TestAgentPanelDataModel` tests:

```python
class TestAgentPanelDataModel:
    @patch.object(AgentPanel, "mount")
    def test_add_agent_creates_entry(self, mock_mount):
        panel = AgentPanel()
        panel.add_agent("code_reviewer", run_id=1)
        assert 1 in panel._entries
        assert panel._entries[1].name == "code_reviewer"
        assert panel._entries[1].completed is False
        mock_mount.assert_called_once()

    @patch.object(AgentPanel, "mount")
    def test_add_agent_multiple_entries(self, mock_mount):
        panel = AgentPanel()
        panel.add_agent("agent_a", run_id=1)
        panel.add_agent("agent_b", run_id=2)
        assert len(panel._entries) == 2

    @patch.object(AgentPanel, "mount")
    def test_redispatch_creates_second_entry(self, mock_mount):
        panel = AgentPanel()
        panel.add_agent("code_reviewer", run_id=1)
        panel.add_agent("code_reviewer", run_id=2)
        assert 1 in panel._entries
        assert 2 in panel._entries
        assert len(panel._entries) == 2

    @patch("ayder_cli.tui.widgets.Static.add_class")
    @patch("ayder_cli.tui.widgets.Static.remove_class")
    @patch("ayder_cli.tui.widgets.Static.update")
    @patch.object(AgentPanel, "scroll_end")
    @patch.object(AgentPanel, "mount")
    def test_complete_agent_marks_completed(self, mock_mount, mock_scroll, mock_update, mock_remove_class, mock_add_class):
        panel = AgentPanel()
        panel.add_agent("web_parser", run_id=5)
        panel.complete_agent(5, "Found 3 results", "completed")
        assert panel._entries[5].completed is True

    @patch("ayder_cli.tui.widgets.Static.add_class")
    @patch("ayder_cli.tui.widgets.Static.remove_class")
    @patch("ayder_cli.tui.widgets.Static.update")
    @patch.object(AgentPanel, "scroll_end")
    @patch.object(AgentPanel, "mount")
    def test_complete_agent_stores_detail(self, mock_mount, mock_scroll, mock_update, mock_remove_class, mock_add_class):
        panel = AgentPanel()
        panel.add_agent("web_parser", run_id=5)
        panel.complete_agent(5, "Full summary text here", "completed")
        assert panel._entries[5].detail_widget is not None

    def test_complete_unknown_run_id_is_noop(self):
        panel = AgentPanel()
        panel.complete_agent(999, "summary", "completed")

    @patch.object(AgentPanel, "mount")
    def test_update_agent_unknown_creates_entry(self, mock_mount):
        panel = AgentPanel()
        panel.update_agent(42, "auto_created", "thinking_start")
        assert 42 in panel._entries

    @patch("ayder_cli.tui.widgets.Static.add_class")
    @patch("ayder_cli.tui.widgets.Static.remove_class")
    @patch("ayder_cli.tui.widgets.Static.update")
    @patch.object(AgentPanel, "scroll_end")
    @patch.object(AgentPanel, "mount")
    def test_prune_at_50_entries(self, mock_mount, mock_scroll, mock_update, mock_remove_class, mock_add_class):
        panel = AgentPanel()
        for i in range(50):
            panel.add_agent(f"agent_{i}", run_id=i + 1)
            panel.complete_agent(i + 1, f"summary {i}", "completed")
        assert len(panel._entries) == 50
        # 51st should prune oldest completed
        oldest_run_id = next(iter(panel._entries))
        panel._entries[oldest_run_id].status_widget.remove = MagicMock()
        if panel._entries[oldest_run_id].detail_widget:
            panel._entries[oldest_run_id].detail_widget.remove = MagicMock()
        panel.add_agent("agent_50", run_id=51)
        assert len(panel._entries) == 50
        assert oldest_run_id not in panel._entries
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/tui/test_widgets.py -v --timeout=10`
Expected: FAIL — `add_agent()` doesn't accept `run_id`, `complete_agent()` still takes name

- [ ] **Step 3: Implement AgentPanel changes**

In `src/ayder_cli/tui/widgets.py`, modify the `AgentPanel` class:

**A) Remove `_run_counter` and `_active_run` from `__init__` (line 697-702):**
```python
def __init__(self, **kwargs):
    super().__init__(**kwargs)
    self._user_visible: bool = False
    self._entries: dict[int, _AgentEntry] = {}
```

**B) Change `add_agent` signature (line 718-737):**
```python
def add_agent(self, name: str, run_id: int) -> None:
    """Add a new agent run entry. Never auto-shows the panel."""
    self._prune_if_needed()

    text = Text()
    text.append("  ▶ ", style="bold yellow")
    text.append(f"{name}", style="bold magenta")
    text.append(" running...", style="dim")

    status_widget = Static(text, classes="agent-status running")
    entry = _AgentEntry(
        status_widget=status_widget,
        detail_widget=None,
        name=name,
    )
    self._entries[run_id] = entry
    self.mount(status_widget)
```

**C) Change `complete_agent` to take `run_id` (line 739-772):**
```python
def complete_agent(self, run_id: int, summary: str, status: str = "completed") -> None:
    """Mark agent as completed with full summary. Lookup by run_id."""
    if run_id not in self._entries:
        return
    entry = self._entries[run_id]
    if entry.completed:
        return
    entry.completed = True

    # Update status line
    text = Text()
    if status == "completed":
        text.append("  ✓ ", style="bold green")
    elif status == "timeout":
        text.append("  ⏱ ", style="bold yellow")
    else:
        text.append("  ✗ ", style="bold red")
    text.append(f"{entry.name}", style="bold")
    preview = summary[:80] + "..." if len(summary) > 80 else summary
    text.append(f" — {preview}", style="dim")
    entry.status_widget.update(text)
    entry.status_widget.remove_class("running")
    status_class = "completed" if status == "completed" else status
    entry.status_widget.add_class(status_class)

    # Add detail block with full summary
    detail = Static(
        Text(f"    {summary}", style="dim"),
        classes="agent-detail",
    )
    entry.detail_widget = detail
    self.mount(detail, after=entry.status_widget)
    self.scroll_end(animate=False)
```

**D) Change `update_agent` to take `run_id` and `name` (line 774-790):**
```python
def update_agent(self, run_id: int, name: str, event: str, data: Any = None) -> None:
    """Handle an agent progress event. Lookup by run_id."""
    if run_id not in self._entries:
        self.add_agent(name, run_id)

    entry = self._entries.get(run_id)
    if entry is None or entry.completed:
        return

    if event == "tool_start" and isinstance(data, dict):
        tool_name = data.get("name", "?")
        self._update_status(entry, f"Running tool: {tool_name}")
    elif event == "thinking_start":
        self._update_status(entry, "Thinking...")
    elif event == "tools_cleanup":
        self._update_status(entry, "Processing...")
```

**E) Change `remove_agent` to take `run_id` (line 792-802):**
```python
def remove_agent(self, run_id: int) -> None:
    """Remove an agent entry from the panel by run_id. Does not affect visibility."""
    if run_id in self._entries:
        entry = self._entries[run_id]
        entry.status_widget.remove()
        if entry.detail_widget:
            entry.detail_widget.remove()
        del self._entries[run_id]
```

**F) Simplify `_prune_if_needed` (line 812-828) — remove `_active_run` references:**
```python
def _prune_if_needed(self) -> None:
    """Remove oldest completed entry if at capacity."""
    if len(self._entries) < self.MAX_ENTRIES:
        return
    to_prune = None
    for run_id, entry in self._entries.items():
        if entry.completed:
            to_prune = run_id
            break
    if to_prune is not None:
        entry = self._entries[to_prune]
        entry.status_widget.remove()
        if entry.detail_widget:
            entry.detail_widget.remove()
        del self._entries[to_prune]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/tui/test_widgets.py -v --timeout=10`
Expected: All PASS

- [ ] **Step 4b: Update `_agent_progress` callback in app.py**

**Important:** AgentPanel signatures changed above. `app.py` must be updated in the same commit to avoid broken intermediate state.

In `src/ayder_cli/tui/app.py`, find `_agent_progress` (line 208). Change signature and body:

```python
def _agent_progress(run_id, name, event, data):
    """Forward agent events to AgentPanel and sync activity bar."""
    try:
        panel = self.query_one("#agent-panel", AgentPanel)
        self.call_later(lambda: panel.update_agent(run_id, name, event, data))
    except Exception:
        pass
    # Keep activity bar agent count in sync and ensure spinner animates
    try:
        activity = self.query_one("#activity-bar", ActivityBar)
        count = self._agent_registry.active_count if self._agent_registry else 0
        self.call_later(lambda: activity.set_agents_running(count))
        self.call_later(self._start_activity_timer)
    except Exception:
        pass
```

- [ ] **Step 2: Update `_agent_complete` callback**

In `src/ayder_cli/tui/app.py`, find `_agent_complete` (line 224). Change signature and body:

```python
def _agent_complete(run_id, summary):
    """Handle agent completion: update UI and wake LLM if all done."""
    try:
        panel = self.query_one("#agent-panel", AgentPanel)
        self.call_later(
            lambda: panel.complete_agent(run_id, summary.summary, summary.status)
        )
    except Exception:
        pass

    # Update activity bar
    try:
        activity = self.query_one("#activity-bar", ActivityBar)
        count = self._agent_registry.active_count if self._agent_registry else 0
        self.call_later(lambda: activity.set_agents_running(count))
    except Exception:
        pass

    # Batch wake-up: only trigger LLM when ALL agents are done.
    if self._agent_registry and self._agent_registry.active_count == 0:
        if not self._is_processing:
            summaries = self._agent_registry.drain_summaries()
            for s in summaries:
                self.messages.append({"role": "system", "content": s.format_for_injection()})
            self.call_later(lambda: self.start_llm_processing())
```

- [ ] **Step 3: Run full test suite**

Run: `.venv/bin/python3 -m pytest tests/ --timeout=10 -q`
Expected: All tests pass

- [ ] **Step 5: Commit (widgets + app together)**

```bash
git add src/ayder_cli/tui/widgets.py tests/tui/test_widgets.py src/ayder_cli/tui/app.py
git commit -m "feat(tui): AgentPanel takes run_id, app callbacks pass run_id"
```

---

### Task 6: Commands and Tool Handler — Handle int dispatch return

**Files:**
- Modify: `src/ayder_cli/tui/commands.py:925-992`
- Modify: `src/ayder_cli/agents/tool.py:54-55`

- [ ] **Step 1: Update `/agent` command handler dispatch**

In `src/ayder_cli/tui/commands.py`, update the dispatch section (line 974-991):

```python
# Show agent in panel and dispatch (sync, fire-and-forget)
result = app._agent_registry.dispatch(agent_name, task)

if isinstance(result, int):
    # Success — run_id returned
    run_id = result
    try:
        agent_panel = app.query_one("#agent-panel", AgentPanel)
        agent_panel.add_agent(agent_name, run_id)
    except Exception:
        pass

    task_preview = task[:80] + "..." if len(task) > 80 else task
    chat_view.add_system_message(
        f"Agent '{agent_name}' dispatched with task: {task_preview}\n"
        f"The agent is running in the background. "
        f"You will receive its summary when it completes."
    )
else:
    # Error — error string returned
    chat_view.add_system_message(result)
```

Note: Remove the old `agent_panel.add_agent(agent_name)` call that happened BEFORE dispatch (line 976-979). Now `add_agent` happens AFTER dispatch succeeds, with the run_id.

- [ ] **Step 2: Update `/agent list` to show instance count**

In `src/ayder_cli/tui/commands.py`, update the list section (line 940-950):

```python
if subcommand == "list":
    agents = app._agent_registry.agents
    if not agents:
        chat_view.add_system_message("No agents configured.")
        return
    lines = ["Configured agents:"]
    for name in agents:
        status = app._agent_registry.get_status(name)
        count = app._agent_registry.get_running_count(name)
        if count > 1:
            lines.append(f"  {name}: {status} ({count} instances)")
        else:
            lines.append(f"  {name}: {status}")
    chat_view.add_system_message("\n".join(lines))
    return
```

- [ ] **Step 3: Update tool handler**

In `src/ayder_cli/agents/tool.py`, update `handle_call_agent` (line 54-55):

```python
def handle_call_agent(*, name: str, task: str) -> str:
    result = registry.dispatch(name, task)
    if isinstance(result, int):
        task_preview = task[:80] + "..." if len(task) > 80 else task
        return (
            f"Agent '{name}' dispatched successfully with task: {task_preview}\n"
            f"The agent is running in the background. "
            f"You will receive its summary when it completes."
        )
    return result  # error string
```

- [ ] **Step 4: Fix `test_config_to_dispatch_flow` integration test**

Now that `handle_call_agent` converts `int` to string, the integration test must assert the string result. In `tests/agents/test_integration.py`, the assertion at line 60 (`assert "dispatched" in result.lower()`) should still work because the handler now returns `f"Agent '{name}' dispatched successfully..."`. Verify the test passes as-is — no change needed if the assertion already matches.

- [ ] **Step 5: Run full test suite**

Run: `.venv/bin/python3 -m pytest tests/ --timeout=10 -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/ayder_cli/tui/commands.py src/ayder_cli/agents/tool.py tests/agents/test_integration.py
git commit -m "feat(agents): handle int dispatch return in commands and tool handler"
```

---

### Task 7: Lint, Type-Check, and Final Verification

**Files:**
- All modified files

- [ ] **Step 1: Run ruff linter**

Run: `.venv/bin/python3 -m ruff check src/ayder_cli/agents/callbacks.py src/ayder_cli/agents/runner.py src/ayder_cli/agents/registry.py src/ayder_cli/agents/tool.py src/ayder_cli/tui/widgets.py src/ayder_cli/tui/app.py src/ayder_cli/tui/commands.py`
Expected: No errors. If any, fix them.

- [ ] **Step 2: Run mypy type checker**

Run: `.venv/bin/python3 -m mypy src/ayder_cli/agents/callbacks.py src/ayder_cli/agents/runner.py src/ayder_cli/agents/registry.py --ignore-missing-imports`
Expected: No errors. If any, fix type annotations.

- [ ] **Step 3: Run full test suite**

Run: `.venv/bin/python3 -m pytest tests/ --timeout=10 -q`
Expected: All 1062+ tests pass, 0 failures

- [ ] **Step 4: Commit any lint/type fixes**

```bash
git add -u
git commit -m "fix: lint and type fixes for multi-instance agents"
```
