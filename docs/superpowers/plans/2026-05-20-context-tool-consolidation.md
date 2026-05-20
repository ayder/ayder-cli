# Context Tool Consolidation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace four memory tools (`save_memory`, `load_memory`, `save_context_memory`, `load_context_memory`) with a single polymorphic `context` tool that handles `save` / `load` / `list` / `stats` / `clear`. Fix the latent `/clear` coordination bug. Cut ~135 tokens per LLM call from the tool-definition surface.

**Architecture:** New `context` tool mirrors the polymorphic enum-dispatch pattern of `file_editor` (one tool, one `action` enum, params interpreted per action). Storage is per-named-slot JSON files in `.ayder/context/` with auto-versioning on overwrite and microsecond timestamps to prevent same-second collisions. Slot names are validated against a slug-like regex to prevent path traversal. The `clear` action takes a **caller-supplied summary** (the LLM provides the summary text in `content`) rather than triggering in-tool summarization — this avoids tool-cycle re-entrancy hazards. Actual message mutation is deferred via `app._pending_compact` and consumed by the chat_loop's `pre_iteration_hook`, composed with the existing agent-summary injection hook so both can run.

**Tech Stack:** Python 3.12, pytest with `anyio`, JSON for storage, existing `ToolDefinition` schema, existing `ContextManagerProtocol`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-05-20-context-tool-consolidation-design.md`

---

## File Structure

**New files:**
- `src/ayder_cli/tools/builtins/context.py` — `context()` dispatcher + `_save` / `_load` / `_list` / `_stats` / `_clear` helpers
- `src/ayder_cli/tools/builtins/context_definitions.py` — `TOOL_DEFINITIONS` tuple with the single `context` ToolDefinition
- `tests/test_context.py` — unit tests for each action
- `tests/tui/test_do_clear_coordination.py` — regression test for the `/clear` fix

**Modified files:**
- `src/ayder_cli/tools/registry.py` — extend `ToolRegistry` and `create_default_registry` with `context_manager` and `app` injectables
- `src/ayder_cli/tools/execution.py` — inject `context_manager` and `app` into tools that declare them
- `src/ayder_cli/application/runtime_factory.py` — pass `context_mgr` into `create_default_registry`
- `src/ayder_cli/tui/app.py` — pass `self` as `app` into the registry; consume `_pending_compact` in `pre_iteration_hook`
- `src/ayder_cli/loops/chat_loop.py` — already has `pre_iteration_hook`; no signature change, but verify it's wired in `app.py`
- `src/ayder_cli/tui/commands.py` — fix `do_clear`; remove `handle_save_memory`/`handle_load_memory`; add `/save-context`, `/load-context`, `/list-contexts`, `/context-stats`; remove old map entries
- `src/ayder_cli/prompts.py` — remove memory templates at lines 232 and 271

**Deleted files:**
- `src/ayder_cli/tools/builtins/memory.py`
- `src/ayder_cli/tools/builtins/memory_definitions.py`
- `tests/test_memory.py`

**Test assertion updates:**
- `tests/tools/test_definition_discovery.py:276-277` — replace memory tool names with `context`
- `tests/tools/test_schemas.py:56` — same

---

### Task 1: Extend ToolRegistry DI with context_manager and app

**Files:**
- Modify: `src/ayder_cli/tools/registry.py:27-29`
- Modify: `src/ayder_cli/tools/registry.py:56-65`
- Modify: `src/ayder_cli/tools/registry.py:115-117`
- Modify: `src/ayder_cli/tools/execution.py:29-36` and `:91-97`
- Test: `tests/tools/test_di_injection.py` (new file)

- [ ] **Step 1: Write the failing test for context_manager injection**

Create `tests/tools/test_di_injection.py`:

```python
"""Verify the registry injects context_manager and app into tool functions
based on signature inspection."""
from unittest.mock import MagicMock

from ayder_cli.core.context import ProjectContext
from ayder_cli.tools.registry import create_default_registry, ToolRegistry


def _tool_with_context_manager(project_ctx, context_manager, foo: str):
    return f"ctx_mgr={context_manager.tag} foo={foo}"


def _tool_with_app(project_ctx, app, foo: str):
    return f"app_msgs={len(app.messages)} foo={foo}"


def test_registry_injects_context_manager(tmp_path):
    project_ctx = ProjectContext(tmp_path)
    fake_mgr = MagicMock(tag="MGR")
    reg = ToolRegistry(project_ctx, context_manager=fake_mgr)
    reg.register("ctxtool", _tool_with_context_manager)

    result = reg.execute("ctxtool", {"foo": "bar"})

    assert "ctx_mgr=MGR" in str(result)
    assert "foo=bar" in str(result)


def test_registry_injects_app(tmp_path):
    project_ctx = ProjectContext(tmp_path)
    fake_app = MagicMock(messages=[1, 2, 3])
    reg = ToolRegistry(project_ctx, app=fake_app)
    reg.register("apptool", _tool_with_app)

    result = reg.execute("apptool", {"foo": "bar"})

    assert "app_msgs=3" in str(result)


def test_registry_skips_injection_when_param_absent(tmp_path):
    """Tools that don't declare context_manager/app must still work."""
    def simple_tool(project_ctx, foo: str):
        return f"foo={foo}"

    project_ctx = ProjectContext(tmp_path)
    reg = ToolRegistry(project_ctx)
    reg.register("simpletool", simple_tool)

    result = reg.execute("simpletool", {"foo": "bar"})
    assert "foo=bar" in str(result)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python3 -m pytest tests/tools/test_di_injection.py -v`
Expected: FAIL — `ToolRegistry.__init__` doesn't accept `context_manager` or `app`.

- [ ] **Step 3: Extend ToolRegistry constructor and execute**

Edit `src/ayder_cli/tools/registry.py:27-29`:

```python
    def __init__(
        self,
        project_ctx: ProjectContext,
        process_manager: Any = None,
        context_manager: Any = None,
        app: Any = None,
    ) -> None:
        self.project_ctx = project_ctx
        self.process_manager = process_manager
        self.context_manager = context_manager
        self.app = app
        self._registry: Dict[str, Callable] = {}
        self._dynamic_definitions: list = []
        self.hooks = HookManager()
```

Edit `src/ayder_cli/tools/registry.py:56-65`:

```python
    def execute(self, name: str, arguments: Any) -> ToolResult:
        tool_func = self._registry.get(name)
        return execute_tool(
            tool_name=name,
            arguments=arguments,
            tool_func=tool_func,
            hook_manager=self.hooks,
            project_ctx=self.project_ctx,
            process_manager=self.process_manager,
            context_manager=self.context_manager,
            app=self.app,
        )
```

Edit `src/ayder_cli/tools/registry.py:115-121` (`create_default_registry`):

```python
def create_default_registry(
    project_ctx: ProjectContext,
    process_manager: Any = None,
    context_manager: Any = None,
    app: Any = None,
) -> ToolRegistry:
    """Create a ToolRegistry with all tools from TOOL_DEFINITIONS auto-registered."""
    from ayder_cli.tools.definition import _PLUGIN_HANDLERS

    reg = ToolRegistry(
        project_ctx,
        process_manager=process_manager,
        context_manager=context_manager,
        app=app,
    )
    for td in TOOL_DEFINITIONS:
        ...
