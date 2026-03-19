# Extract Reusable ChatLoop from TuiChatLoop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename and relocate `TuiChatLoop` to `ChatLoop` in `loops/chat_loop.py`, making the core async chat loop reusable by agents (Phase 2) without breaking any existing consumers.

**Architecture:** Move the file, rename the three public symbols (`TuiChatLoop` → `ChatLoop`, `TuiCallbacks` → `ChatCallbacks`, `TuiLoopConfig` → `ChatLoopConfig`), update internal docstrings, and create backward-compat re-exports in the original `tui/chat_loop.py`. All existing imports continue to work unchanged.

**Tech Stack:** Python 3.12, pytest, ayder_cli loops/base module

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| **Move+Rename** | `src/ayder_cli/tui/chat_loop.py` → `src/ayder_cli/loops/chat_loop.py` | Core chat loop with renamed symbols |
| **Create** | `src/ayder_cli/tui/chat_loop.py` (new) | Backward-compat re-exports of old names |
| **Modify** | `src/ayder_cli/loops/__init__.py` | Export new names |
| **Modify** | `src/ayder_cli/loops/base.py` (docstrings only) | Update references from "TuiChatLoop" to "ChatLoop" |
| **Modify** | `src/ayder_cli/cli_callbacks.py` (docstrings only) | Update references from "TuiCallbacks"/"TuiChatLoop" |
| **No change** | `src/ayder_cli/tui/app.py` | Keeps importing via re-exports — no modification needed |
| **No change** | All test files | Re-exports ensure all existing imports work unchanged |
| **Modify** | `AGENTS.md` (lines 72-74, 119, 161) | Update project structure tree and module table |
| **Modify** | `docs/PROJECT_STRUCTURE.md` (lines 92-94, 160, 183, 286, 391, 441, 491-498, 572) | Update architecture docs |

## Key Constraint

All existing imports from `ayder_cli.tui.chat_loop` must continue to work. The re-export module ensures backward compat. No test files need modification — this is a pure rename with re-exports.

Consumer files that import from `ayder_cli.tui.chat_loop` (these will ALL keep working via re-exports):
- `src/ayder_cli/cli_runner.py:17` — `from ayder_cli.tui.chat_loop import TuiChatLoop, TuiLoopConfig`
- `src/ayder_cli/tui/app.py:38` — `from ayder_cli.tui.chat_loop import TuiChatLoop, TuiLoopConfig`
- `tests/test_cli_callbacks.py:12,19` — `from ayder_cli.tui.chat_loop import TuiCallbacks`
- `tests/ui/test_tui_chat_loop.py:18-19` — `from ayder_cli.tui.chat_loop import TuiChatLoop, TuiLoopConfig`
- `tests/ui/test_confirm_screen.py` (10+ occurrences) — `from ayder_cli.tui.chat_loop import TuiChatLoop, TuiLoopConfig`
- `tests/convergence/test_validation_path.py:243` — `from ayder_cli.tui.chat_loop import TuiChatLoop`
- `tests/convergence/test_runtime_wiring.py:31,67` — `from ayder_cli.tui.chat_loop import TuiChatLoop, TuiLoopConfig`
- `tests/loops/test_base.py:33-34` — `from ayder_cli.tui.chat_loop import TuiChatLoop`
- `tests/test_cli.py:190` — `patch('ayder_cli.cli_runner.TuiChatLoop')`

---

### Task 1: Move chat_loop.py and rename symbols

**Files:**
- Move: `src/ayder_cli/tui/chat_loop.py` → `src/ayder_cli/loops/chat_loop.py`
- Modify: `src/ayder_cli/loops/chat_loop.py` (rename symbols + update docstrings)

- [ ] **Step 1: Copy `tui/chat_loop.py` to `loops/chat_loop.py`**

```bash
cp src/ayder_cli/tui/chat_loop.py src/ayder_cli/loops/chat_loop.py
```

We copy first (not `git mv`) because we need the original location for the re-export file in the next task.

- [ ] **Step 2: Rename `TuiLoopConfig` → `ChatLoopConfig` in `loops/chat_loop.py`**

Change the class definition and its docstring:

```python
# Line 30: was "class TuiLoopConfig:"
@dataclass
class ChatLoopConfig:
    """Configuration for the chat loop."""
```

- [ ] **Step 3: Rename `TuiCallbacks` → `ChatCallbacks` in `loops/chat_loop.py`**

Change the class definition and its docstring:

```python
# Line 47: was "class TuiCallbacks(Protocol):"
@runtime_checkable
class ChatCallbacks(Protocol):
    """Protocol so ChatLoop never touches UI widgets directly."""
```

- [ ] **Step 4: Rename `TuiChatLoop` → `ChatLoop` in `loops/chat_loop.py`**

Change the class definition, docstring, and type hints:

```python
# Line 66: was "class TuiChatLoop(AgentLoopBase):"
class ChatLoop(AgentLoopBase):
    """Async chat loop that drives the LLM pipeline.

    Extends AgentLoopBase for shared escalation detection.
    Does NOT own any UI widgets — communicates through ChatCallbacks.
    """

    def __init__(
        self,
        llm: AIProvider,
        registry: ToolRegistry,
        messages: list[dict],
        config: ChatLoopConfig,        # was TuiLoopConfig
        callbacks: ChatCallbacks,       # was TuiCallbacks
    ) -> None:
```

- [ ] **Step 5: Update the module docstring in `loops/chat_loop.py`**

```python
"""
ChatLoop — async chat loop for LLM agent interactions.

Extracts all LLM call + tool execution logic into a testable,
widget-free class. Communication with UI happens exclusively
through the ChatCallbacks protocol.

Renamed from TuiChatLoop (originally in tui/chat_loop.py) to enable
reuse by agents and other consumers beyond the TUI.
"""
```

- [ ] **Step 6: Update `loops/base.py` docstrings**

In `src/ayder_cli/loops/base.py`, update the module docstring (lines 7-8) from:

```
Both ChatLoop (CLI) and TuiChatLoop (TUI) extend this class.
Each subclass owns its own run() loop, LLM calls, and UI interactions.
```

To:

```
ChatLoop (in loops/chat_loop.py) extends this class.
```

And update the class docstring (line 20) from:

```
    """Shared helpers inherited by CLI ChatLoop and TUI TuiChatLoop."""
```

To:

```
    """Shared helpers inherited by ChatLoop."""
```

- [ ] **Step 7: Update `cli_callbacks.py` docstrings**

In `src/ayder_cli/cli_callbacks.py`, update the module docstring (lines 1-3) from references to `TuiCallbacks` and `TuiChatLoop` to use the new names `ChatCallbacks` and `ChatLoop`. Specifically:

```python
"""CliCallbacks — ChatCallbacks adapter for plain terminal sessions.

Implements the ChatCallbacks protocol so that ChatLoop can be driven
from a plain terminal without Textual widgets.
"""
```

And update the class docstring (line 21) from:

```
    """TuiCallbacks adapter for the CLI — writes to stdout/stderr.
```

To:

```
    """ChatCallbacks adapter for the CLI — writes to stdout/stderr.
```

- [ ] **Step 8: Verify the renamed file has correct syntax**

```bash
uv run python -c "from ayder_cli.loops.chat_loop import ChatLoop, ChatCallbacks, ChatLoopConfig; print('OK')"
```

Expected: `OK`

- [ ] **Step 9: Commit**

```bash
git add src/ayder_cli/loops/chat_loop.py src/ayder_cli/loops/base.py src/ayder_cli/cli_callbacks.py
git commit -m "refactor: copy tui/chat_loop.py to loops/ and rename symbols

Rename TuiChatLoop → ChatLoop, TuiCallbacks → ChatCallbacks,
TuiLoopConfig → ChatLoopConfig. This makes the core async chat loop
reusable beyond the TUI (prerequisite for multi-agent support)."
```

---

### Task 2: Create backward-compat re-export in tui/chat_loop.py

**Files:**
- Replace: `src/ayder_cli/tui/chat_loop.py` (overwrite with re-exports)

- [ ] **Step 1: Replace `tui/chat_loop.py` with re-exports**

