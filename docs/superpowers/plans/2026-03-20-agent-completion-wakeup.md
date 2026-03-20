# Agent Completion Wake-up & Batch Coordination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the main LLM automatically react when agents complete, with batch coordination for parallel dispatches and a re-dispatch guard to prevent infinite loops.

**Architecture:** Add `on_complete` callback to `AgentRegistry` that fires after each agent finishes. The app wires this to a handler that only triggers main LLM processing when ALL active agents have completed. A `_settled` dict tracks recent agent outcomes to block re-dispatch of failed agents within the same user cycle.

**Tech Stack:** Python 3.12, asyncio, Textual (TUI framework), pytest with anyio

**Spec:** `docs/superpowers/specs/2026-03-20-agent-completion-wakeup-design.md`

---

### Task 1: Add `on_complete` callback and `active_count` to AgentRegistry

**Files:**
- Modify: `src/ayder_cli/agents/registry.py:28-47` (constructor + new property)
- Test: `tests/agents/test_registry.py`

- [ ] **Step 1: Write tests for `on_complete` callback and `active_count`**

Add these tests to `tests/agents/test_registry.py` inside `TestAgentRegistry`:

```python
def test_on_complete_callback_received(self, agent_configs):
    """on_complete is stored and accessible."""
    callback = MagicMock()
    reg = AgentRegistry(
        agents=agent_configs,
        parent_config=MagicMock(),
        project_ctx=MagicMock(),
        process_manager=MagicMock(),
        permissions={"r"},
        agent_timeout=300,
        on_complete=callback,
    )
    assert reg._on_complete is callback

def test_active_count_empty(self, registry):
    assert registry.active_count == 0

def test_active_count_with_runners(self, registry):
    registry._active["reviewer"] = MagicMock()
    registry._active["writer"] = MagicMock()
    assert registry.active_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/agents/test_registry.py::TestAgentRegistry::test_on_complete_callback_received tests/agents/test_registry.py::TestAgentRegistry::test_active_count_empty tests/agents/test_registry.py::TestAgentRegistry::test_active_count_with_runners -v`
Expected: FAIL — `on_complete` param doesn't exist, `active_count` property doesn't exist

- [ ] **Step 3: Implement `on_complete` parameter and `active_count` property**

In `src/ayder_cli/agents/registry.py`, modify `__init__` to add `on_complete` parameter (line 36, after `on_progress`):

```python
def __init__(
    self,
    agents: dict[str, AgentConfig],
    parent_config: Any,
    project_ctx: Any,
    process_manager: Any,
    permissions: set[str],
    agent_timeout: int = 300,
    on_progress: Callable[[str, str, Any], None] | None = None,
    on_complete: Callable[[AgentSummary], None] | None = None,
) -> None:
    self.agents = agents
    self._parent_config = parent_config
    self._project_ctx = project_ctx
    self._process_manager = process_manager
    self._permissions = permissions
    self._agent_timeout = agent_timeout
    self._on_progress = on_progress
    self._on_complete = on_complete
    self._loop: asyncio.AbstractEventLoop | None = None
    self._active: dict[str, AgentRunner] = {}
    self._summary_queue: asyncio.Queue[AgentSummary] = asyncio.Queue()
```

Add `active_count` property after `set_loop` (after line 54):

```python
@property
def active_count(self) -> int:
    """Number of currently running agents."""
    return len(self._active)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/agents/test_registry.py -v`