```

- [ ] **Step 4: Extend execute_tool signature**

Edit `src/ayder_cli/tools/execution.py:29-36`:

```python
def execute_tool(
    tool_name: str,
    arguments: Any,
    tool_func: Optional[Callable],
    hook_manager: HookManager,
    project_ctx: ProjectContext,
    process_manager: Any = None,
    context_manager: Any = None,
    app: Any = None,
) -> ToolResult:
```

Edit `src/ayder_cli/tools/execution.py:91-97` (Step 6 dependency injection):

```python
    # Step 6: Dependency injection
    sig = inspect.signature(tool_func)
    call_args = args.copy()
    if "project_ctx" in sig.parameters:
        call_args["project_ctx"] = project_ctx
    if "process_manager" in sig.parameters and process_manager is not None:
        call_args["process_manager"] = process_manager
    if "context_manager" in sig.parameters and context_manager is not None:
        call_args["context_manager"] = context_manager
    if "app" in sig.parameters and app is not None:
        call_args["app"] = app
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python3 -m pytest tests/tools/test_di_injection.py -v`
Expected: 3 tests PASS.

- [ ] **Step 6: Run full registry/execution tests to verify no regressions**

Run: `.venv/bin/python3 -m pytest tests/tools/ -v --timeout=30`
Expected: All existing tests still PASS.

- [ ] **Step 7: Commit**

```bash
git add src/ayder_cli/tools/registry.py src/ayder_cli/tools/execution.py tests/tools/test_di_injection.py
git commit -m "feat(tools): inject context_manager and app via registry DI"
```

---

### Task 2: Wire context_manager into runtime_factory

**Files:**
- Modify: `src/ayder_cli/application/runtime_factory.py:65`
- Modify: `src/ayder_cli/application/runtime_factory.py:165`
- Modify: `src/ayder_cli/tui/app.py:213` area

- [ ] **Step 1: Inspect the current runtime_factory wiring**

Run: `grep -n "create_default_registry\|context_manager" /Users/sinanalyuruk/Vscode/ayder-cli/src/ayder_cli/application/runtime_factory.py`
Expected output shows two `create_default_registry` calls (lines 65 and 165) and the context_mgr creation around line 80.

- [ ] **Step 2: Move context manager creation before registry creation in create_runtime**

The current order at runtime_factory.py:65-82 is: registry first, then context_mgr. We need to swap so the registry can receive context_mgr. Edit `runtime_factory.py:62-82`:

```python
    llm_provider: AIProvider = provider_orchestrator.create(cfg)
    project_ctx = ProjectContext(project_root)
    process_manager = ProcessManager(max_processes=cfg.max_background_processes)

    # Create context manager BEFORE registry so it can be injected.
    context_mgr = context_manager_factory.create(cfg)

    tool_registry = create_default_registry(
        project_ctx,
        process_manager=process_manager,
        context_manager=context_mgr,
    )

    try:
        structure = tool_registry.execute("get_project_structure", {"max_depth": 3})
        macro = PROJECT_STRUCTURE_MACRO_TEMPLATE.format(project_structure=structure)
    except Exception:
        macro = ""

    base_prompt = get_system_prompt(cfg.prompt)
    tool_tags = frozenset(cfg.tool_tags) if cfg.tool_tags else None
    tool_prompts = tool_registry.get_system_prompts(tags=tool_tags)
    system_prompt = base_prompt + tool_prompts + macro

    tool_schemas = tool_registry.get_schemas(tags=tool_tags)
    context_mgr.freeze_system_prompt(system_prompt, tool_schemas)
```

- [ ] **Step 3: Do the same swap in create_agent_runtime**

Edit `runtime_factory.py:164-165`:

```python
    # Create context manager BEFORE registry so it can be injected.
    context_mgr = context_manager_factory.create(cfg)

    tool_registry = create_default_registry(
        project_ctx,
        process_manager=process_manager,
        context_manager=context_mgr,
    )
```

(You'll need to find where `context_mgr` is currently created in the agent runtime function and move that line up. If it's created via a similar pattern, the swap is symmetric.)

- [ ] **Step 4: Wire app into the registry from tui/app.py**

`app.py:213` already does `self.registry = rt.tool_registry`. We need the registry to also hold a reference to the app instance.

The cleanest path is to set it after registry creation. Edit `src/ayder_cli/tui/app.py` around line 213 to add **immediately after** `self.registry = rt.tool_registry`:

```python
        self.registry = rt.tool_registry
        self.registry.app = self  # enables context(clear) to set _pending_compact
        self._pending_compact: dict | None = None
```

- [ ] **Step 5: Run the full test suite**

Run: `.venv/bin/python3 -m pytest tests/ -v --timeout=30`
Expected: All tests PASS (no behavior change yet — only wiring).

- [ ] **Step 6: Commit**

```bash
git add src/ayder_cli/application/runtime_factory.py src/ayder_cli/tui/app.py
git commit -m "feat(runtime): pass context_manager and app handle into tool registry"
```

---

### Task 3: Create context tool skeleton + dispatcher

**Files:**
- Create: `src/ayder_cli/tools/builtins/context.py`
- Create: `tests/test_context.py`

- [ ] **Step 1: Write the failing tests for the dispatcher**

Create `tests/test_context.py`:

```python
"""Unit tests for the context tool dispatcher and per-action behavior."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError, ToolSuccess
from ayder_cli.tools.builtins.context import context


@pytest.fixture
def project_ctx(tmp_path):
    return ProjectContext(tmp_path)


def test_dispatcher_rejects_unknown_action(project_ctx):
    result = context(project_ctx=project_ctx, action="nope")
    assert isinstance(result, ToolError)
    assert "unknown action" in str(result).lower()


def test_dispatcher_requires_action(project_ctx):
    """Calling without an action should be a validation error."""
    result = context(project_ctx=project_ctx, action="")
    assert isinstance(result, ToolError)
    assert result.category == "validation"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_context.py -v`
Expected: FAIL — module `ayder_cli.tools.builtins.context` does not exist.

- [ ] **Step 3: Create the context dispatcher**

Create `src/ayder_cli/tools/builtins/context.py`:

```python
"""Unified session-context tool.

Replaces save_memory, load_memory, save_context_memory, load_context_memory
with a single polymorphic tool dispatching on `action`.

Storage: .ayder/context/<name>.json (current), <name>.<timestamp>.json (versioned).

Slot names are validated to a slug-like character class to prevent
path traversal (`..`, `/`, etc).
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError, ToolSuccess


_VALID_ACTIONS = frozenset({"save", "load", "list", "stats", "clear"})


_SLOT_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _get_context_dir(project_ctx: ProjectContext) -> Path:
    return project_ctx.root / ".ayder" / "context"


def _iso_dashed_timestamp() -> str:
    """Filesystem-safe ISO timestamp with microsecond precision.

    Microseconds avoid same-second collision when two saves of the same slot
    happen rapidly. Colons in the time portion are replaced with dashes for
    Windows/macOS portability.
    """
    return datetime.now().isoformat().replace(":", "-").replace(".", "-")


def _validate_slot_name(name: str | None) -> str | None:
    """Return None if the slot name is safe, else an error message."""
    if not name:
        return "name must be a non-empty string"
    if not _SLOT_NAME_RE.match(name):
        return (
            "name must contain only letters, digits, '.', '_', '-' "
            "(no path separators or '..')"
        )
    if name in (".", "..") or name.startswith("."):
        return "name must not be '.', '..', or start with '.'"
    return None


def context(
    project_ctx: ProjectContext,
    action: str = "",
    name: str | None = None,
    content: str | None = None,
    overwrite: bool = False,
    keep_last_n: int = 0,
    context_manager: Any = None,
    app: Any = None,
) -> str:
    if not action:
        return ToolError("action is required", "validation")
    if action not in _VALID_ACTIONS:
        return ToolError(
            f"unknown action {action!r}; expected one of {sorted(_VALID_ACTIONS)}",
            "validation",
        )

    if action == "save":
        return _save(project_ctx, name, content, overwrite)
    if action == "load":
        return _load(project_ctx, name)
    if action == "list":
        return _list(project_ctx)
    if action == "stats":
        return _stats(project_ctx, context_manager)
    if action == "clear":
        return _clear(project_ctx, name, content, keep_last_n, context_manager, app)

    # Unreachable — _VALID_ACTIONS gate above.
    return ToolError(f"unhandled action {action!r}", "execution")


# Placeholders for next tasks.
def _save(project_ctx, name, content, overwrite):
    return ToolError("save not implemented", "execution")


def _load(project_ctx, name):
    return ToolError("load not implemented", "execution")


def _list(project_ctx):
    return ToolError("list not implemented", "execution")


def _stats(project_ctx, context_manager):
    return ToolError("stats not implemented", "execution")


def _clear(project_ctx, name, content, keep_last_n, context_manager, app):
    return ToolError("clear not implemented", "execution")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_context.py -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/tools/builtins/context.py tests/test_context.py
git commit -m "feat(tools): scaffold context dispatcher with action validation"
```

---

### Task 4: Implement context(action="save")

**Files:**
- Modify: `src/ayder_cli/tools/builtins/context.py` (`_save`)
- Modify: `tests/test_context.py`

- [ ] **Step 1: Write the failing tests for save**

Append to `tests/test_context.py`:

```python
def test_save_creates_file_in_context_dir(project_ctx):
    result = context(
        project_ctx=project_ctx, action="save", name="session", content="hello"
    )
    assert isinstance(result, ToolSuccess)
    ctx_dir = project_ctx.root / ".ayder" / "context"
    assert (ctx_dir / "session.json").exists()
    saved = json.loads((ctx_dir / "session.json").read_text())
    assert saved["content"] == "hello"
    assert saved["name"] == "session"
    assert "saved_at" in saved


