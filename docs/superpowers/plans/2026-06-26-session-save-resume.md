# Session Auto-Save & `--resume` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-save the TUI conversation to `.ayder/sessions/<id>.json` on exit and restore it with `ayder --resume <id>`.

**Architecture:** A new pure module `core/session.py` owns all persistence (id generation, save/load, prefix resolution) plus tiny presentation helpers (replay mapping, exit announcement) — no Textual dependency, fully unit-testable. `run_tui` calls the announce helper in a `try/finally` after `app.run()`. `AyderApp` accepts restored messages, skips rebuilding the system prompt when resuming, and replays prior turns. `cli.py` adds `--resume`, which is mutually exclusive with session-shaping flags.

**Tech Stack:** Python 3, argparse, Textual, pytest. Stdlib only (`uuid`, `json`, `datetime`, `pathlib`).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-06-26-session-save-resume-design.md`.
- Session files: `.ayder/sessions/<id>.json`; `.ayder/` is already gitignored — never stage anything under it.
- Session ID format: `xxxx-xxxx` (8 lowercase hex chars from `uuid4`, single dash).
- Save the message list **verbatim**, including `messages[0]` (the system prompt) and all `tool_calls`/`tool` results.
- Resume restores `model`, `agent_mode`, `safe_mode`, `permissions` from the file; `--resume` takes no session-shaping flags (`-c/--config`, `--verbose`, `--logging-level` remain allowed).
- Path-resolving session functions default `root` to `Path.cwd()`.
- All work is TDD: failing test first, minimal impl, passing test, commit.
- Run tests with: `uv run pytest <path> -v` (or `python -m pytest` if `uv` unavailable).

---

### Task 1: `core/session.py` — persistence core

**Files:**
- Create: `src/ayder_cli/core/session.py`
- Test: `tests/core/test_session.py`

**Interfaces:**
- Consumes: nothing (stdlib only).
- Produces:
  - `SessionError(Exception)`, `SessionNotFound(SessionError)`, `SessionAmbiguous(SessionError)`
  - `@dataclass(frozen=True) SessionData` with fields: `session_id: str`, `messages: list[dict]`, `model: str | None`, `agent_mode: bool`, `safe_mode: bool`, `permissions: set[str]`, `created_at: str`, `updated_at: str`, `path: Path`
  - `sessions_dir(root: Path | None = None) -> Path`
  - `new_session_id(root: Path | None = None) -> str`
  - `save_session(messages: list[dict], *, root: Path | None = None, session_id: str | None = None, model: str | None = None, agent_mode: bool = False, safe_mode: bool = False, permissions: set[str] | None = None) -> str`
  - `resolve_session_id(token: str, root: Path | None = None) -> str`
  - `load_session(token: str, root: Path | None = None) -> SessionData`
  - `list_sessions(root: Path | None = None) -> list[str]`

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_session.py`:

```python
"""Tests for session save/load/resolve (core/session.py)."""

import json
import re

import pytest

from ayder_cli.core.session import (
    SessionAmbiguous,
    SessionNotFound,
    load_session,
    new_session_id,
    resolve_session_id,
    save_session,
    sessions_dir,
)


def _msgs():
    return [
        {"role": "system", "content": "SYS PROMPT"},
        {"role": "user", "content": "fix the bug"},
        {
            "role": "assistant",
            "content": "on it",
            "tool_calls": [{"id": "c1", "function": {"name": "bash"}}],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "done"},
    ]


def test_sessions_dir(tmp_path):
    assert sessions_dir(tmp_path) == tmp_path / ".ayder" / "sessions"


def test_new_session_id_format(tmp_path):
    sid = new_session_id(tmp_path)
    assert re.fullmatch(r"[0-9a-f]{4}-[0-9a-f]{4}", sid)


def test_new_session_id_unique_vs_existing(tmp_path):
    sid1 = save_session(_msgs(), root=tmp_path)
    sid2 = new_session_id(tmp_path)
    assert sid2 != sid1


def test_save_load_roundtrip(tmp_path):
    sid = save_session(
        _msgs(), root=tmp_path, model="qwen", agent_mode=True,
        safe_mode=False, permissions={"r", "w", "x", "http"},
    )
    data = load_session(sid, root=tmp_path)
    assert data.session_id == sid
    assert data.messages == _msgs()              # verbatim, incl. system + tool_calls
    assert data.model == "qwen"
    assert data.agent_mode is True
    assert data.permissions == {"r", "w", "x", "http"}


def test_resolve_exact_and_prefix(tmp_path):
    sid = save_session(_msgs(), root=tmp_path)
    assert resolve_session_id(sid, root=tmp_path) == sid
    assert resolve_session_id(sid[:4], root=tmp_path) == sid          # prefix
    assert resolve_session_id(sid.replace("-", ""), root=tmp_path) == sid  # dash-insensitive


def test_resolve_not_found(tmp_path):
    save_session(_msgs(), root=tmp_path)
    with pytest.raises(SessionNotFound):
        resolve_session_id("zzzz", root=tmp_path)


def test_resolve_ambiguous(tmp_path):
    # Two ids sharing a prefix -> ambiguous on that prefix.
    save_session(_msgs(), root=tmp_path, session_id="abcd-0001")
    save_session(_msgs(), root=tmp_path, session_id="abcd-0002")
    with pytest.raises(SessionAmbiguous):
        resolve_session_id("abcd", root=tmp_path)


def test_resave_preserves_created_at(tmp_path):
    sid = save_session(_msgs(), root=tmp_path)
    created = json.loads((sessions_dir(tmp_path) / f"{sid}.json").read_text())["created_at"]
    save_session(_msgs() + [{"role": "user", "content": "more"}],
                 root=tmp_path, session_id=sid)
    reread = json.loads((sessions_dir(tmp_path) / f"{sid}.json").read_text())
    assert reread["created_at"] == created
    assert reread["message_count"] == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/core/test_session.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ayder_cli.core.session'`.

- [ ] **Step 3: Write the implementation**

Create `src/ayder_cli/core/session.py`:

```python
"""Save and restore TUI chat sessions under .ayder/sessions/.

A session file stores the conversation verbatim (including the system prompt
and all tool calls/results) plus the settings needed to resume it without any
CLI flags. Ids are short `xxxx-xxxx` hex strings; resume matches by exact id or
unique prefix.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


class SessionError(Exception):
    """Base error for session save/load problems."""


class SessionNotFound(SessionError):
    """No saved session matches the given id or prefix."""


class SessionAmbiguous(SessionError):
    """More than one saved session matches the given prefix."""


@dataclass(frozen=True)
class SessionData:
    session_id: str
    messages: list[dict]
    model: str | None
    agent_mode: bool
    safe_mode: bool
    permissions: set[str]
    created_at: str
    updated_at: str
    path: Path


def sessions_dir(root: Path | None = None) -> Path:
    """Return <root>/.ayder/sessions (root defaults to cwd)."""
    base = root if root is not None else Path.cwd()
    return base / ".ayder" / "sessions"


def new_session_id(root: Path | None = None) -> str:
    """Generate a collision-free 'xxxx-xxxx' id within the sessions dir."""
    directory = sessions_dir(root)
    while True:
        raw = uuid.uuid4().hex[:8]
        sid = f"{raw[:4]}-{raw[4:]}"
        if not (directory / f"{sid}.json").exists():
            return sid


def list_sessions(root: Path | None = None) -> list[str]:
    """Return saved session ids (filename stems), sorted."""
    directory = sessions_dir(root)
    if not directory.is_dir():
        return []
    return sorted(p.stem for p in directory.glob("*.json"))


def save_session(
    messages: list[dict],
    *,
    root: Path | None = None,
    session_id: str | None = None,
    model: str | None = None,
    agent_mode: bool = False,
    safe_mode: bool = False,
    permissions: set[str] | None = None,
) -> str:
    """Write *messages* + settings to .ayder/sessions/<id>.json; return the id.

    Reusing an existing *session_id* updates that file in place, preserving its
    original ``created_at`` and bumping ``updated_at``.
    """
    directory = sessions_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    if session_id is None:
        session_id = new_session_id(root)
    path = directory / f"{session_id}.json"

    now = datetime.now().isoformat()
    created_at = now
    if path.exists():
        try:
            created_at = json.loads(path.read_text(encoding="utf-8")).get(
                "created_at", now
            )
        except (OSError, json.JSONDecodeError):
            created_at = now

    base = root if root is not None else Path.cwd()
    payload = {
        "schema_version": 1,
        "session_id": session_id,
        "created_at": created_at,
        "updated_at": now,
        "model": model,
        "agent_mode": bool(agent_mode),
        "safe_mode": bool(safe_mode),
        "permissions": sorted(permissions) if permissions else [],
        "cwd": str(base.resolve()),
        "message_count": len(messages),
        "messages": messages,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return session_id


def resolve_session_id(token: str, root: Path | None = None) -> str:
    """Resolve *token* to a full session id by exact match or unique prefix.

    Matching ignores dashes and case. Raises SessionNotFound / SessionAmbiguous.
    """
    norm = token.strip().lower().replace("-", "")
    ids = list_sessions(root)
    for sid in ids:
        if sid.lower().replace("-", "") == norm:
            return sid
    matches = [sid for sid in ids if sid.lower().replace("-", "").startswith(norm)]
    if len(matches) == 1:
        return matches[0]
    available = ", ".join(ids) if ids else "(none)"
    if not matches:
        raise SessionNotFound(
            f"no session matching '{token}'. Available: {available}"
        )
    raise SessionAmbiguous(
        f"'{token}' matches multiple sessions: {', '.join(matches)}"
    )


def load_session(token: str, root: Path | None = None) -> SessionData:
    """Resolve *token* and load the session file into a SessionData."""
    sid = resolve_session_id(token, root)
    path = sessions_dir(root) / f"{sid}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SessionError(f"could not read session {sid}: {exc}") from exc
    return SessionData(
        session_id=data.get("session_id", sid),
        messages=data.get("messages", []),
        model=data.get("model"),
        agent_mode=bool(data.get("agent_mode", False)),
        safe_mode=bool(data.get("safe_mode", False)),
        permissions=set(data.get("permissions", [])),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
        path=path,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/core/test_session.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/core/session.py tests/core/test_session.py
git commit -m "feat(session): persistence core for save/load/resolve"
```