Expected: ALL PASS (including existing tests)

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/agents/registry.py tests/agents/test_registry.py
git commit -m "feat(agents): add on_complete callback and active_count to AgentRegistry"
```

---

### Task 2: Fire `on_complete` from `_run_and_queue`

**Files:**
- Modify: `src/ayder_cli/agents/registry.py:104-109` (`_run_and_queue` closure)
- Test: `tests/agents/test_registry.py`

- [ ] **Step 1: Write test for `on_complete` being called after agent run**

Add to `tests/agents/test_registry.py`:

```python
@pytest.mark.anyio
async def test_on_complete_called_after_agent_finishes(self, agent_configs):
    """on_complete callback fires after agent completes and is removed from _active."""
    callback = MagicMock()
    reg = AgentRegistry(
        agents=agent_configs,
        parent_config=MagicMock(),
        project_ctx=MagicMock(),
        process_manager=MagicMock(),
        permissions={"r"},
        agent_timeout=300,
        on_complete=callback,
    )
    loop = asyncio.get_running_loop()
    reg.set_loop(loop)

    summary = AgentSummary(
        agent_name="reviewer", status="completed", summary="Done.", error=None
    )

    with patch("ayder_cli.agents.registry.AgentRunner") as MockRunner:
        mock_runner = MockRunner.return_value
        mock_runner.agent_name = "reviewer"
        mock_runner.run = AsyncMock(return_value=summary)

        reg.dispatch("reviewer", "Review code")

        # Allow the scheduled coroutine to run
        await asyncio.sleep(0.1)

    callback.assert_called_once_with(summary)
    # Agent should be removed from _active
    assert "reviewer" not in reg._active
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/agents/test_registry.py::TestAgentRegistry::test_on_complete_called_after_agent_finishes -v`
Expected: FAIL — callback is never called

- [ ] **Step 3: Modify `_run_and_queue` to call `on_complete`**

In `src/ayder_cli/agents/registry.py`, update the `_run_and_queue` closure inside `dispatch()` (lines 104-109):

```python
async def _run_and_queue():
    try:
        summary = await runner.run(task)
        await self._summary_queue.put(summary)
    finally:
        self._active.pop(name, None)
        if self._on_complete is not None:
            try:
                self._on_complete(summary)
            except Exception:
                logger.exception("on_complete callback failed")
```

Note: `summary` is defined in the `try` block. If `runner.run()` raises, we still reach `finally` but `summary` won't be defined. We need a local to handle this.

**Atomicity note:** `_active.pop` and `_on_complete` must NOT be separated by an `await`. Both are sync operations running in an async context on Textual's event loop, so they execute atomically within a single event loop tick. This ensures `active_count` is accurate when `on_complete` fires. Add a comment in the code:

```python
async def _run_and_queue():
    result: AgentSummary | None = None
    try:
        result = await runner.run(task)
        await self._summary_queue.put(result)
    finally:
        # These two operations must stay together without an await between
        # them to ensure active_count is accurate when on_complete fires
        self._active.pop(name, None)
        if self._on_complete is not None and result is not None:
            try:
                self._on_complete(result)
            except Exception:
                logger.exception("on_complete callback failed")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/agents/test_registry.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/agents/registry.py tests/agents/test_registry.py
git commit -m "feat(agents): fire on_complete callback after agent finishes"
```

---

### Task 3: Add `_settled` re-dispatch guard to AgentRegistry

**Files:**
- Modify: `src/ayder_cli/agents/registry.py:82-122` (`dispatch` method + new `_settled` dict + `reset_settled`)
- Test: `tests/agents/test_registry.py`

- [ ] **Step 1: Write tests for re-dispatch guard**

Add to `tests/agents/test_registry.py`:

```python
def test_settled_blocks_failed_agent_redispatch(self, registry):
    """Cannot re-dispatch an agent that errored in this cycle."""
    registry._settled = {"reviewer": "error"}
    result = registry.dispatch("reviewer", "try again")
    assert "failed in this cycle" in result.lower() or "handle the task directly" in result.lower()

def test_settled_blocks_timed_out_agent_redispatch(self, registry):
    """Cannot re-dispatch an agent that timed out in this cycle."""
    registry._settled = {"reviewer": "timeout"}
    result = registry.dispatch("reviewer", "try again")
    assert "failed in this cycle" in result.lower() or "handle the task directly" in result.lower()

def test_settled_allows_completed_agent_redispatch(self, registry):
    """Can re-dispatch an agent that completed successfully."""
    registry._settled = {"reviewer": "completed"}
    mock_loop = MagicMock()
    registry.set_loop(mock_loop)

    with patch("ayder_cli.agents.registry.AgentRunner"), \
         patch("ayder_cli.agents.registry.asyncio.run_coroutine_threadsafe"):
        result = registry.dispatch("reviewer", "run again")

    assert "dispatched" in result.lower()