def test_save_versions_existing_on_default_overwrite(project_ctx):
    context(project_ctx=project_ctx, action="save", name="s", content="v1")
    context(project_ctx=project_ctx, action="save", name="s", content="v2")

    ctx_dir = project_ctx.root / ".ayder" / "context"
    current = ctx_dir / "s.json"
    assert json.loads(current.read_text())["content"] == "v2"

    # One versioned predecessor should exist.
    versioned = [
        p for p in ctx_dir.iterdir()
        if p.name.startswith("s.") and p.name != "s.json"
    ]
    assert len(versioned) == 1
    assert json.loads(versioned[0].read_text())["content"] == "v1"


def test_save_with_overwrite_true_skips_versioning(project_ctx):
    context(project_ctx=project_ctx, action="save", name="s", content="v1")
    context(
        project_ctx=project_ctx, action="save", name="s", content="v2", overwrite=True
    )

    ctx_dir = project_ctx.root / ".ayder" / "context"
    assert json.loads((ctx_dir / "s.json").read_text())["content"] == "v2"
    # No versioned predecessor.
    siblings = [p for p in ctx_dir.iterdir() if p.name != "s.json"]
    assert siblings == []


def test_save_missing_name_returns_validation_error(project_ctx):
    result = context(project_ctx=project_ctx, action="save", content="x")
    assert isinstance(result, ToolError)
    assert result.category == "validation"


def test_save_missing_content_returns_validation_error(project_ctx):
    result = context(project_ctx=project_ctx, action="save", name="s")
    assert isinstance(result, ToolError)
    assert result.category == "validation"


@pytest.mark.parametrize(
    "bad_name",
    ["..", "../escape", "a/b", "a\\b", ".hidden", "name with spaces", ""],
)
def test_save_rejects_unsafe_slot_names(project_ctx, bad_name):
    result = context(
        project_ctx=project_ctx, action="save", name=bad_name, content="x"
    )
    assert isinstance(result, ToolError)
    assert result.category == "validation"


def test_save_versioning_handles_rapid_repeat_saves(project_ctx, monkeypatch):
    """Two saves of the same slot within one second must each produce a distinct
    versioned file (microsecond precision guarantees uniqueness)."""
    context(project_ctx=project_ctx, action="save", name="s", content="v1")
    context(project_ctx=project_ctx, action="save", name="s", content="v2")
    context(project_ctx=project_ctx, action="save", name="s", content="v3")

    ctx_dir = project_ctx.root / ".ayder" / "context"
    versioned = sorted(p.name for p in ctx_dir.iterdir() if p.name != "s.json")
    assert len(versioned) == 2  # v1 and v2 each got versioned
```

Also add `import json` at the top of the test file if not already present.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_context.py -v`
Expected: 5 new tests FAIL with "save not implemented".

- [ ] **Step 3: Implement _save**

Replace the `_save` placeholder in `src/ayder_cli/tools/builtins/context.py`:

```python
def _save(
    project_ctx: ProjectContext,
    name: str | None,
    content: str | None,
    overwrite: bool,
) -> str:
    err = _validate_slot_name(name)
    if err:
        return ToolError(err, "validation")
    if content is None or content == "":
        return ToolError("content is required for save", "validation")

    ctx_dir = _get_context_dir(project_ctx)
    ctx_dir.mkdir(parents=True, exist_ok=True)

    target = ctx_dir / f"{name}.json"
    if target.exists() and not overwrite:
        # Microsecond precision avoids same-second collisions on rapid
        # repeat saves of the same slot.
        versioned = ctx_dir / f"{name}.{_iso_dashed_timestamp()}.json"
        target.rename(versioned)

    payload = {
        "name": name,
        "content": content,
        "saved_at": datetime.now().isoformat(),
    }
    target.write_text(json.dumps(payload, indent=2))
    return ToolSuccess(f"Saved context to {target}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_context.py -v`
Expected: 7 tests PASS (2 dispatcher + 5 save).

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/tools/builtins/context.py tests/test_context.py
git commit -m "feat(tools): implement context(save) with auto-versioning"
```

---

### Task 5: Implement context(action="load")

**Files:**
- Modify: `src/ayder_cli/tools/builtins/context.py` (`_load`)
- Modify: `tests/test_context.py`

- [ ] **Step 1: Write the failing tests for load**

Append to `tests/test_context.py`:

```python
def test_load_returns_content_string(project_ctx):
    context(project_ctx=project_ctx, action="save", name="s", content="payload")
    result = context(project_ctx=project_ctx, action="load", name="s")
    assert isinstance(result, ToolSuccess)
    assert str(result) == "payload"


def test_load_missing_name_returns_validation_error(project_ctx):
    result = context(project_ctx=project_ctx, action="load")
    assert isinstance(result, ToolError)
    assert result.category == "validation"


def test_load_missing_slot_lists_available_in_error(project_ctx):
    context(project_ctx=project_ctx, action="save", name="alpha", content="a")
    context(project_ctx=project_ctx, action="save", name="beta", content="b")

    result = context(project_ctx=project_ctx, action="load", name="gamma")
    assert isinstance(result, ToolError)
    msg = str(result)
    assert "gamma" in msg
    assert "alpha" in msg
    assert "beta" in msg


def test_load_missing_slot_no_contexts_error(project_ctx):
    result = context(project_ctx=project_ctx, action="load", name="any")
    assert isinstance(result, ToolError)
    assert "no saved contexts" in str(result).lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_context.py -v`
Expected: 4 new tests FAIL with "load not implemented".

- [ ] **Step 3: Implement _load**

Replace the `_load` placeholder:

```python
def _load(project_ctx: ProjectContext, name: str | None) -> str:
    err = _validate_slot_name(name)
    if err:
        return ToolError(err, "validation")

    ctx_dir = _get_context_dir(project_ctx)
    target = ctx_dir / f"{name}.json"
    if target.exists():
        payload = json.loads(target.read_text())
        return ToolSuccess(payload.get("content", ""))

    available = _current_slot_names(ctx_dir)
    if not available:
        return ToolError(
            f"no saved contexts; cannot load {name!r}", "execution"
        )
    return ToolError(
        f"context {name!r} not found; available: {', '.join(sorted(available))}",
        "execution",
    )


def _current_slot_names(ctx_dir: Path) -> list[str]:
    """Return slot names for current (non-versioned) JSON files.

    A 'current' file matches <name>.json with no extra dot-separated segments.
    """
    if not ctx_dir.exists():
        return []
    names = []
    for p in ctx_dir.iterdir():
        if not p.is_file() or p.suffix != ".json":
            continue
        # p.stem is everything before the last .json — but for "s.timestamp.json"
        # the stem is "s.timestamp". Current files have no dot in the stem.
        if "." in p.stem:
            continue
        names.append(p.stem)
    return names
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_context.py -v`
Expected: 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/tools/builtins/context.py tests/test_context.py
git commit -m "feat(tools): implement context(load) with available-slots error hint"
```

---

### Task 6: Implement context(action="list")

**Files:**
- Modify: `src/ayder_cli/tools/builtins/context.py` (`_list`)
- Modify: `tests/test_context.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
def test_list_empty_returns_empty_array(project_ctx):
    result = context(project_ctx=project_ctx, action="list")
    assert isinstance(result, ToolSuccess)
    assert json.loads(str(result)) == []


def test_list_returns_current_slots_with_metadata(project_ctx):
    context(project_ctx=project_ctx, action="save", name="alpha", content="a")
    context(project_ctx=project_ctx, action="save", name="beta", content="bb")

    result = context(project_ctx=project_ctx, action="list")
    entries = json.loads(str(result))
    names = sorted(e["name"] for e in entries)
    assert names == ["alpha", "beta"]
    for e in entries:
        assert "saved_at" in e
        assert "size_bytes" in e
        assert isinstance(e["size_bytes"], int)


def test_list_excludes_versioned_files(project_ctx):
    context(project_ctx=project_ctx, action="save", name="s", content="v1")
    context(project_ctx=project_ctx, action="save", name="s", content="v2")

    result = context(project_ctx=project_ctx, action="list")
    entries = json.loads(str(result))
    assert len(entries) == 1
    assert entries[0]["name"] == "s"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_context.py -v`
Expected: 3 new tests FAIL with "list not implemented".

- [ ] **Step 3: Implement _list**

