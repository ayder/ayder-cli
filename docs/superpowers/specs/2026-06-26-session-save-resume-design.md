# Session Auto-Save & `--resume` — Design

- **Date:** 2026-06-26
- **Branch:** feat/agent-harness-workflow
- **Status:** Approved (pending spec review)

## Summary

Persist the chat conversation when the user quits the ayder TUI, and let them
continue it later with `ayder --resume <id>`. On exit, the full in-memory
message list (including the system prompt) plus a small block of
session-shaping settings are written to `.ayder/sessions/<id>.json`, and an exit
line tells the user how to resume:

```
Session saved. Resume with:
  ayder --resume a1b2-c3d4
```

`ayder --resume a1b2-c3d4` loads that file, restores the conversation and its
original settings exactly (no other flags needed), replays the prior turns in
the chat view, and continues. Quitting again updates the same file/ID.

## Goals

- Auto-save the conversation on any TUI exit path (Ctrl+Q, quit action, `/exit`).
- Resume a saved conversation by short ID with **no other flags required** — the
  session is self-contained.
- Faithfully restore the original session: system prompt (covers `--agent` /
  `--system-prompt`), permissions, agent mode, and safe mode.
- Replay prior user/assistant turns visibly in the chat view.
- Keep a stable ID across re-quits of the same conversation.

## Non-Goals (YAGNI)

- No config toggles for enabling/disabling auto-save.
- No retention/pruning of old session files (re-quit reuses the same file, so a
  single ongoing conversation does not accumulate files).
- No `--resume` (latest) shorthand and no `--list-sessions` command.
- No precise cross-machine model forcing (see Known Limitations).

## User-Facing Behavior

### Save on exit

When the TUI exits and the conversation contains at least one `user` message,
the conversation is saved to `.ayder/sessions/<id>.json` and the resume hint is
printed to stdout. Empty conversations (launched and immediately quit, no user
turn) are **not** saved and print nothing.

Saving runs in a `try/finally` around `app.run()` so a crash still attempts to
persist what was in memory.

### Resume

`ayder --resume <id>` loads the session and launches the TUI with the prior
conversation restored. `<id>` matches by exact ID or by **unique prefix**
(`a1b2` works if it is unambiguous).

`--resume` is mutually exclusive with session-shaping options. If combined with
any of `--agent`, `--system-prompt`, `-w`, `-x`, `--http`, `--file`/`-f`,
`--stdin`, a positional command string, `--implement`, `--implement-all`,
`--tasks`, `--temporal-task-queue`, or `--temporal-prompt`, it errors:

```
Error: --resume takes no other options — it restores the original session's
settings. Usage: ayder --resume <id>
```

Allowed alongside `--resume` (environment/diagnostic, not session settings):
`-c`/`--config`, `--verbose`, `--logging-level`. (`-r` defaults to true and is
the always-on read permission; it is ignored, not treated as a conflict.)

On a failed load (no match / ambiguous prefix / corrupt file), print a friendly
error listing available IDs and exit non-zero.

## Session ID

Short grouped form `xxxx-xxxx` — 8 hex chars from `uuid4().hex`, split with a
dash (e.g. `a1b2-c3d4`). Generation re-rolls on the rare collision with an
existing file. The filename is `<id>.json`. Resolution accepts the exact ID or
any unique prefix of it (dashes optional, case-insensitive).

## Session File Format

`.ayder/sessions/<id>.json`:

```jsonc
{
  "schema_version": 1,
  "session_id": "a1b2-c3d4",
  "created_at": "2026-06-26T12:00:00.123456",
  "updated_at": "2026-06-26T12:34:56.654321",
  "model": "qwen3-coder:latest",
  "agent_mode": false,
  "safe_mode": false,
  "permissions": ["r", "w"],
  "cwd": "/Users/me/project",
  "message_count": 12,
  "messages": [
    { "role": "system", "content": "<full system prompt, verbatim>" },
    { "role": "user", "content": "fix the bug in X" },
    { "role": "assistant", "content": "...", "tool_calls": [ ... ] },
    { "role": "tool", "content": "...", "tool_call_id": "..." }
  ]
}
```