def test_reset_settled(self, registry):
    """reset_settled clears the settled tracker."""
    registry._settled = {"reviewer": "error", "writer": "completed"}
    registry.reset_settled()
    assert registry._settled == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/agents/test_registry.py::TestAgentRegistry::test_settled_blocks_failed_agent_redispatch tests/agents/test_registry.py::TestAgentRegistry::test_settled_blocks_timed_out_agent_redispatch tests/agents/test_registry.py::TestAgentRegistry::test_settled_allows_completed_agent_redispatch tests/agents/test_registry.py::TestAgentRegistry::test_reset_settled -v`
Expected: FAIL — `_settled` doesn't exist

- [ ] **Step 3: Implement `_settled` dict, guard in `dispatch()`, and `reset_settled()`**

In `__init__`, add after `self._summary_queue` line:

```python
self._settled: dict[str, str] = {}
```

In `dispatch()`, add check after the `_active` duplicate check (after line 91):

```python
# Re-dispatch guard: block agents that failed in this cycle
if name in self._settled and self._settled[name] in ("error", "timeout"):
    return (
        f"Error: Agent '{name}' failed in this cycle "
        f"(status: {self._settled[name]}). Handle the task directly."
    )
```

In `_run_and_queue`, update the `finally` block to record settled status:

```python
finally:
    self._active.pop(name, None)
    if result is not None:
        self._settled[name] = result.status
    if self._on_complete is not None and result is not None:
        try:
            self._on_complete(result)
        except Exception:
            logger.exception("on_complete callback failed")
```

Add `reset_settled()` method after `cancel()`:

```python
def reset_settled(self) -> None:
    """Clear the settled tracker. Call on new user message cycle."""
    self._settled = {}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/agents/test_registry.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/agents/registry.py tests/agents/test_registry.py
git commit -m "feat(agents): add re-dispatch guard to prevent infinite agent loops"
```

---

### Task 4: Add agent count indicator to ActivityBar

**Files:**
- Modify: `src/ayder_cli/tui/widgets.py:277-361` (ActivityBar class)
- Test: `tests/tui/test_widgets.py` (or create if needed)

- [ ] **Step 1: Write tests for `set_agents_running`**

Check if widget tests exist:

```bash
ls tests/tui/test_widgets.py 2>/dev/null || echo "does not exist"
```

Create or add to `tests/tui/test_widgets.py`:

```python
"""Tests for ActivityBar agent indicator."""

from ayder_cli.tui.widgets import ActivityBar


class TestActivityBarAgents:
    def test_set_agents_running_stores_count(self):
        bar = ActivityBar()
        bar.set_agents_running(3)
        assert bar._agents_running == 3

    def test_set_agents_running_zero(self):
        bar = ActivityBar()
        bar.set_agents_running(3)
        bar.set_agents_running(0)
        assert bar._agents_running == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/tui/test_widgets.py::TestActivityBarAgents -v`
Expected: FAIL — `set_agents_running` doesn't exist

- [ ] **Step 3: Implement `set_agents_running` on ActivityBar**

In `src/ayder_cli/tui/widgets.py`, modify `ActivityBar.__init__` (line 286-294) to add:

```python
self._agents_running = 0
```

Add method after `set_tools_working` (after line 315):

```python
def set_agents_running(self, count: int) -> None:
    """Show or hide the agents running indicator."""
    self._agents_running = count
    self._refresh_display()
```

Update `_refresh_display` (line 323). Strategy: compute the base label and spinner from existing logic, then prepend agent text once at the end. This avoids repeating `if agent_text:` in every branch:

```python
def _refresh_display(self) -> None:
    """Update the displayed text based on current state."""
    if not self._widget:
        return

    # Determine the LLM activity label and spinner
    label: Text | None = None
    spinner = None

    if self._thinking and self._tools_working:
        label = Text.assemble(
            ("Thinking... ", "bold yellow"), ("| ", "dim"), ("Tools Working...", "bold yellow"),
        )
        spinner = self._thinking_spinner
    elif self._thinking:
        label = Text("Thinking...")
        spinner = self._thinking_spinner
    elif self._generating and self._tools_working:
        label = Text.assemble(
            ("Generating... ", "bold green"), ("| ", "dim"), ("Tools Working...", "bold yellow"),
        )
        spinner = self._tools_spinner
    elif self._generating:
        label = Text("Generating...")
        spinner = self._generating_spinner
    elif self._tools_working:
        label = Text("Tools Working...")
        spinner = self._tools_spinner

    # Build agent prefix
    agent_prefix = (
        Text(f"Agents running ({self._agents_running}) ", style="bold cyan")
        if self._agents_running > 0 else None
    )

    if label and agent_prefix:
        # Both agent and LLM activity
        spinner.text = Text.assemble(agent_prefix, ("| ", "dim"), label)
        self._widget.update(spinner)
    elif label:
        # LLM activity only
        spinner.text = label
        self._widget.update(spinner)
    elif agent_prefix:
        # Agents only, no LLM — show with spinner
        self._thinking_spinner.text = agent_prefix
        self._widget.update(self._thinking_spinner)
    else:
        self._widget.update("")