Replace the `_list` placeholder:

```python
def _list(project_ctx: ProjectContext) -> str:
    ctx_dir = _get_context_dir(project_ctx)
    if not ctx_dir.exists():
        return ToolSuccess(json.dumps([]))

    entries = []
    for name in _current_slot_names(ctx_dir):
        path = ctx_dir / f"{name}.json"
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        entries.append({
            "name": name,
            "saved_at": payload.get("saved_at", ""),
            "size_bytes": path.stat().st_size,
        })
    return ToolSuccess(json.dumps(entries, indent=2))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_context.py -v`
Expected: 14 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/tools/builtins/context.py tests/test_context.py
git commit -m "feat(tools): implement context(list) returning current slots only"
```

---

### Task 7: Implement context(action="stats")

**Files:**
- Modify: `src/ayder_cli/tools/builtins/context.py` (`_stats`)
- Modify: `tests/test_context.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
def test_stats_returns_token_and_cache_fields(project_ctx):
    from ayder_cli.core.context_manager import ContextStats

    fake_mgr = MagicMock()
    fake_mgr.get_stats.return_value = ContextStats(
        total_tokens=1000,
        available_tokens=9000,
        utilization_percent=10.0,
        message_count=5,
        compaction_count=0,
        messages_compacted=0,
    )
    # Simulate Ollama context manager exposing _cache_monitor
    fake_cache_status = MagicMock(state="hot", hit_ratio=0.87)
    fake_mgr._cache_monitor.last_status = fake_cache_status

    result = context(
        project_ctx=project_ctx, action="stats", context_manager=fake_mgr
    )
    assert isinstance(result, ToolSuccess)
    payload = json.loads(str(result))
    assert payload["total_tokens"] == 1000
    assert payload["available_tokens"] == 9000
    assert payload["utilization_percent"] == 10.0
    assert payload["message_count"] == 5
    assert payload["cache_state"] == "hot"
    assert payload["cache_hit_ratio"] == 0.87
    assert payload["saved_contexts_count"] == 0


def test_stats_cache_na_when_monitor_absent(project_ctx):
    from ayder_cli.core.context_manager import ContextStats

    fake_mgr = MagicMock(spec=["get_stats"])  # no _cache_monitor attr
    fake_mgr.get_stats.return_value = ContextStats(
        total_tokens=100, available_tokens=900,
        utilization_percent=10.0, message_count=1,
        compaction_count=0, messages_compacted=0,
    )

    result = context(
        project_ctx=project_ctx, action="stats", context_manager=fake_mgr
    )
    payload = json.loads(str(result))
    assert payload["cache_state"] == "n/a"
    assert payload["cache_hit_ratio"] is None


def test_stats_counts_saved_contexts(project_ctx):
    from ayder_cli.core.context_manager import ContextStats

    context(project_ctx=project_ctx, action="save", name="a", content="x")
    context(project_ctx=project_ctx, action="save", name="b", content="y")

    fake_mgr = MagicMock(spec=["get_stats"])
    fake_mgr.get_stats.return_value = ContextStats()

    result = context(
        project_ctx=project_ctx, action="stats", context_manager=fake_mgr
    )
    payload = json.loads(str(result))
    assert payload["saved_contexts_count"] == 2


def test_stats_no_context_manager_returns_error(project_ctx):
    result = context(project_ctx=project_ctx, action="stats")
    assert isinstance(result, ToolError)
    assert "context_manager" in str(result).lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_context.py -v`
Expected: 4 new tests FAIL with "stats not implemented".

- [ ] **Step 3: Implement _stats**

Replace the `_stats` placeholder:

```python
def _stats(project_ctx: ProjectContext, context_manager: Any) -> str:
    if context_manager is None:
        return ToolError(
            "stats requires an active context_manager (none injected)",
            "execution",
        )

    stats = context_manager.get_stats()

    # Cache info is optional — only OllamaContextManager exposes _cache_monitor.
    cache_state = "n/a"
    cache_hit_ratio = None
    monitor = getattr(context_manager, "_cache_monitor", None)
    if monitor is not None:
        last = getattr(monitor, "last_status", None)
        if last is not None:
            cache_state = last.state
            cache_hit_ratio = last.hit_ratio

    ctx_dir = _get_context_dir(project_ctx)
    saved_contexts_count = len(_current_slot_names(ctx_dir))

    payload = {
        "total_tokens": stats.total_tokens,
        "available_tokens": stats.available_tokens,
        "utilization_percent": stats.utilization_percent,
        "message_count": stats.message_count,
        "compaction_count": stats.compaction_count,
        "messages_compacted": stats.messages_compacted,
        "cache_state": cache_state,
        "cache_hit_ratio": cache_hit_ratio,
        "saved_contexts_count": saved_contexts_count,
    }
    return ToolSuccess(json.dumps(payload, indent=2))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_context.py -v`
Expected: 18 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/tools/builtins/context.py tests/test_context.py
git commit -m "feat(tools): implement context(stats) reading ContextStats + CacheMonitor"
```

---

### Task 8: Implement context(action="clear")

**Files:**
- Modify: `src/ayder_cli/tools/builtins/context.py` (`_clear`)
- Modify: `tests/test_context.py`

The `clear` action is deferred — the tool saves the summary, sets `app._pending_compact`, and returns. The actual `app.messages` mutation happens in the chat_loop's pre-iteration hook (Task 9).

- [ ] **Step 1: Write the failing tests for clear**

Append:

```python
def test_clear_creates_auto_compact_slot(project_ctx):
    fake_app = MagicMock()
    fake_app._pending_compact = None
    fake_app.messages = [{"role": "user", "content": "x"}]

    result = context(
        project_ctx=project_ctx,
        action="clear",
        content="summary text",
        app=fake_app,
    )
    assert isinstance(result, ToolSuccess)

    ctx_dir = project_ctx.root / ".ayder" / "context"
    slots = list(ctx_dir.glob("auto-compact-*.json"))
    assert len(slots) == 1
    payload = json.loads(slots[0].read_text())
    assert payload["content"] == "summary text"


def test_clear_sets_pending_compact_on_app(project_ctx):
    fake_app = MagicMock()
    fake_app._pending_compact = None
    fake_app.messages = [{"role": "user", "content": "x"}] * 5

    result = context(
        project_ctx=project_ctx,
        action="clear",
        content="summary",
        keep_last_n=2,
        app=fake_app,
    )
    assert isinstance(result, ToolSuccess)
    assert fake_app._pending_compact is not None
    assert fake_app._pending_compact["keep_last_n"] == 2
    assert fake_app._pending_compact["summary_content"] == "summary"
    assert fake_app._pending_compact["summary_name"].startswith("auto-compact-")


def test_clear_uses_explicit_name_when_provided(project_ctx):
    fake_app = MagicMock()
    fake_app._pending_compact = None
    fake_app.messages = []

    context(
        project_ctx=project_ctx,
        action="clear",
        name="my-checkpoint",
        content="summary",
        app=fake_app,
    )
    ctx_dir = project_ctx.root / ".ayder" / "context"
    assert (ctx_dir / "my-checkpoint.json").exists()


def test_clear_requires_content(project_ctx):
    fake_app = MagicMock()
    fake_app._pending_compact = None
    result = context(
        project_ctx=project_ctx, action="clear", app=fake_app
    )
    assert isinstance(result, ToolError)
    assert result.category == "validation"


def test_clear_requires_app(project_ctx):
    result = context(
        project_ctx=project_ctx, action="clear", content="summary"
    )
    assert isinstance(result, ToolError)
    assert "tui session" in str(result).lower() or "app" in str(result).lower()


def test_clear_returns_projected_counts(project_ctx):
    fake_app = MagicMock()
    fake_app._pending_compact = None
    fake_app.messages = [{"role": "user", "content": "x"}] * 10

    result = context(
        project_ctx=project_ctx,
        action="clear",
        content="summary",
        keep_last_n=3,
        app=fake_app,
    )
    payload = json.loads(str(result))
    assert payload["messages_before"] == 10
    assert payload["kept_last_n"] == 3
    assert payload["saved_as"].startswith("auto-compact-")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_context.py -v`
Expected: 6 new tests FAIL with "clear not implemented".

- [ ] **Step 3: Implement _clear**

Replace the `_clear` placeholder:

