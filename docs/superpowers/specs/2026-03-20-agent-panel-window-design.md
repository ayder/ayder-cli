# Agent Panel Window — Toggleable TUI Panel

**Date:** 2026-03-20
**Status:** Approved

## Problem

When agents complete, their status lines (`✓ web_parser — FINDINGS: ...`) remain inline in the chat area permanently. There is no way to review agent output on demand, no scrollable history, and no user control over visibility. The agent panel auto-shows on dispatch and has no toggle.

## Design

### Overview

Refactor `AgentPanel` into a scrollable, toggleable panel (like ToolPanel with Ctrl+O). Toggled with **Ctrl+G**. Never auto-shows — the ActivityBar spinner ("Agents running (2)") provides ambient status. User opens the panel when they want detail.

### Panel Behavior

- **Starts hidden.** `display = False` on mount.
- **Ctrl+G toggles** visibility via `_user_visible` flag (same pattern as ToolPanel).
- **Never auto-shows.** `add_agent()` and `complete_agent()` update content silently regardless of visibility.
- **Scrollable.** `overflow-y: scroll`, `max-height: 40%`. PageUp/PageDown work when panel has focus.
- **No auto-clear.** Entries persist across turns. Pruned on `add_agent()` when total entries exceed 50 (oldest completed entry removed).
- **No expand/collapse.** Each entry renders status line + full detail inline — keep it simple.

### Data Model

Entries are keyed by **run ID** (not agent name) to support re-dispatch of the same agent:

```python
_run_counter: int = 0
_entries: dict[int, _AgentEntry]  # run_id -> entry
_active_run: dict[str, int]      # agent_name -> current run_id (for progress routing)
```

`_AgentEntry` is a simple dataclass:
```python
@dataclass
class _AgentEntry:
    container: Container    # parent widget holding status + detail
    status_widget: Static   # status line (updated in real-time)
    detail_widget: Static | None  # full output (added on completion)
    name: str
    completed: bool = False
```

On `add_agent(name)`: increment `_run_counter`, create new entry, map `_active_run[name] = run_id`.
On `update_agent(name, ...)`: look up `_active_run[name]` to find the current entry.
On `complete_agent(name, ...)`: look up `_active_run[name]`, mark completed, append detail widget.

Re-dispatching `code_reviewer` twice creates two separate entries in the panel.

### Per-Agent Entry Structure

Each agent run produces two widgets inside a container:

```
✓ code_reviewer — FINDINGS: Identified 2 critical security vulnerabilities
    FINDINGS: Identified 2 critical security vulnerabilities (SQL injection,
    data exfiltration). 1. SQL injection in query builder at line 42...
    2. Data exfiltration risk in export endpoint...

▶ web_parser — Running tool: fetch_web
```

- **Status line** (`agent-status` class): Updated in real-time during agent lifecycle. Shows running state, then final status with preview.
- **Detail block** (`agent-detail` class): Rendered on `complete_agent()` with full summary text. Dim color, indented. Not present while agent is running.

### Agent Lifecycle (Silent Updates)

```
dispatch()        → add_agent(name)           → status: "▶ agent_name running..."
on_progress()     → update_agent(name, event) → status: "Thinking...", "Running tool: X"
on_complete()     → complete_agent(name, ...)  → status: "✓ agent_name — preview"
                                               → detail: full summary text appended
```

All updates happen regardless of panel visibility.

### `remove_agent()` — Neutered

The existing `remove_agent()` method currently removes the widget from the DOM and hides the panel when empty. Under the new design:
- Remove the `self.display = False` auto-hide behavior.
- Keep the method for explicit removal if needed, but it should only remove the entry from the DOM and `_entries` dict — it must not affect panel visibility.
- No code currently calls `remove_agent()`, so this is defensive cleanup only.

### Keybinding

```python
("ctrl+g", "toggle_agents", "Toggle Agents")
```

Action method follows the ToolPanel pattern:
```python
def action_toggle_agents(self) -> None:
    agent_panel = self.query_one("#agent-panel", AgentPanel)
    visible = agent_panel.toggle()
    chat_view = self.query_one("#chat-view", ChatView)
    state = "visible" if visible else "hidden"
    chat_view.add_system_message(f"Agent panel {state} (Ctrl+G to toggle)")
```

### CSS (Claude Theme)

```css
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

#agent-panel {
    min-height: 0;
    max-height: 40%;
    width: 100%;
}

AgentPanel .agent-entry { height: auto; padding: 0 1; }
AgentPanel .agent-status { color: #d4a043; }
AgentPanel .agent-status.completed { color: #5cb870; }
AgentPanel .agent-status.error { color: #ff5555; }
AgentPanel .agent-status.timeout { color: #d4a043; }
AgentPanel .agent-detail { color: #666680; padding: 0 0 0 4; }
```

### StatusBar Key Hint

Update the StatusBar hint string to include `^G:agents`:
```
^C:cancel ^L:clear ^O:tools ^T:think ^G:agents PgUp/Dn:scroll ^Q:quit
```

## Files Affected

- `src/ayder_cli/tui/widgets.py` — Refactor AgentPanel: new data model (`_entries`, `_active_run`, `_run_counter`), add `_user_visible` and `toggle()`, restructure entries as status + detail containers, remove auto-show from `add_agent()`, neuter `remove_agent()` auto-hide. Update StatusBar key hint to include `^G:agents`.
- `src/ayder_cli/tui/app.py` — Add `("ctrl+g", "toggle_agents", "Toggle Agents")` to BINDINGS, add `action_toggle_agents()` method.
- `src/ayder_cli/themes/claude.py` — Add AgentPanel CSS block (type selector + ID selector).
- `src/ayder_cli/tui/commands.py` — No changes needed, but verify `handle_agent` (line 977) does not re-add auto-show behavior. The call to `agent_panel.add_agent(agent_name)` gets the new silent behavior transitively.

## What Does NOT Change

- ActivityBar agent count spinner (already works)
- `_agent_complete` callback in app.py (already calls `panel.complete_agent()`)
- `_agent_progress` callback in app.py (already calls `panel.update_agent()`)
- Batch wake-up logic
- `_settled` re-dispatch guard

## Constraints

- AgentPanel must follow the ToolPanel pattern exactly (toggle, CSS, action method)
- No auto-show — ActivityBar spinner is the ambient indicator
- No expand/collapse — keep it simple, all content inline
- No auto-clear — persistent scrollable log, prune at 50 entries
- Existing tests must not break