The `messages` array is the in-memory list saved **verbatim** — including
`messages[0]` (the system prompt) and all `tool_calls` / `tool` results so the
provider's call/result pairing remains valid on resume. The metadata block makes
resume self-contained without any flags.

On re-save with an existing `session_id`, `created_at` is preserved and
`updated_at` is bumped.

## Architecture

### New module: `src/ayder_cli/core/session.py`

Pure and TUI-independent — all the persistence logic, unit-testable without
running Textual. Path-resolving functions default `root` to `Path.cwd()` (the
same project-root convention as the notes/context tools).

```python
class SessionError(Exception): ...
class SessionNotFound(SessionError): ...
class SessionAmbiguous(SessionError): ...

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

def sessions_dir(root: Path | None = None) -> Path
    # <root>/.ayder/sessions

def new_session_id(root: Path | None = None) -> str
    # collision-checked "xxxx-xxxx"

def save_session(
    messages: list[dict],
    *,
    root: Path | None = None,
    session_id: str | None = None,   # reuse to update in place; else new id
    model: str | None = None,
    agent_mode: bool = False,
    safe_mode: bool = False,
    permissions: set[str] | None = None,
) -> str                              # returns the session id written

def resolve_session_id(token: str, root: Path | None = None) -> str
    # exact or unique-prefix; raises SessionNotFound / SessionAmbiguous

def load_session(token: str, root: Path | None = None) -> SessionData

def list_sessions(root: Path | None = None) -> list[str]
    # session ids present, for friendly error messages
```

`save_session` creates `.ayder/sessions/` if missing. Timestamps are produced
inside `save_session` (the only impure surface).

### Save-on-exit: `src/ayder_cli/tui/__init__.py`

`run_tui` gains two parameters:

```python
def run_tui(
    model="default", safe_mode=False, permissions=None, agent_mode=False,
    system_prompt_override=None,
    initial_messages: list[dict] | None = None,   # NEW
    resume_session_id: str | None = None,         # NEW
) -> None
```

These pass straight through to `AyderApp`. After `app.run(...)` returns
(wrapped in `try/finally`), it calls a testable helper:

```python
def persist_and_announce(
    messages, *, root, session_id, model, agent_mode, safe_mode,
    permissions, out=print,
) -> str | None
    # returns None (and prints nothing) if there is no user message;
    # otherwise save_session(...) and print the resume hint via out().
```

`run_tui` invokes it with values read off the app instance
(`app.messages`, `app.resume_session_id`, `app.model`, `app._resuming` flags,
`app.permissions`, `app.safe_mode`, plus agent_mode).

### Resume entry point: `src/ayder_cli/cli.py`

1. Add `--resume` to `_add_common_args`:

```python
parser.add_argument(
    "--resume", type=str, metavar="ID", default=None,
    help="Resume a saved session by id (or unique prefix) from "
         ".ayder/sessions/. Takes no other session options.",
)
```

2. In `main()`, after permissions/config/logging setup and before the
   file/stdin block (~line 397), handle resume:
   - Validate mutual exclusivity (error + exit 1 if a session-shaping flag is
     also set).
   - `load_session(args.resume)`; on `SessionError`, print the message (with
     available IDs from `list_sessions()`) and exit 1.
   - Call `run_tui(...)` passing restored `permissions`, `agent_mode`,
     `safe_mode`, `model`, `initial_messages=sess.messages`,
     `resume_session_id=sess.session_id`; then `return`.

### Resume restore: `src/ayder_cli/tui/app.py`

`AyderApp.__init__` gains `initial_messages` and `resume_session_id`:

```python
self.resume_session_id = resume_session_id
self._resuming = bool(initial_messages and initial_messages[0].get("role") == "system")
self.messages = list(initial_messages) if initial_messages else []
if not self._resuming:
    self._init_system_prompt()
```