```python
def _clear(
    project_ctx: ProjectContext,
    name: str | None,
    content: str | None,
    keep_last_n: int,
    context_manager: Any,
    app: Any,
) -> str:
    if content is None or content == "":
        return ToolError("content (summary text) is required for clear", "validation")
    if app is None:
        return ToolError(
            "clear requires a running TUI session (no app handle)",
            "execution",
        )

    slot_name = name or f"auto-compact-{_iso_dashed_timestamp()}"
    save_result = _save(project_ctx, slot_name, content, overwrite=False)
    if isinstance(save_result, ToolError):
        return save_result

    messages_before = len(getattr(app, "messages", []))
    app._pending_compact = {
        "summary_name": slot_name,
        "summary_content": content,
        "keep_last_n": max(0, int(keep_last_n)),
    }

    payload = {
        "messages_before": messages_before,
        "kept_last_n": max(0, int(keep_last_n)),
        "saved_as": slot_name,
        "status": "pending — will be applied at next chat-loop iteration",
    }
    return ToolSuccess(json.dumps(payload, indent=2))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_context.py -v`
Expected: 24 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/tools/builtins/context.py tests/test_context.py
git commit -m "feat(tools): implement context(clear) with deferred compaction"
```

---

### Task 9: Wire pending_compact consumer into chat_loop pre_iteration_hook

**Files:**
- Modify: `src/ayder_cli/tui/app.py` — add the hook function
- Modify: `src/ayder_cli/loops/chat_loop.py:46` — verify hook is being awaited (it already should be per the existing code)
- Test: `tests/tui/test_pending_compact_consumer.py` (new file)

- [ ] **Step 1: Verify chat_loop already calls pre_iteration_hook**

Run: `grep -n "pre_iteration_hook" /Users/sinanalyuruk/Vscode/ayder-cli/src/ayder_cli/loops/chat_loop.py`
Expected output shows the hook is awaited at the start of each iteration (around line 114). If not, this task expands to wire it in — but per the current code it's already there.

- [ ] **Step 2: Write the failing test for the consumer**

Create `tests/tui/test_pending_compact_consumer.py`:

```python
"""Test the consumer function that processes app._pending_compact at
the start of each chat-loop iteration."""
from unittest.mock import MagicMock

import pytest


def _make_app(messages, pending):
    """Build a minimal app-shaped object."""
    app = MagicMock()
    app.messages = messages
    app._pending_compact = pending
    app.context_manager = MagicMock()
    return app


@pytest.mark.anyio
async def test_consumer_no_pending_is_noop():
    from ayder_cli.tui.app import apply_pending_compact

    app = _make_app([{"role": "user", "content": "x"}], pending=None)
    await apply_pending_compact(app, app.messages)

    assert len(app.messages) == 1


@pytest.mark.anyio
async def test_consumer_wipes_messages_preserves_system_and_summary():
    from ayder_cli.tui.app import apply_pending_compact

    msgs = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "old1"},
        {"role": "assistant", "content": "old2"},
        {"role": "user", "content": "old3"},
    ]
    pending = {
        "summary_name": "auto-compact-X",
        "summary_content": "the summary",
        "keep_last_n": 0,
    }
    app = _make_app(msgs, pending)

    await apply_pending_compact(app, app.messages)

    assert app.messages[0] == {"role": "system", "content": "SYS"}
    assert any("the summary" in str(m.get("content", "")) for m in app.messages)
    assert len(app.messages) == 2  # system + summary
    assert app._pending_compact is None


@pytest.mark.anyio
async def test_consumer_preserves_keep_last_n_exchanges():
    """An 'exchange' = one user message and all subsequent
    assistant/tool/tool_result messages until the next user message
    (or end of list)."""
    from ayder_cli.tui.app import apply_pending_compact

    msgs = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2-with-tool"},
        {"role": "tool", "content": "tool-output"},
        {"role": "assistant", "content": "a2-followup"},
    ]
    pending = {
        "summary_name": "auto",
        "summary_content": "sum",
        "keep_last_n": 1,
    }
    app = _make_app(msgs, pending)

    await apply_pending_compact(app, app.messages)

    # Expect: system + summary + the last exchange (u2 → a2-with-tool → tool → a2-followup)
    assert app.messages[0]["role"] == "system"
    assert "sum" in str(app.messages[1].get("content", ""))
    assert app.messages[2:] == [
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2-with-tool"},
        {"role": "tool", "content": "tool-output"},
        {"role": "assistant", "content": "a2-followup"},
    ]
    assert app._pending_compact is None


@pytest.mark.anyio
async def test_consumer_keep_last_n_zero_drops_all_non_system():
    from ayder_cli.tui.app import apply_pending_compact

    msgs = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
    ]
    pending = {"summary_name": "a", "summary_content": "s", "keep_last_n": 0}
    app = _make_app(msgs, pending)

    await apply_pending_compact(app, app.messages)

    # system + summary only
    assert len(app.messages) == 2
    assert app.messages[0]["role"] == "system"


@pytest.mark.anyio
async def test_consumer_resets_context_manager():
    from ayder_cli.tui.app import apply_pending_compact

    msgs = [{"role": "system", "content": "SYS"}]
    pending = {"summary_name": "a", "summary_content": "s", "keep_last_n": 0}
    app = _make_app(msgs, pending)

    await apply_pending_compact(app, app.messages)

    app.context_manager.clear.assert_called_once()
```

Also create `tests/tui/__init__.py` if it doesn't exist:

```python
# empty
```

Add an anyio backend fixture if the test suite doesn't have a global one. Check `tests/conftest.py`:
```
Run: grep -n anyio /Users/sinanalyuruk/Vscode/ayder-cli/tests/conftest.py 2>/dev/null
```
If no anyio_backend fixture exists, prepend to the new test file:

```python
@pytest.fixture
def anyio_backend():
    return "asyncio"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/tui/test_pending_compact_consumer.py -v`
Expected: FAIL — `apply_pending_compact` does not exist.

- [ ] **Step 4: Add apply_pending_compact to app.py**

Append to `src/ayder_cli/tui/app.py` (at module scope, after the class):

```python
def _split_into_exchanges(messages: list[dict]) -> list[list[dict]]:
    """Group messages into exchanges.

    An exchange begins with a user message and includes every subsequent
    assistant/tool/tool_result message until the next user message (or end of
    list). Messages before the first user message (typically the system msg)
    are excluded — caller handles them separately.
    """
    exchanges: list[list[dict]] = []
    current: list[dict] = []
    for m in messages:
        role = m.get("role")
        if role == "user":
            if current:
                exchanges.append(current)
            current = [m]
        elif current:
            # Only collect if we've already seen a user message
            current.append(m)
    if current:
        exchanges.append(current)
    return exchanges


async def apply_pending_compact(app, messages: list[dict]) -> None:
    """Consume ``app._pending_compact`` set by context(action='clear').

    Called by the chat_loop pre_iteration_hook. Wipes ``messages`` (preserving
    the system message and the last `keep_last_n` *exchanges*) and re-seeds
    with the summary. Also resets the context_manager's internal counters.

    An exchange = one user message + all subsequent assistant/tool messages
    until the next user message. This matters because raw message slicing
    can split a tool_result from its assistant call.
    """
    pending = getattr(app, "_pending_compact", None)
    if not pending:
        return

    summary_content = pending.get("summary_content", "")
    keep_last_n = max(0, int(pending.get("keep_last_n", 0)))

    system_msg = None
    if messages and messages[0].get("role") == "system":
        system_msg = messages[0]

    tail_messages: list[dict] = []
    if keep_last_n > 0:
        exchanges = _split_into_exchanges(messages)
        for ex in exchanges[-keep_last_n:]:
            tail_messages.extend(ex)

    messages.clear()
    if system_msg is not None:
        messages.append(system_msg)
    messages.append({
        "role": "user",
        "content": f"[Previous session summary]\n\n{summary_content}",
    })
    messages.extend(tail_messages)

    cm = getattr(app, "context_manager", None)
    # clear() is duck-typed — not all ContextManagerProtocol implementations
    # declare it. DefaultContextManager does; OllamaContextManager may not.
    if cm is not None and hasattr(cm, "clear"):
        cm.clear()

    app._pending_compact = None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/tui/test_pending_compact_consumer.py -v`
Expected: 4 tests PASS.

- [ ] **Step 6: Compose apply_pending_compact with existing agent-summary hook**

`src/ayder_cli/tui/app.py:357-363` already assigns `_inject_summaries` to `self.chat_loop.config.pre_iteration_hook` when `self._agent_registry` is present. **Naively reassigning would silently break agent summary injection.** Compose the two hooks instead.

Replace the block at `src/ayder_cli/tui/app.py:355-363` (the `# Wire pre-iteration hook for agent summary injection` block):