---

### Task 2: `core/session.py` — exit + replay helpers

**Files:**
- Modify: `src/ayder_cli/core/session.py` (append functions)
- Test: `tests/core/test_session.py` (append tests)

**Interfaces:**
- Consumes: `save_session` (Task 1).
- Produces:
  - `should_save_session(messages: list[dict]) -> bool` — True iff any message has `role == "user"`.
  - `resume_hint(session_id: str) -> str` — the two-line "Session saved..." text.
  - `persist_and_announce(messages: list[dict], *, root: Path | None = None, session_id: str | None = None, model: str | None = None, agent_mode: bool = False, safe_mode: bool = False, permissions: set[str] | None = None, out=print) -> str | None` — saves + prints the hint when there is a user message; otherwise returns None and prints nothing.
  - `messages_to_replay_items(messages: list[dict]) -> list[tuple[str, str]]` — `("user"|"assistant", content)` pairs; skips system/tool messages and empty content.

- [ ] **Step 1: Write the failing tests**

Append to `tests/core/test_session.py`:

```python
from ayder_cli.core.session import (
    messages_to_replay_items,
    persist_and_announce,
    resume_hint,
    should_save_session,
)


def test_should_save_session():
    assert should_save_session([{"role": "system", "content": "s"}]) is False
    assert should_save_session(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "hi"}]
    ) is True


def test_resume_hint_mentions_id_and_command():
    text = resume_hint("a1b2-c3d4")
    assert "a1b2-c3d4" in text
    assert "ayder --resume a1b2-c3d4" in text


def test_persist_and_announce_skips_without_user(tmp_path):
    printed = []
    result = persist_and_announce(
        [{"role": "system", "content": "s"}], root=tmp_path, out=printed.append
    )
    assert result is None
    assert printed == []
    assert list((tmp_path / ".ayder" / "sessions").glob("*.json")) == []


def test_persist_and_announce_saves_and_prints(tmp_path):
    printed = []
    result = persist_and_announce(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "hi"}],
        root=tmp_path, out=printed.append,
    )
    assert result is not None
    assert (tmp_path / ".ayder" / "sessions" / f"{result}.json").exists()
    assert any("ayder --resume" in line for line in printed)


def test_persist_and_announce_reuses_id(tmp_path):
    result = persist_and_announce(
        [{"role": "user", "content": "hi"}],
        root=tmp_path, session_id="a1b2-c3d4", out=lambda _x: None,
    )
    assert result == "a1b2-c3d4"
    assert (tmp_path / ".ayder" / "sessions" / "a1b2-c3d4.json").exists()


def test_messages_to_replay_items():
    msgs = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1"}]},
        {"role": "tool", "tool_call_id": "c1", "content": "result"},
        {"role": "user", "content": "thanks"},
    ]
    assert messages_to_replay_items(msgs) == [
        ("user", "hi"),
        ("assistant", "hello"),
        ("user", "thanks"),
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/core/test_session.py -k "should_save or resume_hint or persist or replay_items" -v`
Expected: FAIL with `ImportError: cannot import name 'should_save_session'`.