The agent capability-prompt append (currently `app.py:328-331`) is guarded with
`if not self._resuming` so a restored system prompt (which already contains the
capability text) is not double-injected.

`model`, `agent_mode`, `safe_mode`, and `permissions` continue to flow through
the existing `__init__` params; on resume the CLI supplies the restored values.

### Replay: `src/ayder_cli/tui/app.py`

A pure mapper (unit-tested):

```python
def messages_to_replay_items(messages) -> list[tuple[str, str]]
    # [("user", text), ("assistant", text), ...]
    # skips the system message and tool messages; skips assistant entries whose
    # content is empty (tool-call-only turns).
```

In `on_mount`, when `self._resuming`, render a one-line "resumed session" banner
(noting the saved model if it differs from the active one) followed by the
replay items into `ChatView`. The full message list — including tool
calls/results — remains in `self.messages` so the model has complete context;
only the visible bubbles are user/assistant turns.

## Edge Cases

- **Empty conversation on quit:** no user message → no file written, nothing
  printed.
- **Resume then quit:** `resume_session_id` is set, so `save_session` updates the
  same file (stable ID; `created_at` preserved).
- **ID not found:** `SessionNotFound` → friendly error listing available IDs,
  exit 1.
- **Ambiguous prefix:** `SessionAmbiguous` → error listing the matches, exit 1.
- **Corrupt/old JSON:** `SessionError` → error, exit 1 (no silent crash).
- **Crash mid-session:** `try/finally` in `run_tui` still attempts the save.
- **`/model` switch inside a resumed session:** `update_system_prompt_model()`
  regenerates the system prompt, overwriting the restored one. Documented
  limitation, acceptable.

## Known Limitations

- **Model restore is best-effort.** Existing logic (`app.py:241-245`) lets a
  non-`"default"` config model win over the passed-in model. Resuming on a
  machine whose config pins a different model uses the config model. The saved
  model is recorded and shown in the replay banner; forcing it would require
  provider plumbing and is out of scope.

## Testing Plan

TDD throughout. New `tests/core/test_session.py`:

- `new_session_id` returns `xxxx-xxxx` shape and is unique across calls.
- `save_session` → `load_session` round-trips messages + metadata.
- System message at index 0 and `tool_calls`/`tool` messages survive verbatim.
- `resolve_session_id`: exact match, unique prefix, ambiguous (raises),
  not-found (raises), dash-insensitive / case-insensitive.
- Re-save with same `session_id` preserves `created_at`, bumps `updated_at`.
- `permissions` round-trip as a set.

`persist_and_announce` (in `tests/tui/`): skips when no user message (returns
None, no output); saves and prints the hint when a user message exists; reuses
`resume_session_id`.

`messages_to_replay_items`: maps user/assistant turns, skips system and tool
messages, skips empty assistant content.

`tests/test_cli.py`: `--resume` parses; `--resume` + a session-shaping flag
exits non-zero with the guidance message; `--resume <bad-id>` exits non-zero.

## File-by-File Changes

| File | Change |
|------|--------|
| `src/ayder_cli/core/session.py` | **NEW** — persistence module (API above). |
| `src/ayder_cli/cli.py` | Add `--resume` arg; mutual-exclusivity guard + resume handler in `main()`. |
| `src/ayder_cli/tui/__init__.py` | `run_tui` gains `initial_messages`/`resume_session_id`; `persist_and_announce` helper + `try/finally` save-on-exit. |
| `src/ayder_cli/tui/app.py` | `__init__` `initial_messages`/`resume_session_id`; skip system-prompt rebuild + capability append on resume; `messages_to_replay_items`; replay in `on_mount`. |
| `tests/core/test_session.py` | **NEW** — session module tests. |
| `tests/tui/` | `persist_and_announce` + `messages_to_replay_items` tests. |
| `tests/test_cli.py` | `--resume` parsing + mutual-exclusivity + bad-id tests. |

## Future Extensions (not now)

- `[session]` config section: `auto_save` toggle, retention/pruning.
- `--resume` with no argument = resume most recent session.
- `--list-sessions` to browse saved sessions.