```python
        # Compose the pre-iteration hook from all sources that need it:
        # (a) drain pending_compact set by context(action="clear")
        # (b) inject agent summaries when an agent registry is present
        existing_hook = self.chat_loop.config.pre_iteration_hook

        async def _composed_pre_iteration(messages):
            # 1. Apply any pending compaction first — this may wipe history.
            await apply_pending_compact(self, messages)

            # 2. Drain agent summaries (only if an agent registry exists).
            if self._agent_registry:
                summaries = self._agent_registry.drain_summaries()
                for s in summaries:
                    messages.append({
                        "role": "system",
                        "content": s.format_for_injection(),
                    })

            # 3. Chain any pre-existing hook (defensive: in case a test or
            # plugin installed one before this point).
            if existing_hook is not None:
                result = existing_hook(messages)
                if hasattr(result, "__await__"):
                    await result

        self.chat_loop.config.pre_iteration_hook = _composed_pre_iteration
```

This runs unconditionally (not gated on `_agent_registry`) because pending_compact must always be checked. The agent-summary step is gated internally.

- [ ] **Step 6b: Add regression test for hook composition**

Append to `tests/tui/test_pending_compact_consumer.py`:

```python
@pytest.mark.anyio
async def test_composed_hook_runs_pending_compact_and_agent_summaries():
    """Both hooks must run when both are needed."""
    from ayder_cli.tui.app import apply_pending_compact

    # Set up: app with pending compaction AND a fake agent registry.
    app = _make_app(
        [
            {"role": "system", "content": "SYS"},
            {"role": "user", "content": "u1"},
        ],
        pending={"summary_name": "a", "summary_content": "the-summary", "keep_last_n": 0},
    )

    fake_summary = MagicMock()
    fake_summary.format_for_injection.return_value = "AGENT-SUMMARY"
    agent_registry = MagicMock()
    agent_registry.drain_summaries.return_value = [fake_summary]

    # Inline the composition logic from app.py for the test.
    async def composed(messages):
        await apply_pending_compact(app, messages)
        summaries = agent_registry.drain_summaries()
        for s in summaries:
            messages.append({"role": "system", "content": s.format_for_injection()})

    await composed(app.messages)

    # Should have: system + summary user-message + agent-summary system-message
    assert app.messages[0]["role"] == "system" and app.messages[0]["content"] == "SYS"
    assert "the-summary" in app.messages[1]["content"]
    assert app.messages[-1]["content"] == "AGENT-SUMMARY"
```

- [ ] **Step 7: Run the full test suite to check for regressions**

Run: `.venv/bin/python3 -m pytest tests/ -v --timeout=30`
Expected: All PASS.

- [ ] **Step 8: Commit**

```bash
git add src/ayder_cli/tui/app.py tests/tui/__init__.py tests/tui/test_pending_compact_consumer.py
git commit -m "feat(tui): consume pending_compact at chat_loop iteration boundary"
```

---

### Task 10: Register context tool in TOOL_DEFINITIONS

**Files:**
- Create: `src/ayder_cli/tools/builtins/context_definitions.py`
- Test: `tests/test_context.py` add registration assertions

**Note:** `src/ayder_cli/tools/definition.py` uses `pkgutil.iter_modules` to auto-discover `*_definitions.py` files under `tools/builtins/`. Creating `context_definitions.py` with a `TOOL_DEFINITIONS` tuple is sufficient — **no edits to `definition.py` are needed**.

- [ ] **Step 1: Confirm auto-discovery behavior**

Run: `grep -n "iter_modules\|TOOL_DEFINITIONS" /Users/sinanalyuruk/Vscode/ayder-cli/src/ayder_cli/tools/definition.py | head -10`
Expected: lines around 110 show `pkgutil.iter_modules(package_path)` looping over builtins and pulling each module's `TOOL_DEFINITIONS`. This confirms no manual aggregation is required.

- [ ] **Step 2: Write the failing registration test**

Append to `tests/test_context.py`:

```python
def test_context_tool_is_registered():
    from ayder_cli.tools.definition import TOOL_DEFINITIONS

    names = [td.name for td in TOOL_DEFINITIONS]
    assert "context" in names
    assert "save_memory" not in names
    assert "load_memory" not in names
    assert "save_context_memory" not in names
    assert "load_context_memory" not in names


def test_context_tool_schema_has_all_actions():
    from ayder_cli.tools.definition import TOOL_DEFINITIONS

    td = next(t for t in TOOL_DEFINITIONS if t.name == "context")
    action_schema = td.parameters["properties"]["action"]
    assert set(action_schema["enum"]) == {"save", "load", "list", "stats", "clear"}
    assert td.parameters["required"] == ["action"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python3 -m pytest tests/test_context.py::test_context_tool_is_registered tests/test_context.py::test_context_tool_schema_has_all_actions -v`
Expected: FAIL — `context` not in TOOL_DEFINITIONS.

- [ ] **Step 4: Create context_definitions.py**

Create `src/ayder_cli/tools/builtins/context_definitions.py`:

```python
"""Tool definition for the unified context tool.

Tool: context (replaces save_memory, load_memory, save_context_memory,
load_context_memory).
"""
from typing import Tuple

from ..definition import ToolDefinition

TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="context",
        description=(
            "Session context. action=save snapshots state by name; "
            "load restores by name; list enumerates slots; "
            "stats reports token + cache usage; "
            "clear summarizes the conversation, auto-saves it, and frees the budget."
        ),
        description_template="Context action={action}",
        tags=("core",),
        func_ref="ayder_cli.tools.builtins.context:context",
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["save", "load", "list", "stats", "clear"],
                    "description": "Operation to perform.",
                },
                "name": {
                    "type": "string",
                    "description": "Slot name. Required for save and load.",
                },
                "content": {
                    "type": "string",
                    "description": "Content to snapshot. Required for save and clear.",
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "Save: skip auto-versioning of existing slot.",
                },
                "keep_last_n": {
                    "type": "integer",
                    "description": "Clear: number of most-recent message exchanges to retain verbatim (default 0).",
                },
            },
            "required": ["action"],
        },
        permission="w",
        safe_mode_blocked=False,
    ),
)
```

- [ ] **Step 5: Verify the file was auto-discovered**

No edits needed. Run a quick interactive check:

```bash
.venv/bin/python3 -c "from ayder_cli.tools.definition import TOOL_DEFINITIONS_BY_NAME; print('context' in TOOL_DEFINITIONS_BY_NAME)"
```
Expected output: `True`

- [ ] **Step 6: Run registration tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_context.py -v`
Expected: All 26 tests PASS (24 from earlier + 2 registration).

- [ ] **Step 7: Verify the tool can be dispatched end-to-end via registry**

Append to `tests/test_context.py`:

```python
def test_context_tool_executes_via_registry(tmp_path):
    from ayder_cli.tools.registry import create_default_registry

    project_ctx = ProjectContext(tmp_path)
    reg = create_default_registry(project_ctx)

    result = reg.execute(
        "context",
        {"action": "save", "name": "test", "content": "hello"}
    )
    assert isinstance(result, ToolSuccess)
    assert (tmp_path / ".ayder" / "context" / "test.json").exists()
```

- [ ] **Step 8: Run final test**

Run: `.venv/bin/python3 -m pytest tests/test_context.py -v`
Expected: 27 tests PASS.

- [ ] **Step 9: Commit**

```bash
git add src/ayder_cli/tools/builtins/context_definitions.py src/ayder_cli/tools/definition.py tests/test_context.py
git commit -m "feat(tools): register context ToolDefinition and verify end-to-end dispatch"
```

---

### Task 11: Fix the /clear coordination bug

**Files:**
- Modify: `src/ayder_cli/tui/commands.py:862-875` (`do_clear`)
- Test: `tests/tui/test_do_clear_coordination.py` (new file)

- [ ] **Step 1: Write the failing test**

Create `tests/tui/test_do_clear_coordination.py`:

```python
"""Regression: /clear must reset the context manager's counters, not just
clear app.messages and the chat view."""
from unittest.mock import MagicMock


def test_do_clear_calls_context_manager_clear():
    from ayder_cli.tui.commands import do_clear

    app = MagicMock()
    app.messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u"},
    ]
    app.context_manager = MagicMock()
    chat_view = MagicMock()

    do_clear(app, chat_view)

    app.context_manager.clear.assert_called_once()