Replace the entire content of `src/ayder_cli/tui/chat_loop.py` with:

```python
"""Backward-compatibility re-exports.

The canonical implementation has moved to ``ayder_cli.loops.chat_loop``.
These aliases ensure existing imports continue to work.
"""

from ayder_cli.loops.chat_loop import ChatLoop as TuiChatLoop
from ayder_cli.loops.chat_loop import ChatCallbacks as TuiCallbacks
from ayder_cli.loops.chat_loop import ChatLoopConfig as TuiLoopConfig

# Re-export module-level helpers that some tests or consumers may reference
from ayder_cli.loops.chat_loop import (  # noqa: F401
    _parse_arguments,
    _repair_truncated_json,
    _check_required_args,
    _unwrap_exec_result,
    _is_escalation_result,
)

__all__ = [
    "TuiChatLoop",
    "TuiCallbacks",
    "TuiLoopConfig",
    "_parse_arguments",
    "_repair_truncated_json",
    "_check_required_args",
    "_unwrap_exec_result",
    "_is_escalation_result",
]
```

- [ ] **Step 2: Verify old import paths still work**

```bash
uv run python -c "from ayder_cli.tui.chat_loop import TuiChatLoop, TuiCallbacks, TuiLoopConfig; print('OLD OK')"
uv run python -c "from ayder_cli.loops.chat_loop import ChatLoop, ChatCallbacks, ChatLoopConfig; print('NEW OK')"
```

Expected: Both print `OK`.

- [ ] **Step 3: Verify old and new names resolve to the same class**

```bash
uv run python -c "
from ayder_cli.tui.chat_loop import TuiChatLoop
from ayder_cli.loops.chat_loop import ChatLoop
assert TuiChatLoop is ChatLoop, 'Classes must be identical objects'
print('IDENTITY OK')
"
```

Expected: `IDENTITY OK`

- [ ] **Step 4: Commit**

```bash
git add src/ayder_cli/tui/chat_loop.py
git commit -m "refactor: replace tui/chat_loop.py with backward-compat re-exports

All existing imports from ayder_cli.tui.chat_loop continue to work.
TuiChatLoop/TuiCallbacks/TuiLoopConfig are now aliases for
ChatLoop/ChatCallbacks/ChatLoopConfig from loops/chat_loop.py."
```

---

### Task 3: Update loops/__init__.py exports

**Files:**
- Modify: `src/ayder_cli/loops/__init__.py`

- [ ] **Step 1: Add new exports to `loops/__init__.py`**

Current content of `src/ayder_cli/loops/__init__.py`:

```python
"""Shared agent loop base classes."""

from ayder_cli.loops.base import AgentLoopBase
from ayder_cli.loops.config import LoopConfig

__all__ = ["AgentLoopBase", "LoopConfig"]
```

Change to:

```python
"""Shared agent loop base classes and chat loop."""

from ayder_cli.loops.base import AgentLoopBase
from ayder_cli.loops.config import LoopConfig
from ayder_cli.loops.chat_loop import ChatLoop, ChatCallbacks, ChatLoopConfig

__all__ = [
    "AgentLoopBase",
    "LoopConfig",
    "ChatLoop",
    "ChatCallbacks",
    "ChatLoopConfig",
]
```

- [ ] **Step 2: Verify import from package**

```bash
uv run python -c "from ayder_cli.loops import ChatLoop, ChatCallbacks, ChatLoopConfig; print('PACKAGE OK')"
```

Expected: `PACKAGE OK`

- [ ] **Step 3: Commit**

```bash
git add src/ayder_cli/loops/__init__.py
git commit -m "refactor: export ChatLoop/ChatCallbacks/ChatLoopConfig from loops package"
```

---

### Task 4: Run full test suite and verify zero breakage

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

```bash
uv run poe test
```

Expected: All tests pass (979+ tests). Zero failures.

