# Context Tool Consolidation — Design

**Date:** 2026-05-20
**Status:** Draft (awaiting user review)
**Author:** brainstorming session

## Goal

Reduce the memory-related tool surface from four tools to one polymorphic `context` tool that handles save / load / list / stats / clear. Drop the JSONL fact-log entirely. Fix the silent-overwrite data-loss bug. Fix the `/clear` coordination bug (context-manager counters not reset). Cut tool-definition tokens carried in every LLM call.

## Motivation

The current memory cluster has four tools doing two overlapping jobs:

| Tool pair | Storage | Purpose |
|---|---|---|
| `save_memory` / `load_memory` | JSONL append-log | Accumulate facts with category/tag filtering |
| `save_context_memory` / `load_context_memory` | One JSON file per name | Snapshot session state for restore |

`create_note` already covers "agent takes markdown notes," so the JSONL fact-log (`save_memory`) is the redundant third pattern. The real use case is session-state snapshotting — saving an LLM-generated summary at session end and restoring it next session — which only `save_context_memory` actually serves, but it has three real defects:

1. Silent overwrite — calling `save_context_memory("session", ...)` twice destroys the first save with no warning.
2. No discovery — the LLM cannot ask "which sessions exist?" without an extra tool.
3. Storage collides with `save_memory` in `.ayder/memory/`.

`file_editor` already uses a polymorphic enum-dispatch pattern (`operation: write|replace|insert|delete`) reliably in this stack, so the same shape is appropriate here.

## Tool Design

### Signature

```python
context(action, name=None, content=None, overwrite=False, keep_last_n=0)
```

### JSON Schema (token-budgeted)

The tool description and parameter descriptions are the per-call cost. Both are kept as short as accuracy allows.

```json
{
  "name": "context",
  "description": "Session context. action=save snapshots state by name; load restores by name; list enumerates slots; stats reports token + cache usage; clear auto-saves the caller-provided summary (content) then deferred-wipes the conversation to free the budget.",
  "parameters": {
    "type": "object",
    "properties": {
      "action": {
        "type": "string",
        "enum": ["save", "load", "list", "stats", "clear"],
        "description": "Operation to perform."
      },
      "name": {
        "type": "string",
        "description": "Slot name. Required for save and load."
      },
      "content": {
        "type": "string",
        "description": "Content. Required for save (the snapshot text) and clear (the LLM's summary of work done)."
      },
      "overwrite": {
        "type": "boolean",
        "description": "Save: skip auto-versioning of existing slot."
      },
      "keep_last_n": {
        "type": "integer",
        "description": "Clear: number of most-recent message exchanges to retain verbatim (default 0)."
      }
    },
    "required": ["action"]
  }
}
```

Conditional-required (`content` only when `action=save`) is intentionally not encoded in `oneOf`/`if`-`then`. Tool-calling frameworks rarely surface those constraints to the model and they bloat the schema. The description does the work.

### Per-action behavior

| `action` | Required params | Returns |
|---|---|---|
| `save` | `name`, `content` | `ToolSuccess` confirming write path; versioned predecessor noted if applicable |
| `load` | `name` | `ToolSuccess(content_string)`; on missing name, `ToolError` whose body lists available names |
| `list` | none | `ToolSuccess(JSON array)` of `{name, saved_at, size_bytes}` |
| `stats` | none | `ToolSuccess(JSON object)` with token + cache fields (see below) |
| `clear` | `content` | `ToolSuccess(JSON object)` summarizing the deferred compaction (see below) |

### `stats` payload

Reads from existing instrumentation — no new collection logic:

```json
{
  "total_tokens": 12345,
  "available_tokens": 87655,
  "utilization_percent": 12.3,
  "message_count": 42,
  "compaction_count": 1,
  "messages_compacted": 8,
  "cache_state": "hot",
  "cache_hit_ratio": 0.87,
  "saved_contexts_count": 3
}
```

Token fields come from `ContextManagerProtocol.get_stats()` (returns `ContextStats`). Cache fields come from `CacheMonitor.last_status` (may be `None` for non-Ollama providers — return `cache_state: "n/a"` in that case). `saved_contexts_count` is a directory scan.

### `clear` payload and behavior

`clear` is the LLM's "I'm done with this chunk, free the budget" signal. **The LLM provides its own summary** as the `content` parameter — the tool does not invoke a secondary summarization round-trip. This caller-supplied design avoids tool-cycle re-entrancy hazards (an LLM-driven summarization step inside a tool call would require chat-loop re-entrancy that the current architecture does not support cleanly).

Behavior (synchronous file write + deferred message mutation):

1. Validate `content` is non-empty (the LLM-authored summary).
2. Auto-save the summary into `.ayder/context/<name>.json`. If `name` is not provided, generate `auto-compact-<microsecond-timestamp>`. Same versioning rules as `save`.
3. Set `app._pending_compact = {"summary_name": <name>, "summary_content": <content>, "keep_last_n": <n>}` on the running app handle.
4. Return projected counts to the LLM immediately.