```

**Important:** Do NOT reset `_agents_running` in `clear()`. The `clear()` method is called by `_finish_processing` in `app.py` (line 624) whenever the LLM finishes a response. If agents are still running when the LLM finishes, `clear()` would prematurely hide the indicator. Agent count is managed exclusively by `set_agents_running()`.

Also update `clear()` (line 354) to call `_refresh_display()` instead of blanking the widget directly. This ensures the agent indicator survives LLM completion:

```python
def clear(self) -> None:
    """Reset LLM activity state. Agent indicator preserved via _refresh_display."""
    self._thinking = False
    self._generating = False
    self._tools_working = False
    self._refresh_display()  # Shows agent indicator if agents still running, else blanks
```

Also update `update_spinners` (line 317) to account for agent activity:

```python
def update_spinners(self) -> None:
    """Re-render spinners (call on a timer)."""
    if (not self._thinking and not self._generating
            and not self._tools_working and self._agents_running == 0):
        return
    self._refresh_display()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/tui/test_widgets.py::TestActivityBarAgents -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/tui/widgets.py tests/tui/test_widgets.py
git commit -m "feat(tui): add agent count indicator to ActivityBar"
```

---

### Task 5: Wire `on_complete` and batch wake-up in AyderApp

**Files:**
- Modify: `src/ayder_cli/tui/app.py:204-233` (agent registry init), `src/ayder_cli/tui/app.py:546-558` (handle_input_submitted), `src/ayder_cli/tui/app.py:560-564` (_process_next_message)
- Test: `tests/agents/test_integration.py` (add integration test)

This is the core wiring task. No new files — just connecting pieces in `app.py`.

- [ ] **Step 1: Write pattern validation test for batch wake-up**

This test validates the callback pattern that `app.py` will implement. It passes immediately since it tests standalone logic, not wired code. Add to `tests/agents/test_integration.py`:

```python
@pytest.mark.anyio
async def test_batch_wakeup_pattern_only_fires_when_all_agents_complete():
    """Validates the batch wake-up pattern: only trigger when active_count == 0."""
    from ayder_cli.agents.config import AgentConfig
    from ayder_cli.agents.registry import AgentRegistry
    from ayder_cli.agents.summary import AgentSummary
    from unittest.mock import MagicMock

    wakeup_calls = []

    def on_complete(summary):
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

    # Simulate: two agents in _active, one completes
    reg._active["a"] = MagicMock()
    reg._active["b"] = MagicMock()

    summary_a = AgentSummary(agent_name="a", status="completed", summary="done a", error=None)
    await reg._summary_queue.put(summary_a)
    reg._active.pop("a")
    on_complete(summary_a)
    assert len(wakeup_calls) == 0  # b is still running

    summary_b = AgentSummary(agent_name="b", status="completed", summary="done b", error=None)
    await reg._summary_queue.put(summary_b)
    reg._active.pop("b")
    on_complete(summary_b)
    assert len(wakeup_calls) == 1  # Now all done, wake up fires
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/agents/test_integration.py::test_batch_wakeup_pattern_only_fires_when_all_agents_complete -v`
Expected: PASS (pattern validation — not a TDD red-green cycle)

- [ ] **Step 3: Wire `on_complete` in AyderApp.__init__**

In `src/ayder_cli/tui/app.py`, modify the agent registry initialization block (around line 206). Define the `on_complete` callback and pass it to `AgentRegistry`:

```python
# Initialize agent registry if agents are configured (Part 1)
self._agent_registry: AgentRegistry | None = None
if hasattr(self.config, 'agents') and isinstance(self.config.agents, dict) and self.config.agents:
    def _agent_progress(name, event, data):
        """Forward agent events to AgentPanel."""
        try:
            panel = self.query_one("#agent-panel", AgentPanel)
            self.call_later(lambda: panel.update_agent(name, event, data))
        except Exception:
            pass

    def _agent_complete(summary):
        """Handle agent completion: update UI and wake LLM if all done."""
        try:
            panel = self.query_one("#agent-panel", AgentPanel)
            self.call_later(
                lambda: panel.complete_agent(summary.agent_name, summary.summary, summary.status)
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

        # Batch wake-up: only trigger LLM when ALL agents are done
        if self._agent_registry and self._agent_registry.active_count == 0:
            if not self._is_processing:
                # Drain summaries and inject into messages
                summaries = self._agent_registry.drain_summaries()
                for s in summaries:
                    self.messages.append({"role": "system", "content": s.format_for_injection()})
                    try:
                        chat_view = self.query_one("#chat-view", ChatView)
                        self.call_later(
                            lambda ss=s: chat_view.add_system_message(
                                f"Agent '{ss.agent_name}' {ss.status}: {ss.summary[:100]}"
                            )
                        )
                    except Exception:
                        pass
                # Wake the main LLM
                self.call_later(lambda: self.start_llm_processing())

    self._agent_registry = AgentRegistry(
        agents=self.config.agents,
        parent_config=self.config,
        project_ctx=rt.project_ctx,
        process_manager=self._process_manager,
        permissions=self.permissions,
        agent_timeout=getattr(self.config, 'agent_timeout', 300),
        on_progress=_agent_progress,
        on_complete=_agent_complete,
    )

    # Register call_agent tool
    handler = create_call_agent_handler(self._agent_registry)
    self.registry.register_dynamic_tool(AGENT_TOOL_DEFINITION, handler)

    # Append capability prompts to system prompt
    cap_prompts = self._agent_registry.get_capability_prompts()
    if cap_prompts and self.messages and self.messages[0].get("role") == "system":
        self.messages[0]["content"] += cap_prompts
```

- [ ] **Step 4: Update `dispatch()` in the app to show agent count in activity bar**

Update `_agent_progress` in `app.py` to sync activity bar count AND start the activity timer. Both `/agent` command dispatches and `call_agent` tool dispatches trigger progress events, so this single callback covers both paths:

```python
def _agent_progress(name, event, data):
    """Forward agent events to AgentPanel and sync activity bar."""
    try:
        panel = self.query_one("#agent-panel", AgentPanel)
        self.call_later(lambda: panel.update_agent(name, event, data))
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

Also in `src/ayder_cli/tui/commands.py`, add `ActivityBar` to the import (line 17):

```python
from ayder_cli.tui.widgets import AgentPanel, ActivityBar, ChatView, StatusBar
```

After the dispatch call in `handle_agent`, update activity bar and start timer:

```python
# Update activity bar with agent count and start timer
try:
    activity = app.query_one("#activity-bar", ActivityBar)
    count = app._agent_registry.active_count if app._agent_registry else 0
    activity.set_agents_running(count)
    app._start_activity_timer()
except Exception:
    pass
```

Also update `_maybe_stop_activity_timer` in `app.py` (line 382-388) to not stop the timer while agents are running:

```python
def _maybe_stop_activity_timer(self) -> None:
    """Stop the activity timer if nothing is active."""
    activity = self.query_one("#activity-bar", ActivityBar)
    if (not activity._thinking and not activity._generating
            and not activity._tools_working and activity._agents_running == 0):
        if self._activity_timer:
            self._activity_timer.stop()
            self._activity_timer = None
```

**Critical:** Also update `_finish_processing` in `app.py` (line 618-633). Replace the direct timer stop with `_maybe_stop_activity_timer()` so the timer keeps running while agents are active:

```python
def _finish_processing(self) -> None:
    """Finish processing - clear activity bar and process next message."""
    self._maybe_stop_activity_timer()  # Was: direct timer.stop() — now agent-aware

    activity = self.query_one("#activity-bar", ActivityBar)
    activity.clear()

    input_bar = self.query_one("#input-bar", CLIInputBar)
    input_bar.focus_input()

    if self._pending_messages:
        self._process_next_message()
    else:
        self._is_processing = False
```

- [ ] **Step 5: Reset `_settled` on new user message**

In `src/ayder_cli/tui/app.py`, modify `handle_input_submitted` (line 546-558). Add settled reset before processing:

```python
@on(CLIInputBar.Submitted)
def handle_input_submitted(self, event: CLIInputBar.Submitted) -> None:
    """Handle user input submission."""
    user_input = event.value

    # New user message = new cycle, reset re-dispatch guard
    if self._agent_registry and not user_input.startswith("/"):
        self._agent_registry.reset_settled()

    if user_input.startswith("/"):
        self._handle_command(user_input)
        return

    self._pending_messages.append(user_input)

    if not self._is_processing:
        self._process_next_message()
```

- [ ] **Step 6: Simplify `pre_iteration_hook` (now a fallback only)**

The `_inject_summaries` hook in `app.py` (lines 283-307) still serves as fallback when agents complete while the LLM is already processing. It can be simplified since the `on_complete` callback now handles the panel updates. Update it to only inject system messages:

```python
if self._agent_registry:
    async def _inject_summaries(messages):
        summaries = self._agent_registry.drain_summaries()
        for s in summaries:
            messages.append({"role": "system", "content": s.format_for_injection()})

    self.chat_loop.config.pre_iteration_hook = _inject_summaries
```

- [ ] **Step 7: Run all tests**

Run: `uv run pytest tests/ --timeout=10 -v`
Expected: ALL PASS

- [ ] **Step 8: Run lint and type checks**

Run: `uv run ruff check src/ayder_cli/agents/ src/ayder_cli/tui/app.py src/ayder_cli/tui/widgets.py`
Run: `uv run mypy src/ayder_cli/agents/ src/ayder_cli/tui/app.py src/ayder_cli/tui/widgets.py`

- [ ] **Step 9: Commit**

```bash
git add src/ayder_cli/tui/app.py src/ayder_cli/tui/commands.py tests/agents/test_integration.py
git commit -m "feat(agents): wire batch wake-up and settled reset in AyderApp"
```

---

### Task 6: Update capability prompts to instruct LLM about batch behavior

**Files:**
- Modify: `src/ayder_cli/agents/registry.py:65-80` (`get_capability_prompts`)
- Test: `tests/agents/test_registry.py`

- [ ] **Step 1: Write test for updated prompts**

Add to `tests/agents/test_registry.py`:

```python
def test_capability_prompts_mention_batch_behavior(self, registry):
    """Capability prompts explain batch completion and no-retry for failures."""
    prompts = registry.get_capability_prompts()
    assert "all agents complete" in prompts.lower() or "batch" in prompts.lower()
    assert "failed" in prompts.lower() or "error" in prompts.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/agents/test_registry.py::TestAgentRegistry::test_capability_prompts_mention_batch_behavior -v`
Expected: FAIL

- [ ] **Step 3: Update `get_capability_prompts` with batch and retry guidance**

In `src/ayder_cli/agents/registry.py`, update `get_capability_prompts()`:

```python
def get_capability_prompts(self) -> str:
    """Generate capability prompt text for the main LLM's system prompt."""
    if not self.agents:
        return ""

    lines = [
        "\n## Available Agents",
        "You can delegate tasks to specialized agents using the call_agent tool.",
        "Each agent runs independently with its own context and may use a different LLM.",
        "",
        "**Batch behavior:** When you dispatch multiple agents, you will receive",
        "all their summaries together after the last agent completes.",
        "Do not respond until you have all results.",
        "",
        "**On agent failure:** If an agent fails (error/timeout), do NOT re-dispatch it.",
        "Handle the failed task yourself. Agents that completed successfully CAN be",
        "re-dispatched if needed (e.g., to re-run tests after fixing code).",
        "",
    ]
    for name, cfg in self.agents.items():
        desc = cfg.system_prompt[:100] if cfg.system_prompt else "(no description)"
        lines.append(f"- {name}: {desc}")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/agents/test_registry.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/agents/registry.py tests/agents/test_registry.py
git commit -m "feat(agents): update capability prompts with batch and retry guidance"
```

---

### Task 7: Final verification and cleanup

**Files:**
- All modified files from Tasks 1-6

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ --timeout=10 -v`
Expected: ALL PASS

- [ ] **Step 2: Run lint**

Run: `uv run ruff check src/ tests/`
Fix any issues with: `uv run ruff check --fix src/ tests/`

- [ ] **Step 3: Run type checks**

Run: `uv run mypy src/ayder_cli/agents/ src/ayder_cli/tui/`

- [ ] **Step 4: Commit any fixes**

```bash
git add -u
git commit -m "chore: lint and type fixes for agent wake-up feature"
```
