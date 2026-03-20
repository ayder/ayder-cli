# Agent Panel Window Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor AgentPanel into a toggleable, scrollable panel (Ctrl+G) with per-entry status + full detail output.

**Architecture:** Replace the current `dict[str, Static]` data model with run-ID-keyed entries. Each entry has a status widget and an optional detail widget, mounted as siblings in the panel (no Container wrapper — kept simple per user request). Follow the ToolPanel toggle pattern exactly. Add CSS styling to claude.py theme.

**Tech Stack:** Python 3.12, Textual (TUI framework), pytest

**Spec:** `docs/superpowers/specs/2026-03-20-agent-panel-window-design.md`

---

### File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/ayder_cli/tui/widgets.py:674-755` | Modify | Refactor AgentPanel class |
| `src/ayder_cli/tui/app.py:129-138` | Modify | Add Ctrl+G keybinding |
| `src/ayder_cli/tui/app.py:690-704` | Modify | Add action_toggle_agents() |
| `src/ayder_cli/themes/claude.py:454-510` | Modify | Add AgentPanel CSS after ToolPanel CSS |
| `src/ayder_cli/tui/widgets.py:641` | Modify | StatusBar key hint |
| `tests/tui/test_widgets.py` | Modify | Add AgentPanel tests |

**Note:** Line numbers are approximate — search for the relevant code pattern if they shift after earlier tasks.

**Verification note:** `src/ayder_cli/tui/commands.py` line 977 calls `agent_panel.add_agent(agent_name)`. The new `add_agent()` removes `self.display = True`, so this call gets the new silent behavior transitively. No changes needed, but verify after Task 1.

---

### Task 1: AgentPanel Data Model and Toggle

**Files:**
- Modify: `src/ayder_cli/tui/widgets.py:674-755`
- Test: `tests/tui/test_widgets.py`

- [ ] **Step 1: Write failing tests for new data model and toggle**

Tests mock `mount()` and `scroll_end()` since Textual DOM operations require a live app context.

```python
# tests/tui/test_widgets.py — append after existing tests
from unittest.mock import patch, MagicMock

from ayder_cli.tui.widgets import AgentPanel


class TestAgentPanelToggle:
    def test_starts_not_visible(self):
        panel = AgentPanel()
        assert panel._user_visible is False

    def test_toggle_returns_new_state(self):
        panel = AgentPanel()
        assert panel.toggle() is True
        assert panel._user_visible is True

    def test_toggle_twice_returns_false(self):
        panel = AgentPanel()
        panel.toggle()
        assert panel.toggle() is False
        assert panel._user_visible is False


class TestAgentPanelDataModel:
    @patch.object(AgentPanel, "mount")
    def test_add_agent_creates_entry(self, mock_mount):
        panel = AgentPanel()
        panel.add_agent("code_reviewer")
        assert "code_reviewer" in panel._active_run
        run_id = panel._active_run["code_reviewer"]
        assert run_id in panel._entries
        assert panel._entries[run_id].name == "code_reviewer"
        assert panel._entries[run_id].completed is False
        mock_mount.assert_called_once()

    @patch.object(AgentPanel, "mount")
    def test_add_agent_increments_run_counter(self, mock_mount):
        panel = AgentPanel()
        panel.add_agent("agent_a")
        panel.add_agent("agent_b")
        assert panel._run_counter == 2

    @patch.object(AgentPanel, "mount")
    def test_redispatch_creates_second_entry(self, mock_mount):
        panel = AgentPanel()
        panel.add_agent("code_reviewer")
        first_run = panel._active_run["code_reviewer"]
        panel.add_agent("code_reviewer")
        second_run = panel._active_run["code_reviewer"]
        assert first_run != second_run
        assert first_run in panel._entries
        assert second_run in panel._entries

    @patch.object(AgentPanel, "scroll_end")
    @patch.object(AgentPanel, "mount")
    def test_complete_agent_marks_completed(self, mock_mount, mock_scroll):
        panel = AgentPanel()
        panel.add_agent("web_parser")
        panel.complete_agent("web_parser", "Found 3 results", "completed")
        run_id = panel._active_run["web_parser"]
        assert panel._entries[run_id].completed is True

    @patch.object(AgentPanel, "scroll_end")
    @patch.object(AgentPanel, "mount")
    def test_complete_agent_stores_detail(self, mock_mount, mock_scroll):
        panel = AgentPanel()
        panel.add_agent("web_parser")
        panel.complete_agent("web_parser", "Full summary text here", "completed")
        run_id = panel._active_run["web_parser"]
        assert panel._entries[run_id].detail_widget is not None

    def test_complete_unknown_agent_is_noop(self):
        panel = AgentPanel()
        # Should not raise
        panel.complete_agent("nonexistent", "summary", "completed")

    @patch.object(AgentPanel, "mount")
    def test_update_agent_unknown_creates_entry(self, mock_mount):
        panel = AgentPanel()
        panel.update_agent("auto_created", "thinking_start")
        assert "auto_created" in panel._active_run

    @patch.object(AgentPanel, "scroll_end")
    @patch.object(AgentPanel, "mount")
    def test_prune_at_50_entries(self, mock_mount, mock_scroll):
        panel = AgentPanel()
        # Create 50 completed entries — mock remove() on widgets
        for i in range(50):
            name = f"agent_{i}"
            panel.add_agent(name)
            panel.complete_agent(name, f"summary {i}", "completed")
        assert len(panel._entries) == 50
        # 51st should prune oldest completed
        # Mock remove() on the widgets that will be pruned
        oldest_run_id = next(iter(panel._entries))
        panel._entries[oldest_run_id].status_widget.remove = MagicMock()
        if panel._entries[oldest_run_id].detail_widget:
            panel._entries[oldest_run_id].detail_widget.remove = MagicMock()
        panel.add_agent("agent_50")
        assert len(panel._entries) == 50
        assert oldest_run_id not in panel._entries
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/tui/test_widgets.py -v --timeout=10`
Expected: FAIL — `AgentPanel` has no `_user_visible`, `toggle`, `_entries`, `_active_run`, `_run_counter`