The actual message wipe + re-seed happens **after the tool call cycle completes**, when the chat_loop's `pre_iteration_hook` fires at the start of the next iteration. This avoids mutating `app.messages` mid-tool-call (which would orphan a tool_result from its assistant pair).

Return shape (immediate, before the deferred wipe runs):

```json
{
  "messages_before": 42,
  "kept_last_n": 0,
  "saved_as": "auto-compact-2026-05-20T15-22-08-123456",
  "status": "pending — will be applied at next chat-loop iteration"
}
```

Failure modes:
- Missing `content` → `ToolError("content (summary text) is required for clear", "validation")`. No file write, no flag set.
- Missing app handle (e.g., headless CLI) → `ToolError("clear requires a running TUI session (no app handle)", "execution")`.
- `_save` fails → its error propagates; flag is not set.

### `/clear` coordination fix (bundled)

### `/clear` coordination fix (bundled)

Today `do_clear` in `tui/commands.py:862` clears `app.messages` and the chat view but does **not** call `ContextManagerProtocol.clear()` (defined at `default_context_manager.py:437`). As a result, the active context manager's `_compressed_count`, `_message_meta`, and cache state persist across an explicit user `/clear`. This is a latent bug.

Fixed in the same PR: `do_clear` calls `app.context_manager.clear()` after clearing `app.messages`. Independent of the new `context(action="clear")` tool — this fixes the existing `/clear` slash command too.

`clear()` is invoked with `hasattr(cm, "clear")` (duck-typed) rather than as a `ContextManagerProtocol` method, because the protocol does not declare it. Only `DefaultContextManager` currently implements it. Promoting `clear()` to the protocol is a separate refactor that would require updates to every implementer — out of scope here.

## Storage

```
.ayder/context/
├── session-2026-05-20.json                          # current
├── session-2026-05-20.2026-05-20T14-32-15.json      # auto-versioned predecessor
└── project-state.json
```

Each JSON file contains:

```json
{
  "name": "session-2026-05-20",
  "content": "<the snapshot string>",
  "saved_at": "2026-05-20T14:35:02"
}
```

`save` with `overwrite=false` (default) renames any existing `<name>.json` to `<name>.<ISO-timestamp>.json` before writing the new file. `overwrite=true` removes the predecessor without versioning.

The timestamp in versioned filenames uses dashes instead of colons (`2026-05-20T14-32-15-987654`) for filesystem portability **and includes microseconds** to prevent collision when the same slot is overwritten more than once per second. The `saved_at` field inside the JSON body uses standard ISO 8601 with colons (`2026-05-20T14:35:02.987654`) — these are deliberately different.

**Slot name validation.** All slot names are validated against `^[A-Za-z0-9._-]+$` and rejected if they equal `.`, `..`, or start with `.`. This prevents path traversal (`name="../escape"`) and accidental nested paths. Validation is applied at the entry of both `save` and `load`.

`list` returns only "current" entries — files whose name matches `<name>.json` with no additional `.` segments before the extension. Versioned files (which contain an extra `.<timestamp>` segment) are recovery-only and not surfaced through the tool. Recovery is a manual operation (file restore).

## Implementation Sketch

### Dependency injection

`stats` and `clear` need access to the active `ContextManagerProtocol` and (for `clear`) the running `AyderApp` instance. The registry already injects `project_ctx` and `process_manager` based on function signature inspection. Extend the same mechanism with two more injectable types:

```python
def context(
    project_ctx: ProjectContext,
    context_manager: ContextManagerProtocol,
    app: Any,  # AyderApp instance; needed by clear. Optional — None in headless mode.
    action: str,
    name: str | None = None,
    content: str | None = None,
    overwrite: bool = False,
    keep_last_n: int = 0,
) -> str:
    ...
```

Registry change: in `create_default_registry(...)`, accept and inject `context_manager` and an `app` reference the same way it does `process_manager`. If the `app` handle is unavailable (e.g., headless CLI execution), `context(action="clear")` returns `ToolError("clear requires a running TUI session", "execution")` and the other actions still work.

**`CacheMonitor` is not a separate injectable.** Only `OllamaContextManager` owns one, and it's attached as an instance attribute (`context_manager._cache_monitor`). `_stats` accesses it via `getattr(context_manager, "_cache_monitor", None)` and gracefully reports `cache_state="n/a"` when absent. Adding a separate DI parameter would duplicate the lookup and complicate registry construction for the non-Ollama case.

### File layout

New module: `src/ayder_cli/tools/builtins/context.py`
- `context(...)` — dispatcher on `action`
- `_save(project_ctx, name, content, overwrite)`
- `_load(project_ctx, name)`
- `_list(project_ctx)`
- `_stats(project_ctx, context_manager, cache_monitor)`
- `_clear(app, context_manager, keep_last_n)` — wraps the existing `/compact` flow; returns the JSON summary described above
- Helper: `_get_context_dir(project_ctx)` returns `.ayder/context/`
- Helper: `_auto_compact_name()` returns `f"auto-compact-{iso_timestamp_dashed()}"`

New definitions module: `src/ayder_cli/tools/builtins/context_definitions.py`

### Removed files / code