- [ ] **Step 3: Write the implementation**

Append to `src/ayder_cli/core/session.py`:

```python
def should_save_session(messages: list[dict]) -> bool:
    """True if the conversation has at least one user turn worth saving."""
    return any(m.get("role") == "user" for m in messages)


def resume_hint(session_id: str) -> str:
    """The exit message telling the user how to resume the saved session."""
    return f"Session saved. Resume with:\n  ayder --resume {session_id}"


def persist_and_announce(
    messages: list[dict],
    *,
    root: Path | None = None,
    session_id: str | None = None,
    model: str | None = None,
    agent_mode: bool = False,
    safe_mode: bool = False,
    permissions: set[str] | None = None,
    out=print,
) -> str | None:
    """Save the session on exit and print the resume hint.

    Returns the session id, or None when there is nothing worth saving.
    """
    if not should_save_session(messages):
        return None
    sid = save_session(
        messages,
        root=root,
        session_id=session_id,
        model=model,
        agent_mode=agent_mode,
        safe_mode=safe_mode,
        permissions=permissions,
    )
    out(resume_hint(sid))
    return sid


def messages_to_replay_items(messages: list[dict]) -> list[tuple[str, str]]:
    """Map saved messages to ('user'|'assistant', text) pairs for replay.

    Skips the system prompt, tool messages, and empty (tool-call-only) turns.
    """
    items: list[tuple[str, str]] = []
    for m in messages:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        content = m.get("content")
        if isinstance(content, str) and content.strip():
            items.append((role, content))
    return items
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/core/test_session.py -v`
Expected: PASS (all tests, including Task 1's).

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/core/session.py tests/core/test_session.py
git commit -m "feat(session): exit announce + replay-mapping helpers"
```

---

### Task 3: `AyderApp` — restore on resume + replay

**Files:**
- Modify: `src/ayder_cli/tui/app.py` (`__init__` ~201-225, ~273-274, ~328-331; `on_mount` ~621-641; add two methods)
- Test: `tests/tui/test_resume.py` (new)

**Interfaces:**
- Consumes: `messages_to_replay_items` (Task 2); `ChatView.add_user_message`, `ChatView.add_assistant_message`, `ChatView.add_system_message`.
- Produces:
  - `AyderApp.__init__` accepts `initial_messages: list[dict] | None = None` and `resume_session_id: str | None = None`.
  - Attributes: `self.resume_session_id`, `self._resuming: bool`.
  - `AyderApp._replay_history(self, chat_view) -> None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/tui/test_resume.py`:

```python
"""Resume restore + replay for AyderApp."""

from unittest.mock import MagicMock

from ayder_cli.tui.app import AyderApp


def _restored():
    return [
        {"role": "system", "content": "RESTORED SYS"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]


def test_init_seeds_messages_and_skips_system_rebuild():
    app = AyderApp(
        model="test",
        initial_messages=_restored(),
        resume_session_id="a1b2-c3d4",
    )
    assert app._resuming is True
    assert app.resume_session_id == "a1b2-c3d4"
    # No fresh system prompt appended; restored list is used verbatim.
    assert app.messages == _restored()
    assert app.messages[0]["content"] == "RESTORED SYS"


def test_init_without_resume_builds_system_prompt():
    app = AyderApp(model="test")
    assert app._resuming is False
    assert app.resume_session_id is None
    assert app.messages and app.messages[0]["role"] == "system"


def test_replay_history_dispatches_to_chat_view():
    app = AyderApp(model="test", initial_messages=_restored(),
                   resume_session_id="a1b2-c3d4")
    chat_view = MagicMock()
    app._replay_history(chat_view)
    chat_view.add_user_message.assert_called_once_with("hi")
    chat_view.add_assistant_message.assert_called_once_with("hello")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/tui/test_resume.py -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'initial_messages'`.

- [ ] **Step 3a: Add the constructor parameters**

In `src/ayder_cli/tui/app.py`, change the `__init__` signature (currently ends at line 208):

```python
    def __init__(
        self,
        model: str = "default",
        safe_mode: bool = False,
        permissions: set | None = None,
        agent_mode: bool = False,
        system_prompt_override: str | None = None,
        initial_messages: list[dict] | None = None,
        resume_session_id: str | None = None,
        **kwargs,
    ):
```

- [ ] **Step 3b: Record resume state**

After the line `self._system_prompt_override = system_prompt_override` (line ~225), add:

```python
        self.resume_session_id = resume_session_id
        self._resuming = bool(
            initial_messages and initial_messages[0].get("role") == "system"
        )
```

- [ ] **Step 3c: Seed messages and skip rebuild when resuming**

Replace the two lines (currently ~273-274):

```python
        self.messages: list[dict] = []
        self._init_system_prompt()
```

with:

```python
        self.messages: list[dict] = list(initial_messages) if initial_messages else []
        if not self._resuming:
            self._init_system_prompt()
```

- [ ] **Step 3d: Do not re-inject agent capability prompts on resume**

Change the capability-prompt guard (currently ~330):

```python
            if cap_prompts and self.messages and self.messages[0].get("role") == "system":
```

to:

```python
            if (
                not self._resuming
                and cap_prompts
                and self.messages
                and self.messages[0].get("role") == "system"
            ):
```

- [ ] **Step 3e: Add the replay method**

Add this method to `AyderApp` (place it just after `_init_system_prompt`, before `update_system_prompt_model` at ~425):

```python
    def _replay_history(self, chat_view) -> None:
        """Render restored user/assistant turns into the chat view on resume."""
        from ayder_cli.core.session import messages_to_replay_items

        for role, content in messages_to_replay_items(self.messages):
            if role == "user":
                chat_view.add_user_message(content)
            else:
                chat_view.add_assistant_message(content)
```

- [ ] **Step 3f: Replay in `on_mount`**

In `on_mount`, after the banner Static is mounted (currently line 638 `chat_view.mount(Static(banner, classes="banner-content"))`) and before `self.call_after_refresh(self._position_banner)` (line 641), add:

```python
        if self._resuming:
            chat_view.add_system_message(f"↻ Resumed session {self.resume_session_id}")
            self._replay_history(chat_view)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/tui/test_resume.py -v`
Expected: PASS (3 tests).

Also run existing TUI tests to confirm no regression:
Run: `uv run pytest tests/tui/test_input_box.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/tui/app.py tests/tui/test_resume.py
git commit -m "feat(tui): restore + replay conversation on resume"
```

---

### Task 4: `run_tui` — save on exit, accept restored messages

**Files:**
- Modify: `src/ayder_cli/tui/__init__.py` (`run_tui`, lines 30-71)
- Test: `tests/tui/test_resume.py` (append)

**Interfaces:**
- Consumes: `persist_and_announce` (Task 2); `AyderApp(initial_messages=, resume_session_id=)` and `AyderApp.resume_session_id` (Task 3).
- Produces: `run_tui(..., initial_messages: list[dict] | None = None, resume_session_id: str | None = None) -> None` that saves the session after `app.run()` returns.

- [ ] **Step 1: Write the failing tests**

Append to `tests/tui/test_resume.py`:

```python
class _FakeApp:
    """Stand-in for AyderApp so run_tui can be tested without Textual."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.messages = kwargs.get("initial_messages") or [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "hi"},
        ]
        self.resume_session_id = kwargs.get("resume_session_id")
        self.model = kwargs.get("model", "test")
        self.safe_mode = kwargs.get("safe_mode", False)
        self.permissions = kwargs.get("permissions") or {"r"}

    def run(self, **kwargs):
        return None


def test_run_tui_saves_session_on_exit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("ayder_cli.tui.AyderApp", _FakeApp)
    from ayder_cli.tui import run_tui

    run_tui(permissions={"r", "w"}, model="m")

    files = list((tmp_path / ".ayder" / "sessions").glob("*.json"))
    assert len(files) == 1


def test_run_tui_reuses_resume_session_id(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("ayder_cli.tui.AyderApp", _FakeApp)
    from ayder_cli.tui import run_tui

    run_tui(
        initial_messages=[
            {"role": "system", "content": "s"},
            {"role": "user", "content": "hi"},
        ],
        resume_session_id="a1b2-c3d4",
    )
    assert (tmp_path / ".ayder" / "sessions" / "a1b2-c3d4.json").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/tui/test_resume.py -k run_tui -v`
Expected: FAIL — `run_tui()` rejects `initial_messages`, and no session file is written.

- [ ] **Step 3: Update `run_tui`**

Replace the body of `run_tui` in `src/ayder_cli/tui/__init__.py` (lines 30-71) with:

```python
def run_tui(
    model: str = "default",
    safe_mode: bool = False,
    permissions: set | None = None,
    agent_mode: bool = False,
    system_prompt_override: str | None = None,
    initial_messages: list[dict] | None = None,
    resume_session_id: str | None = None,
) -> None:
    """
    Run the CLI-style TUI application.

    Args:
        model: The LLM model name to use
        safe_mode: Whether to enable safe mode
        permissions: Set of granted permission levels ("r", "w", "x")
        agent_mode: When True, inject the AGENTIC orchestrator system prompt
            so the main LLM drives the multi-agent harness (ayder-cli --agent).
        system_prompt_override: When set, use this text as the system-prompt base
            instead of the built-in prompts.py prompt (ayder --system-prompt FILE).
        initial_messages: When resuming, the restored conversation (incl. the
            saved system prompt) to seed the app with.
        resume_session_id: When resuming, the id of the session being continued
            so save-on-exit updates the same file.
    """
    import sys
    from ayder_cli.providers import ProviderUnavailableError
    from ayder_cli.core.session import persist_and_announce

    try:
        app = AyderApp(
            model=model, safe_mode=safe_mode, permissions=permissions,
            agent_mode=agent_mode, system_prompt_override=system_prompt_override,
            initial_messages=initial_messages, resume_session_id=resume_session_id,
        )
    except ProviderUnavailableError as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(1)

    try:
        app.run(inline=True, mouse=False)
    finally:
        # Ensure mouse reporting is disabled after exit — Textual's driver may
        # leave it on if the shutdown path doesn't fully complete (e.g. Ctrl+Q).
        sys.stdout.write(
            "\033[?1000l"  # disable mouse click tracking
            "\033[?1002l"  # disable mouse button-event tracking
            "\033[?1003l"  # disable all mouse tracking
            "\033[?1006l"  # disable SGR extended mouse mode
        )
        sys.stdout.flush()

        # Auto-save the conversation so it can be resumed later.
        try:
            persist_and_announce(
                app.messages,
                session_id=app.resume_session_id,
                model=app.model,
                agent_mode=agent_mode,
                safe_mode=app.safe_mode,
                permissions=app.permissions,
            )
        except Exception as exc:  # never let a save failure mask the exit
            print(f"Warning: could not save session: {exc}", file=sys.stderr)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/tui/test_resume.py -v`
Expected: PASS (all 5 tests in the file).

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/tui/__init__.py tests/tui/test_resume.py
git commit -m "feat(tui): auto-save session on exit, accept restored messages"
```

---

### Task 5: `cli.py` — `--resume` flag, guard, and handler

**Files:**
- Modify: `src/ayder_cli/cli.py` (`_add_common_args` ~127; `main()` after plugin subcommands ~317)
- Test: `tests/test_cli.py` (append a `TestMainResume` class)

**Interfaces:**
- Consumes: `load_session`, `SessionError`, `list_sessions` (Tasks 1-2); `run_tui(initial_messages=, resume_session_id=)` (Task 4).
- Produces: `--resume ID` CLI option; resume launch path in `main()`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
class TestMainResume:
    """Test --resume flag parsing, conflict guard, and launch."""

    def test_resume_arg_parses(self):
        from ayder_cli.cli import create_parser

        args = create_parser().parse_args(['--resume', 'a1b2-c3d4'])
        assert args.resume == 'a1b2-c3d4'

    def test_resume_conflicts_with_session_flags(self):
        from ayder_cli.cli import main

        with patch.object(sys, 'argv', ['ayder', '--resume', 'a1b2', '-w']), \
             patch.object(sys.stdin, 'isatty', return_value=True):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 1

    def test_resume_loads_and_launches(self, tmp_path, monkeypatch):
        from ayder_cli.cli import main
        from ayder_cli.core.session import save_session

        monkeypatch.chdir(tmp_path)
        sid = save_session(
            [{"role": "system", "content": "SYS"},
             {"role": "user", "content": "hi"}],
            model="qwen", agent_mode=True, permissions={"r", "w", "x", "http"},
        )

        with patch.object(sys, 'argv', ['ayder', '--resume', sid]), \
             patch.object(sys.stdin, 'isatty', return_value=True), \
             patch('ayder_cli.tui.run_tui') as mock_run_tui:
            main()

        kwargs = mock_run_tui.call_args[1]
        assert kwargs['resume_session_id'] == sid
        assert kwargs['initial_messages'][1]['content'] == "hi"
        assert kwargs['agent_mode'] is True
        assert kwargs['permissions'] == {"r", "w", "x", "http"}

    def test_resume_bad_id_exits(self, tmp_path, monkeypatch):
        from ayder_cli.cli import main

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, 'argv', ['ayder', '--resume', 'zzzz']), \
             patch.object(sys.stdin, 'isatty', return_value=True):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::TestMainResume -v`
Expected: FAIL — `args.resume` does not exist / resume path not implemented.

- [ ] **Step 3a: Add the `--resume` argument**

In `src/ayder_cli/cli.py`, inside `_add_common_args`, add this just before the version flag (currently line 127 `# Version flag`):

```python
    parser.add_argument(
        "--resume",
        type=str,
        metavar="ID",
        default=None,
        help="Resume a saved session by id (or unique prefix) from "
        ".ayder/sessions/. Takes no other session options "
        "(restores the original model, permissions, and system prompt).",
    )

```

- [ ] **Step 3b: Add the resume handler in `main()`**

In `main()`, immediately after the plugin-subcommand handling (after the `update-plugin` block that ends at line 317, before the `# Build granted permissions set` comment at line 319), insert:

```python
    # --resume: restore a saved session and launch the TUI. It is mutually
    # exclusive with session-shaping options — the saved file already carries
    # the model, permissions, agent mode, and system prompt.
    if getattr(args, "resume", None):
        _conflicts: list[str] = []
        if getattr(args, "agent", False):
            _conflicts.append("--agent")
        if getattr(args, "system_prompt", None):
            _conflicts.append("--system-prompt")
        if getattr(args, "w", False):
            _conflicts.append("-w")
        if getattr(args, "x", False):
            _conflicts.append("-x")
        if getattr(args, "http", False):
            _conflicts.append("--http")
        if getattr(args, "file", None):
            _conflicts.append("--file/-f")
        if getattr(args, "stdin", False):
            _conflicts.append("--stdin")
        if getattr(args, "command", None):
            _conflicts.append("a command")
        if getattr(args, "implement", None):
            _conflicts.append("--implement")
        if getattr(args, "implement_all", False):
            _conflicts.append("--implement-all")
        if getattr(args, "tasks", False):
            _conflicts.append("--tasks")
        if getattr(args, "temporal_task_queue", None):
            _conflicts.append("--temporal-task-queue")
        if getattr(args, "temporal_prompt", None):
            _conflicts.append("--temporal-prompt")
        if _conflicts:
            print(
                "Error: --resume takes no other options — it restores the "
                "original session's settings. Usage: ayder --resume <id>",
                file=sys.stderr,
            )
            sys.exit(1)

        from ayder_cli.core.session import SessionError, load_session

        try:
            sess = load_session(args.resume)
        except SessionError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        from ayder_cli.tui import run_tui

        run_tui(
            model=sess.model or "default",
            safe_mode=sess.safe_mode,
            permissions=set(sess.permissions),
            agent_mode=sess.agent_mode,
            initial_messages=sess.messages,
            resume_session_id=sess.session_id,
        )
        return

```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py::TestMainResume -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/cli.py tests/test_cli.py
git commit -m "feat(cli): --resume to restore a saved session"
```

---

### Task 6: Full-suite verification + manual smoke

**Files:** none (verification only).

- [ ] **Step 1: Run the project checks**

Run: `uv run poe check-all`
Expected: lint (ruff), type-check (mypy), and the full pytest suite pass. If `poe` is unavailable, run `uv run pytest -q` plus `uv run ruff check src tests` and `uv run mypy src`.

- [ ] **Step 2: Manual smoke — save**

```bash
uv run ayder
# type a message, get a reply, then Ctrl+Q
```
Expected: on exit, stdout shows:
```
Session saved. Resume with:
  ayder --resume <id>
```
and `.ayder/sessions/<id>.json` exists.

- [ ] **Step 3: Manual smoke — resume**

```bash
uv run ayder --resume <id-or-prefix>
```
Expected: the TUI opens, shows "↻ Resumed session <id>" and the prior user/assistant turns, and the model has full context. Quit again → the same `<id>.json` is updated (its `created_at` unchanged).

- [ ] **Step 4: Manual smoke — guard + bad id**

```bash
uv run ayder --resume <id> -w     # expect: error about no other options, exit 1
uv run ayder --resume nope        # expect: "no session matching 'nope'. Available: ..."
```

- [ ] **Step 5: Commit (if any verification fixups were needed)**

```bash
git add -A
git commit -m "test(session): verification fixups"
```

---

## Self-Review

**Spec coverage:**
- Save on exit (`.ayder/sessions/<id>.json`, full messages incl. system prompt + metadata) → Tasks 1, 2, 4.
- Skip empty conversations → `should_save_session` (Task 2), tested.
- Resume hint printed on exit → `resume_hint` / `persist_and_announce` (Task 2), wired in Task 4.
- Short `xxxx-xxxx` id, unique-prefix + dash/case-insensitive resolution → Task 1, tested.
- `.ayder/sessions/` storage, gitignored → Task 1 (`sessions_dir`), Global Constraints.
- Verbatim messages incl. `tool_calls`/system → Task 1 roundtrip test.
- Restore model/agent_mode/safe_mode/permissions → Task 1 (save/load), Task 5 (passed to run_tui), Task 3 (used by app).
- `--resume` mutually exclusive with session-shaping flags; `-c/--config`, `--verbose`, `--logging-level` allowed → Task 5 (guard lists only session-shaping flags), tested.
- Replay prior user/assistant turns; tool messages kept in memory → `messages_to_replay_items` (Task 2) + `_replay_history`/`on_mount` (Task 3), tested.
- Stable id on re-quit (preserve `created_at`) → Task 1 test + `persist_and_announce(session_id=...)` (Task 4 reuse test).
- Friendly errors + non-zero exit on bad/ambiguous/corrupt id → Task 1 (`SessionNotFound`/`SessionAmbiguous`/`SessionError`), Task 5 bad-id test.
- Crash-safe save (`try/finally`) → Task 4.
- Known limitation (model best-effort vs config) → documented in spec; no task needed.

**Placeholder scan:** No TBD/TODO; every code step shows complete code; every test step shows full assertions.

**Type consistency:** `SessionData` fields and all function signatures are identical across the Interfaces blocks and the implementations. `messages_to_replay_items` returns `list[tuple[str, str]]` and is consumed accordingly in `_replay_history`. `persist_and_announce` kwargs match between Task 4's call site and Task 2's definition (`session_id`, `model`, `agent_mode`, `safe_mode`, `permissions`, `out`). `run_tui` params match Task 5's call site.

## Execution Handoff

Plan complete. See the Execution options below.