def test_do_clear_preserves_system_message():
    from ayder_cli.application.message_contract import get_message_role
    from ayder_cli.tui.commands import do_clear

    app = MagicMock()
    sys_msg = {"role": "system", "content": "sys"}
    app.messages = [sys_msg, {"role": "user", "content": "u"}]
    app.context_manager = MagicMock()

    do_clear(app, MagicMock())

    assert app.messages == [sys_msg]


def test_do_clear_handles_missing_context_manager():
    """If for any reason app.context_manager is absent, /clear must not crash."""
    from ayder_cli.tui.commands import do_clear

    app = MagicMock(spec=["messages"])  # no context_manager attr
    app.messages = []

    do_clear(app, MagicMock())  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/tui/test_do_clear_coordination.py -v`
Expected: `test_do_clear_calls_context_manager_clear` FAILS — current `do_clear` doesn't call `context_manager.clear()`.

- [ ] **Step 3: Patch do_clear**

Edit `src/ayder_cli/tui/commands.py:862-875`. Replace the body of `do_clear` with:

```python
def do_clear(app: AyderApp, chat_view: ChatView) -> None:
    """Clear conversation history and reset context-manager counters."""
    from ayder_cli.application.message_contract import get_message_role

    if app.messages:
        if get_message_role(app.messages[0]) == "system":
            system_msg = app.messages[0]
            app.messages.clear()
            app.messages.append(system_msg)
        else:
            app.messages.clear()

    cm = getattr(app, "context_manager", None)
    if cm is not None and hasattr(cm, "clear"):
        cm.clear()

    chat_view.clear_messages()
    chat_view.add_system_message("Conversation history cleared.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/tui/test_do_clear_coordination.py -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/tui/commands.py tests/tui/test_do_clear_coordination.py
git commit -m "fix(tui): /clear now resets context-manager counters (coordination bug)"
```

---

### Task 12: Add new context slash commands

**Files:**
- Modify: `src/ayder_cli/tui/commands.py`

These slash commands give the user a TUI path to the same operations the LLM uses via `context(action=...)`. They invoke the tool through the registry.

- [ ] **Step 1: Add handler functions**

Append to `src/ayder_cli/tui/commands.py` (above the `COMMAND_MAP` definition near line 1067):

```python
def handle_save_context(app: AyderApp, args: str, chat_view: ChatView) -> None:
    """Handle /save-context <name>. Triggers the LLM to summarize and save."""
    from ayder_cli.prompts import SAVE_CONTEXT_COMMAND_PROMPT_TEMPLATE
    from ayder_cli.application.message_contract import get_message_role, get_message_content

    name = args.strip() or "session"
    if len(app.messages) <= 1:
        chat_view.add_system_message("No conversation to save.")
        return

    convo = ""
    for msg in app.messages:
        role = get_message_role(msg)
        if role in ("user", "assistant"):
            convo += f"[{role}] {get_message_content(msg)}\n\n"

    prompt = SAVE_CONTEXT_COMMAND_PROMPT_TEMPLATE.format(
        name=name, conversation_text=convo
    )
    app.messages.append({"role": "user", "content": prompt})
    chat_view.add_system_message(f"Saving context to slot '{name}'...")
    app.start_llm_processing()


def handle_load_context(app: AyderApp, args: str, chat_view: ChatView) -> None:
    """Handle /load-context <name>. Reads the slot and seeds it into the conversation."""
    name = args.strip()
    if not name:
        chat_view.add_system_message("Usage: /load-context <name>")
        return

    result = app.registry.execute("context", {"action": "load", "name": name})
    if "not found" in str(result).lower():
        chat_view.add_system_message(str(result))
        return

    app.messages.append({
        "role": "user",
        "content": f"[Loaded context '{name}']\n\n{str(result)}",
    })
    chat_view.add_system_message(f"Loaded context from slot '{name}'.")


def handle_list_contexts(app: AyderApp, args: str, chat_view: ChatView) -> None:
    """Handle /list-contexts. Print available context slots."""
    result = app.registry.execute("context", {"action": "list"})
    chat_view.add_system_message(f"Saved contexts:\n{str(result)}")


def handle_context_stats(app: AyderApp, args: str, chat_view: ChatView) -> None:
    """Handle /context-stats. Print current token + cache usage."""
    result = app.registry.execute("context", {"action": "stats"})
    chat_view.add_system_message(f"Context stats:\n{str(result)}")
```

- [ ] **Step 2: Register handlers in COMMAND_MAP**

Find the `COMMAND_MAP` dictionary in `src/ayder_cli/tui/commands.py` (around line 1067). Add entries (alphabetical insertion is fine):

```python
    "/save-context": handle_save_context,
    "/load-context": handle_load_context,
    "/list-contexts": handle_list_contexts,
    "/context-stats": handle_context_stats,
```

- [ ] **Step 3: Add SAVE_CONTEXT_COMMAND_PROMPT_TEMPLATE to prompts.py**

Append to `src/ayder_cli/prompts.py`:

```python
# =============================================================================
# SAVE CONTEXT COMMAND (tui/commands.py)
# =============================================================================
# Used by: tui/commands.py::handle_save_context()

SAVE_CONTEXT_COMMAND_PROMPT_TEMPLATE = """Summarize the following conversation in 200-400 words, focusing on:
- Goals and decisions made
- Code changes attempted or completed
- Open questions or next steps

Then call the context tool exactly once to save it:
  context(action="save", name="{name}", content="<your summary>")

Conversation:
{conversation_text}
"""
```

- [ ] **Step 4: Smoke-test by running existing TUI tests**

Run: `.venv/bin/python3 -m pytest tests/tui/ -v --timeout=30`
Expected: All PASS (the new handlers aren't yet tested but don't break existing tests).

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/tui/commands.py src/ayder_cli/prompts.py
git commit -m "feat(tui): add /save-context, /load-context, /list-contexts, /context-stats"
```

---

### Task 13: Remove the old memory tool surface

**Files:**
- Delete: `src/ayder_cli/tools/builtins/memory.py`
- Delete: `src/ayder_cli/tools/builtins/memory_definitions.py`
- Delete: `tests/test_memory.py`
- Modify: `src/ayder_cli/tui/commands.py` (remove `handle_save_memory`, `handle_load_memory`, map entries)
- Modify: `src/ayder_cli/prompts.py` (remove BOTH `LOAD_MEMORY_COMMAND_PROMPT_TEMPLATE` definitions — at lines ~207 and ~274 — plus `SAVE_MEMORY_COMMAND_PROMPT_TEMPLATE` at line ~236, and the related `COMPACT_COMMAND_PROMPT_TEMPLATE` and comment blocks if they reference `commands/system.py` (orphan; that file no longer exists))
- Modify: `tests/tools/test_definition_discovery.py:276-277`
- Modify: `tests/tools/test_schemas.py:56`

**Note:** `definition.py` uses auto-discovery — deleting `memory_definitions.py` is enough; no manual aggregator edit needed.

- [ ] **Step 1: Locate every reference to the old memory tools**

Run:
```bash
grep -rn "save_memory\|load_memory\|save_context_memory\|load_context_memory\|SAVE_MEMORY_COMMAND_PROMPT_TEMPLATE\|LOAD_MEMORY_COMMAND_PROMPT_TEMPLATE\|/save-memory\|/load-memory" /Users/sinanalyuruk/Vscode/ayder-cli/src /Users/sinanalyuruk/Vscode/ayder-cli/tests
```
Note every file in the output. The deletions/edits below should cover all of them.

- [ ] **Step 2: Delete the memory builtin files**

```bash
rm /Users/sinanalyuruk/Vscode/ayder-cli/src/ayder_cli/tools/builtins/memory.py
rm /Users/sinanalyuruk/Vscode/ayder-cli/src/ayder_cli/tools/builtins/memory_definitions.py
rm /Users/sinanalyuruk/Vscode/ayder-cli/tests/test_memory.py
```

- [ ] **Step 3: Confirm no manual aggregator edit is needed**

`definition.py` uses `pkgutil.iter_modules`-based auto-discovery (Task 10 Step 1 confirmed this). Deleting `memory_definitions.py` in Step 2 above removes the module from discovery automatically.

Sanity check:
```bash
.venv/bin/python3 -c "from ayder_cli.tools.definition import TOOL_DEFINITIONS_BY_NAME; print(sorted(n for n in TOOL_DEFINITIONS_BY_NAME if 'memory' in n))"
```
Expected output: `[]`

- [ ] **Step 4: Remove memory slash commands and handlers**

Edit `src/ayder_cli/tui/commands.py`:
- Delete `handle_save_memory` (around line 369) and `handle_load_memory` (around line 394) functions in their entirety.
- In `COMMAND_MAP` (around line 1067-1068), remove:
  ```python
  "/save-memory": handle_save_memory,
  "/load-memory": handle_load_memory,
  ```

- [ ] **Step 5: Remove memory prompt templates (all of them)**

`src/ayder_cli/prompts.py` contains **two** `LOAD_MEMORY_COMMAND_PROMPT_TEMPLATE` definitions — at lines ~207 and ~274. The first is an orphan (its `# Used by:` comment references `commands/system.py::LoadCommand` which no longer exists). Both must go.

Delete:
- Line ~203-211: the comment block `# Used by: commands/system.py::LoadCommand.execute()` and the first `LOAD_MEMORY_COMMAND_PROMPT_TEMPLATE` definition.
- Line ~214-226: the orphaned `COMPACT_COMMAND_PROMPT_TEMPLATE` if its comment also references the non-existent `commands/system.py`. **Caution:** verify it isn't used by anything else first:
  ```bash
  grep -rn "COMPACT_COMMAND_PROMPT_TEMPLATE" /Users/sinanalyuruk/Vscode/ayder-cli/src /Users/sinanalyuruk/Vscode/ayder-cli/tests
  ```
  `tui/commands.py:handle_compact` uses it — keep this one. Only remove if the only callers were the deleted memory handlers.
- Line ~229-247: the `SAVE_MEMORY_COMMAND_PROMPT_TEMPLATE` block plus its `# SAVE/LOAD MEMORY COMMANDS` section header.
- Line ~270-281: the comment block `# Used by: tui/commands.py::handle_load_memory()` and the second `LOAD_MEMORY_COMMAND_PROMPT_TEMPLATE` definition.

After editing, run a residual-reference check:
```bash
grep -n "SAVE_MEMORY_COMMAND_PROMPT_TEMPLATE\|LOAD_MEMORY_COMMAND_PROMPT_TEMPLATE" /Users/sinanalyuruk/Vscode/ayder-cli/src/ayder_cli/prompts.py
```
Expected: no matches.

- [ ] **Step 6: Update test assertions**

Open `tests/tools/test_definition_discovery.py` around line 276-277. Replace:

```python
        assert 'save_memory' in tool_names
        assert 'load_memory' in tool_names
```

with:

```python
        assert 'context' in tool_names
```

Open `tests/tools/test_schemas.py:56`. Find the list of expected tool names. Remove `"save_memory"`, `"load_memory"`, `"save_context_memory"`, `"load_context_memory"`. Add `"context"`.

- [ ] **Step 7: Run the full test suite**

Run: `.venv/bin/python3 -m pytest tests/ -v --timeout=30`
Expected: All PASS. If anything fails with `ImportError` or `NameError`, you missed a reference — re-run Step 1 to find it.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor(tools): remove obsolete memory tool surface

Drops save_memory, load_memory, save_context_memory, load_context_memory
along with their TUI handlers, slash commands, and prompt templates.
Functionality consolidated into the new context tool."
```

---

### Task 14: Update token-cost note in tool-tag system prompts (optional)

**Files:**
- Modify: `src/ayder_cli/prompts.py` if there's a system prompt that mentions specific memory tools
- Modify: any documentation under `docs/` that lists tools

- [ ] **Step 1: Search for residual references**

Run:
```bash
grep -rn "save_memory\|load_memory\|save_context_memory\|load_context_memory" /Users/sinanalyuruk/Vscode/ayder-cli/src /Users/sinanalyuruk/Vscode/ayder-cli/docs
```

If empty: skip the remaining steps and move to Task 15.

- [ ] **Step 2: Update any remaining references**

For each match, decide:
- Documentation: rewrite to mention `context` instead.
- Source: remove the reference (these were missed in Task 13).

- [ ] **Step 3: Commit (only if changes were made)**

```bash
git add -A
git commit -m "docs: replace memory-tool references with context tool"
```

---

### Task 15: Final verification

- [ ] **Step 1: Run the full test suite with verbose output**

Run: `.venv/bin/python3 -m pytest tests/ -v --timeout=30`
Expected: All tests PASS. New test count should be roughly `previous_count + 30` (new context tests + DI tests + pending_compact tests + do_clear coordination tests, minus the deleted test_memory.py).

- [ ] **Step 2: Run mypy**

Run: `uv run poe typecheck` (defined in `pyproject.toml` as `mypy src/`)
Expected: No errors. If mypy is strict about the `Any` injected types, that's fine — the codebase already uses `Any` for `process_manager`.

- [ ] **Step 3: Run ruff/lint**

Run: `uv run poe lint` or `.venv/bin/python3 -m ruff check src/`
Expected: No errors.

- [ ] **Step 4: Manual TUI smoke test (optional, requires running ayder-cli)**

Start the TUI:
```bash
ayder-cli
```

In the chat, try:
1. `/context-stats` — should print token/cache info.
2. `/list-contexts` — should print `[]`.
3. Type a few messages.
4. Ask the LLM: `Save a context snapshot called "test" with your understanding so far.`
5. The LLM should call `context(action="save", name="test", content="...")`.
6. `/list-contexts` — should show the slot.
7. `/load-context test` — should print the content.
8. `/clear` — should clear messages AND reset counters.
9. Ask the LLM to call `context(action="clear", content="my summary so far", keep_last_n=1)` and confirm `app._pending_compact` is set; on next iteration the messages should be wiped/re-seeded.

If the manual test reveals an issue, file a follow-up — no need to debug in this plan.

- [ ] **Step 5: Final commit (if any cleanup needed)**

If everything is green, no commit needed. Otherwise, fix and commit any remaining issues with descriptive messages.

---

## Self-Review

**Spec coverage:**
- ✅ Polymorphic context tool with 5 actions — Tasks 3-8, 10.
- ✅ Auto-versioning storage with timestamp filenames — Task 4 (`_save`).
- ✅ Storage in `.ayder/context/` separate from `.ayder/memory/` — Task 3 (`_get_context_dir`).
- ✅ `load` returns content string; missing name lists available — Task 5.
- ✅ `list` returns current entries only — Task 6.
- ✅ `stats` reads from `ContextStats` + `CacheMonitor` — Task 7.
- ✅ `clear` deferred via `_pending_compact` — Tasks 8 + 9.
- ✅ Token-budgeted descriptions — Task 10 (the description matches the spec).
- ✅ `/clear` coordination fix — Task 11.
- ✅ New slash commands — Task 12.
- ✅ Old memory tool removal — Task 13.
- ✅ DI extension for `context_manager` + `app` — Tasks 1-2.

**Open items resolved during planning:**
- ✅ Where `CacheMonitor` lives: `OllamaContextManager._cache_monitor`, accessed via `getattr` on the context manager — no separate DI injection needed.
- ✅ Where `ContextManagerProtocol` lives: `RuntimeComponents.context_manager`, passed to registry via `create_default_registry`.
- ✅ Chat-loop re-entrancy for clear: handled by deferred pattern (Task 9). The tool only sets a flag; mutation happens at the safe pre-iteration boundary.

**Still deferred (out of scope for this plan):**
- Garbage collection of accumulated `auto-compact-*` slots — flagged as a follow-up.
- Provider/model name in `stats` payload — flagged as a follow-up.
- Adding `clear()` to `ContextManagerProtocol`. The plan uses `hasattr(cm, "clear")` because only `DefaultContextManager` currently implements it. Promoting it to the protocol is a separate refactor with broader implications (touches `OllamaContextManager` and any future provider).
- Agent-runtime context isolation. Currently all agents share `.ayder/context/` via the parent's `project_ctx`. Slot-name conventions (e.g., agent-name prefix) can give logical isolation without a structural change.

**Placeholder scan:** No `TBD`, `TODO`, or "implement later" in any task. Each task has the complete code an engineer needs.

**Type consistency check:**
- `_pending_compact` shape — set in Task 8 (`summary_name`, `summary_content`, `keep_last_n`), consumed in Task 9 (same keys). ✅
- `context_manager` parameter — consistent across `_stats` (Task 7) and `_clear` (Task 8) signatures. ✅
- `app` parameter — consistent across `_clear` (Task 8) and registry injection (Task 1). ✅
- Tool name `context` — used in Tasks 3, 10, 12, 13 consistently. ✅