- [ ] **Step 3: Add `dataclass` import to widgets.py**

At the top of `src/ayder_cli/tui/widgets.py`, add to the imports section:

```python
from dataclasses import dataclass
```

- [ ] **Step 4: Implement new AgentPanel**

Replace the `AgentPanel` class in `src/ayder_cli/tui/widgets.py` (lines 674-755) with:

```python
@dataclass
class _AgentEntry:
    """Internal data for one agent run in the panel.

    No Container wrapper — status and detail are mounted as siblings
    in the panel for simplicity (per user request).
    """
    status_widget: Static   # Status line (updated in real-time)
    detail_widget: Static | None  # Full output (added on completion)
    name: str
    completed: bool = False


class AgentPanel(Container):
    """Scrollable panel for agent runs. Toggled with Ctrl+G.

    Never auto-shows. Content updates silently regardless of visibility.
    The ActivityBar spinner provides ambient status.
    """

    MAX_ENTRIES = 50

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._user_visible: bool = False
        self._run_counter: int = 0
        self._entries: dict[int, _AgentEntry] = {}
        self._active_run: dict[str, int] = {}  # agent_name -> current run_id

    def compose(self) -> ComposeResult:
        # Empty generator — widgets mounted dynamically
        return
        yield

    def on_mount(self) -> None:
        self.display = False

    def toggle(self) -> bool:
        """Toggle panel visibility. Returns new visibility state."""
        self._user_visible = not self._user_visible
        self.display = self._user_visible
        return self._user_visible

    def add_agent(self, name: str) -> None:
        """Add a new agent run entry. Never auto-shows the panel."""
        self._prune_if_needed()
        self._run_counter += 1
        run_id = self._run_counter

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
        self._active_run[name] = run_id
        self.mount(status_widget)

    def complete_agent(self, name: str, summary: str, status: str = "completed") -> None:
        """Mark agent as completed with full summary."""
        run_id = self._active_run.get(name)
        if run_id is None or run_id not in self._entries:
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
        text.append(f"{name}", style="bold")
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

    def update_agent(self, name: str, event: str, data: Any = None) -> None:
        """Handle an agent progress event."""
        if name not in self._active_run:
            self.add_agent(name)

        run_id = self._active_run[name]
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

    def remove_agent(self, name: str) -> None:
        """Remove an agent entry from the panel. Does not affect panel visibility."""
        run_id = self._active_run.get(name)
        if run_id is not None and run_id in self._entries:
            entry = self._entries[run_id]
            entry.status_widget.remove()
            if entry.detail_widget:
                entry.detail_widget.remove()
            del self._entries[run_id]
            if self._active_run.get(name) == run_id:
                del self._active_run[name]

    def _update_status(self, entry: _AgentEntry, status_text: str) -> None:
        """Update the status line text for a running agent."""
        text = Text()
        text.append("  ▶ ", style="bold yellow")
        text.append(f"{entry.name}", style="bold magenta")
        text.append(f" — {status_text}", style="dim")
        entry.status_widget.update(text)

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
            if self._active_run.get(entry.name) == to_prune:
                del self._active_run[entry.name]
            del self._entries[to_prune]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/tui/test_widgets.py -v --timeout=10`
Expected: All tests PASS

- [ ] **Step 6: Run full test suite to check for regressions**

Run: `.venv/bin/python3 -m pytest tests/ --timeout=10 -q`
Expected: All 1051+ tests pass. Verify `commands.py` line 977 (`agent_panel.add_agent(agent_name)`) gets the new silent behavior transitively (no `self.display = True`).

- [ ] **Step 7: Commit**

```bash
git add src/ayder_cli/tui/widgets.py tests/tui/test_widgets.py
git commit -m "feat(tui): refactor AgentPanel with run-id entries and toggle"
```

---

### Task 2: Keybinding and Action Method

**Files:**
- Modify: `src/ayder_cli/tui/app.py` (BINDINGS list, ~line 129)
- Modify: `src/ayder_cli/tui/app.py` (add action after `action_toggle_thinking`, ~line 704)

- [ ] **Step 1: Add Ctrl+G to BINDINGS**