- `src/ayder_cli/tools/builtins/memory.py` — delete
- `src/ayder_cli/tools/builtins/memory_definitions.py` — delete
- `tests/test_memory.py` — delete
- `tui/commands.py` — remove `handle_save_memory`, `handle_load_memory`; remove `/save-memory`, `/load-memory` from the command map
- `prompts.py` — remove references at lines 232 and 271 (memory tool prompt hints)
- `tests/tools/test_definition_discovery.py` line 276-277 — update assertions
- `tests/tools/test_schemas.py` line 56 — update tool list
- The JSONL file `.ayder/memory/memories.jsonl` is no longer written; existing project files are left in place (no automatic deletion — user can `rm -rf .ayder/memory/` if desired)

### Slash command renames and fixes

In `tui/commands.py`:
- `/save-memory` → `/save-context` (call `context(action="save", ...)`)
- `/load-memory` → `/load-context` (call `context(action="load", ...)`)
- Add `/list-contexts` (call `context(action="list")`)
- Add `/context-stats` (call `context(action="stats")`)
- **Fix `/clear`**: `do_clear` (line 862) gains a call to `app.context_manager.clear()` after the message wipe. The existing `/clear` keeps its current behavior (purely user-driven clear), now correctly coordinated with the context manager. No new slash command for `context(action="clear")` — that path is LLM-initiated; `/compact` already covers the user-initiated equivalent.

Clean break — no aliases for the old memory names.

## Token Math

Approximate token cost of the tool-definition surface carried in every LLM call.

| Surface | Tokens |
|---|---|
| Current: `save_memory` + `load_memory` + `save_context_memory` + `load_context_memory` | ~260 |
| New: `context` (with `clear` action and `keep_last_n` param) | ~125 |
| **Saved per call** | **~135** |

Counts are estimates from current schema text; exact tokenization depends on the provider's tokenizer. The win compounds with every tool call in a session.

## Test Plan

New file: `tests/test_context.py`
- `test_save_creates_file_in_context_dir`
- `test_save_versions_existing_on_default_overwrite`
- `test_save_with_overwrite_true_skips_versioning`
- `test_load_returns_content_string`
- `test_load_missing_name_lists_available_in_error`
- `test_list_returns_current_slots_only_not_versioned`
- `test_list_empty_returns_empty_array`
- `test_stats_returns_token_and_cache_fields`
- `test_stats_cache_na_when_monitor_absent`
- `test_invalid_action_returns_validation_error`
- `test_save_missing_name_returns_validation_error`
- `test_save_missing_content_returns_validation_error`
- `test_clear_creates_auto_compact_slot`
- `test_clear_preserves_keep_last_n_exchanges`
- `test_clear_resets_context_manager_counters`
- `test_clear_returns_error_without_app_handle`
- `test_clear_does_not_mutate_state_on_summarizer_failure`

Additional test for the bundled fix:
- New file or addition to existing `tests/tui/test_commands.py`: `test_do_clear_resets_context_manager` — verifies `/clear` now calls `ContextManagerProtocol.clear()`.

## Migration

Single PR. No data migration — existing `.ayder/memory/` files are orphaned but not deleted (user can clean manually). The `/save-memory` and `/load-memory` slash commands break; that is an accepted breaking change since the project is pre-1.0.

## Out of Scope

- Refactoring `notes`, `tasks`, and the new `context` to share a common `project_storage` utility. The duplicate `_title_to_slug` and `_get_*_dir` helpers across those three modules are noted for a follow-up but not addressed here.
- Consolidating the four process-management tools into one polymorphic tool. Same pattern would apply but is not part of this design.
- Migrating data from the old JSONL log into the new context store. The log holds facts (different shape, different lifecycle) and `create_note` is the better landing place if any of that data needs to be preserved manually.

## Open Items for Implementation Plan

- Decide whether `stats` should also include the active provider/model name (useful context, ~1 extra line in payload).
- Decide whether `auto-compact-*` slots should be garbage-collected after N entries (otherwise they accumulate unboundedly across long sessions).
- Decide whether to promote `clear()` to `ContextManagerProtocol`. Currently only `DefaultContextManager` implements it; the design uses `hasattr` duck-typing. Promotion would force every context manager (including `OllamaContextManager`) to implement reset semantics consistently.
- Decide whether agent-runtime contexts should be isolated from the parent's `.ayder/context/`. Current design shares the namespace; agents can use slot-name prefixes for logical isolation.

**Resolved during planning:**
- `CacheMonitor` lives on `OllamaContextManager._cache_monitor` (instance attribute); accessed via `getattr(context_manager, "_cache_monitor", None)` — no separate DI injection.
- `ContextManagerProtocol` instance is created in `runtime_factory.create_runtime()` and held on `RuntimeComponents.context_manager`; passed to `create_default_registry(..., context_manager=context_mgr)` for tool DI.
- `clear` action does **not** trigger in-tool LLM summarization. The LLM provides its own summary as the `content` parameter and the tool defers message mutation via `app._pending_compact`, consumed at the next chat-loop iteration boundary by a composed `pre_iteration_hook`.