The re-exports ensure every existing import path works. Key test files that exercise the old import paths:
- `tests/ui/test_tui_chat_loop.py` — imports `TuiChatLoop`, `TuiLoopConfig`
- `tests/ui/test_confirm_screen.py` — imports `TuiChatLoop`, `TuiLoopConfig` (10+ times)
- `tests/test_cli_callbacks.py` — imports `TuiCallbacks`, checks isinstance
- `tests/convergence/test_runtime_wiring.py` — imports `TuiChatLoop`, `TuiLoopConfig`
- `tests/convergence/test_validation_path.py` — imports `TuiChatLoop`
- `tests/loops/test_base.py` — imports `TuiChatLoop`, checks `issubclass`
- `tests/test_cli.py` — patches `ayder_cli.cli_runner.TuiChatLoop`

- [ ] **Step 2: Run linter**

```bash
uv run poe lint
```

Expected: No errors.

- [ ] **Step 3: Run type checker**

```bash
uv run poe typecheck
```

Expected: No new errors.

- [ ] **Step 4: Verify no import of old module internals that bypass re-exports**

Search for any direct imports of the class names from the source module that might break:

```bash
grep -rn "from ayder_cli.tui.chat_loop import" src/ tests/ --include="*.py"
```

Expected: All matches should be importing one of: `TuiChatLoop`, `TuiCallbacks`, `TuiLoopConfig`, `_parse_arguments`, `_repair_truncated_json`, `_check_required_args`, `_unwrap_exec_result`, `_is_escalation_result` — all of which are covered by the re-export module.

- [ ] **Step 5: Commit (only if any fixes were needed)**

If any test or lint issue was found and fixed, commit here. Otherwise skip.

---

### Task 5: Update documentation

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/PROJECT_STRUCTURE.md`

- [ ] **Step 1: Update AGENTS.md project structure tree**

In the `loops/` section (around line 72-74), change:

```
│   ├── loops/                  # Shared agent loop base
│   │   ├── base.py             # AgentLoopBase (iteration, checkpoint, routing)
│   │   └── config.py           # Shared LoopConfig dataclass
```

To:

```
│   ├── loops/                  # Shared agent loop + base classes
│   │   ├── base.py             # AgentLoopBase (iteration, checkpoint, routing)
│   │   ├── chat_loop.py        # ChatLoop (async LLM + tool execution loop)
│   │   └── config.py           # Shared LoopConfig dataclass
```

- [ ] **Step 2: Update AGENTS.md TUI section**

In the `tui/` section (around line 119), change:

```
│   │   ├── chat_loop.py        # TUI async chat loop (TuiChatLoop)
```

To:

```
│   │   ├── chat_loop.py        # Backward-compat re-exports → loops/chat_loop.py
```

- [ ] **Step 3: Update AGENTS.md module table**

Around line 161, change:

```
| `tui/chat_loop.py` | Async LLM loop for TUI (TuiChatLoop + TuiCallbacks protocol) |
```

To:

```
| `loops/chat_loop.py` | Async LLM + tool execution loop (ChatLoop + ChatCallbacks protocol) |
| `tui/chat_loop.py` | Backward-compat re-exports (TuiChatLoop → ChatLoop aliases) |
```

- [ ] **Step 4: Update docs/PROJECT_STRUCTURE.md Key Architectural Principles**

Around line 94, change:

```
4. **Shared Loop Base**: `AgentLoopBase` (in `loops/base.py`) owns iteration counting, checkpoint trigger detection, and tool-call routing; both `ChatLoop` and `TuiChatLoop` extend it
```

To:

```
4. **Shared Loop Base**: `AgentLoopBase` (in `loops/base.py`) owns tool-call routing and escalation detection; `ChatLoop` (in `loops/chat_loop.py`) extends it with the full async LLM + tool execution loop
```

- [ ] **Step 5: Update docs/PROJECT_STRUCTURE.md module tables**

Around line 160, delete the stale entry referencing a nonexistent root-level `chat_loop.py` (this module was removed in a prior refactor):

```
| `chat_loop.py` | Sync CLI agent loop | `ChatLoop`, `LoopConfig`, `ToolCallHandler` |
```

Remove this row entirely. The new `loops/chat_loop.py` is already covered in the loops section.

Around line 183, change:

```
| `tui/chat_loop.py` | TUI chat loop logic | `TuiChatLoop`, `TuiLoopConfig` |
```

To:

```
| `tui/chat_loop.py` | Backward-compat re-exports | `TuiChatLoop` → `ChatLoop`, `TuiLoopConfig` → `ChatLoopConfig` |
```

- [ ] **Step 6: Update docs/PROJECT_STRUCTURE.md TuiCallbacks section**

Around line 286, change:

```
The `TuiCallbacks` protocol in `tui/chat_loop.py` decouples `TuiChatLoop` from all UI concerns:
```

To:

```
The `ChatCallbacks` protocol in `loops/chat_loop.py` (aliased as `TuiCallbacks` in `tui/chat_loop.py`) decouples `ChatLoop` from all UI concerns:
```

- [ ] **Step 7: Update docs/PROJECT_STRUCTURE.md TUI Chat Loop Summary section**

Around line 491-498, change:

```
### TUI Chat Loop Summary (src/ayder_cli/tui/chat_loop.py)