In `src/ayder_cli/tui/app.py`, find the BINDINGS list and add the new entry after the `ctrl+t` line:

```python
BINDINGS = [
    ("ctrl+q", "quit", "Quit"),
    ("ctrl+x", "cancel", "Cancel"),
    ("ctrl+c", "cancel", "Cancel"),
    ("ctrl+l", "clear", "Clear Chat"),
    ("ctrl+o", "toggle_tools", "Toggle Tools"),
    ("ctrl+t", "toggle_thinking", "Toggle Thinking"),
    ("ctrl+g", "toggle_agents", "Toggle Agents"),
    ("pageup", "scroll_chat_up", "Scroll Up"),
    ("pagedown", "scroll_chat_down", "Scroll Down"),
]
```

- [ ] **Step 2: Add action_toggle_agents method**

In `src/ayder_cli/tui/app.py`, add the new method after `action_toggle_thinking`:

```python
def action_toggle_agents(self) -> None:
    """Toggle the agent panel."""
    agent_panel = self.query_one("#agent-panel", AgentPanel)
    visible = agent_panel.toggle()
    chat_view = self.query_one("#chat-view", ChatView)
    state = "visible" if visible else "hidden"
    chat_view.add_system_message(f"Agent panel {state} (Ctrl+G to toggle)")
```

- [ ] **Step 3: Run full test suite**

Run: `.venv/bin/python3 -m pytest tests/ --timeout=10 -q`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add src/ayder_cli/tui/app.py
git commit -m "feat(tui): add Ctrl+G keybinding for agent panel toggle"
```

---

### Task 3: CSS Styling

**Files:**
- Modify: `src/ayder_cli/themes/claude.py` (after ToolPanel CSS block, ~line 480)

- [ ] **Step 1: Add AgentPanel CSS**

In `src/ayder_cli/themes/claude.py`, insert the following CSS block after the ToolPanel `.tool-item.completed` block (before the `/* AyderApp */` comment):

```css
/* AgentPanel - Scrollable panel for agent run history.
   Toggled with Ctrl+G. Targets 'AgentPanel' in widgets.py. */
AgentPanel {
    layout: vertical;
    height: auto;
    max-height: 40%;
    background: #0a0a18;
    border-top: solid #333350;
    padding: 1 1;
    overflow-y: scroll;
    display: none;
}

AgentPanel .agent-status {
    height: auto;
    color: #d4a043;
    padding: 0 1;
}

AgentPanel .agent-status.running {
    color: #d4a043;
}

AgentPanel .agent-status.completed {
    color: #5cb870;
}

AgentPanel .agent-status.error {
    color: #ff5555;
}

AgentPanel .agent-status.timeout {
    color: #d4a043;
}

AgentPanel .agent-detail {
    height: auto;
    color: #666680;
    padding: 0 0 0 4;
}
```

- [ ] **Step 2: Add `#agent-panel` ID selector**

In the same file, after the `#tool-panel` ID selector block, add:

```css
#agent-panel {
    min-height: 0;
    max-height: 40%;
    width: 100%;
}
```

- [ ] **Step 3: Run full test suite**

Run: `.venv/bin/python3 -m pytest tests/ --timeout=10 -q`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add src/ayder_cli/themes/claude.py
git commit -m "feat(tui): add AgentPanel CSS styling to claude theme"
```

---

### Task 4: StatusBar Key Hint

**Files:**
- Modify: `src/ayder_cli/tui/widgets.py` (StatusBar compose, ~line 641)

- [ ] **Step 1: Update StatusBar key hint**

In `src/ayder_cli/tui/widgets.py`, find the key-hint Label in `StatusBar.compose()` and change:

```python
yield Label("^C:cancel ^L:clear ^O:tools ^T:think PgUp/Dn:scroll ^Q:quit", classes="key-hint")
```

to:

```python
yield Label("^C:cancel ^L:clear ^O:tools ^T:think ^G:agents PgUp/Dn:scroll ^Q:quit", classes="key-hint")
```

- [ ] **Step 2: Run full test suite**

Run: `.venv/bin/python3 -m pytest tests/ --timeout=10 -q`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add src/ayder_cli/tui/widgets.py
git commit -m "feat(tui): add ^G:agents to StatusBar key hints"
```

---

### Task 5: Lint, Type-Check, and Final Verification

**Files:**
- All modified files

- [ ] **Step 1: Run ruff linter**

Run: `.venv/bin/python3 -m ruff check src/ayder_cli/tui/widgets.py src/ayder_cli/tui/app.py src/ayder_cli/themes/claude.py tests/tui/test_widgets.py`
Expected: No errors. If any, fix them.

- [ ] **Step 2: Run mypy type checker**

Run: `.venv/bin/python3 -m mypy src/ayder_cli/tui/widgets.py --ignore-missing-imports`
Expected: No errors. If any, fix type annotations.

- [ ] **Step 3: Run full test suite**

Run: `.venv/bin/python3 -m pytest tests/ --timeout=10 -q`
Expected: All 1051+ tests pass, 0 failures

- [ ] **Step 4: Commit any lint/type fixes**

```bash
git add -u
git commit -m "fix: lint and type fixes for agent panel"
```
