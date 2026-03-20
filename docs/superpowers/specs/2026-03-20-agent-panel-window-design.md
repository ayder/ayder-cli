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
- **Scrollable.** `overflow-y: auto`, `max-height: 40%`. PageUp/PageDown work when panel has focus.
- **No auto-clear.** Entries persist across turns. Pruned only when exceeding ~50 agent runs (oldest removed).
- **No expand/collapse.** Each entry renders status line + full detail inline — keep it simple.

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
    overflow-y: auto;
    display: none;
}

AgentPanel .agent-entry { height: auto; padding: 0 1; }
AgentPanel .agent-status { color: #d4a043; }
AgentPanel .agent-status.completed { color: #5cb870; }
AgentPanel .agent-status.error { color: #ff5555; }
AgentPanel .agent-status.timeout { color: #d4a043; }
AgentPanel .agent-detail { color: #666680; padding: 0 0 0 4; }
```

## Files Affected

- `src/ayder_cli/tui/widgets.py` — Refactor AgentPanel: add `_user_visible`, `toggle()`, restructure entries as status + detail, remove auto-show from `add_agent()`, remove auto-hide from `remove_agent()`
- `src/ayder_cli/tui/app.py` — Add `("ctrl+g", "toggle_agents", "Toggle Agents")` to BINDINGS, add `action_toggle_agents()` method
- `src/ayder_cli/themes/claude.py` — Add AgentPanel CSS block

## What Does NOT Change

- ActivityBar agent count spinner (already works)
- `_agent_complete` callback in app.py (already calls `panel.complete_agent()`)
- `_agent_progress` callback in app.py (already calls `panel.update_agent()`)
- Batch wake-up logic
- `_settled` re-dispatch guard
- `/agent` command handler in commands.py

## Constraints

- AgentPanel must follow the ToolPanel pattern exactly (toggle, CSS, action method)
- No auto-show — ActivityBar spinner is the ambient indicator
- No expand/collapse — keep it simple, all content inline
- No auto-clear — persistent scrollable log
- Existing tests must not break