`TuiChatLoop` (extends `AgentLoopBase`) implements the core async agentic process:
```

To:

```
### Chat Loop Summary (src/ayder_cli/loops/chat_loop.py)

`ChatLoop` (extends `AgentLoopBase`) implements the core async agentic process:
```

- [ ] **Step 8: Update docs/PROJECT_STRUCTURE.md AgentLoopBase section**

Around line 572, change:

```
`AgentLoopBase` extracted to `loops/base.py`. Both `ChatLoop` and `TuiChatLoop` extend it:
```

To:

```
`AgentLoopBase` extracted to `loops/base.py`. `ChatLoop` (in `loops/chat_loop.py`) extends it:
```

- [ ] **Step 9: Update docs/PROJECT_STRUCTURE.md Protocol-Based Imports example**

Around line 391, change the code example:

```python
# tui/chat_loop.py
from typing import Protocol

class TuiCallbacks(Protocol):
    ...
```

To:

```python
# loops/chat_loop.py (aliased as TuiCallbacks in tui/chat_loop.py)
from typing import Protocol

class ChatCallbacks(Protocol):
    ...
```

- [ ] **Step 10: Update docs/PROJECT_STRUCTURE.md File Organization Tips**

Around line 441, change:

```
2. **New Application-Layer Shared Logic**: Add to `application/` and import from both `chat_loop.py` and `tui/chat_loop.py`.
```

To:

```
2. **New Application-Layer Shared Logic**: Add to `application/` and import from `loops/chat_loop.py`.
```

- [ ] **Step 11: Commit**

```bash
git add AGENTS.md docs/PROJECT_STRUCTURE.md
git commit -m "docs: update structure docs for ChatLoop rename and relocation"
```

---

### Task 6: Final verification

- [ ] **Step 1: Run full test suite**

```bash
uv run poe test
```

Expected: All tests pass.

- [ ] **Step 2: Run linter**

```bash
uv run poe lint
```

Expected: No errors.

- [ ] **Step 3: Verify new import paths work end-to-end**

```bash
uv run python -c "
from ayder_cli.loops.chat_loop import ChatLoop, ChatCallbacks, ChatLoopConfig
from ayder_cli.tui.chat_loop import TuiChatLoop, TuiCallbacks, TuiLoopConfig
from ayder_cli.loops import ChatLoop as L2

assert TuiChatLoop is ChatLoop, 'TuiChatLoop must be ChatLoop'
assert TuiCallbacks is ChatCallbacks, 'TuiCallbacks must be ChatCallbacks'
assert TuiLoopConfig is ChatLoopConfig, 'TuiLoopConfig must be ChatLoopConfig'
assert L2 is ChatLoop, 'Package export must match'
print('ALL IDENTITY CHECKS OK')
"
```

Expected: `ALL IDENTITY CHECKS OK`

- [ ] **Step 4: Verify issubclass relationship preserved**

```bash
uv run python -c "
from ayder_cli.loops.base import AgentLoopBase
from ayder_cli.loops.chat_loop import ChatLoop
assert issubclass(ChatLoop, AgentLoopBase), 'ChatLoop must extend AgentLoopBase'
print('INHERITANCE OK')
"
```

Expected: `INHERITANCE OK`
