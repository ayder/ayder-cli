# Context Tool Consolidation — Design

**Date:** 2026-05-20
**Status:** Draft (awaiting user review)
**Author:** brainstorming session

## Goal

Reduce the memory-related tool surface from four tools to one polymorphic `context` tool that handles save / load / list / stats. Drop the JSONL fact-log entirely. Fix the silent-overwrite data-loss bug. Cut tool-definition tokens carried in every LLM call.

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
context(action, name=None, content=None, overwrite=False)
```

### JSON Schema (token-budgeted)

The tool description and parameter descriptions are the per-call cost. Both are kept as short as accuracy allows.

```json
{
  "name": "context",
  "description": "Session context. action=save snapshots state by name; load restores by name; list enumerates slots; stats reports token + cache usage.",
  "parameters": {
    "type": "object",
    "properties": {
      "action": {
        "type": "string",
        "enum": ["save", "load", "list", "stats"],
        "description": "Operation to perform."
      },
      "name": {
        "type": "string",
        "description": "Slot name. Required for save and load."
      },
      "content": {
        "type": "string",
        "description": "Content to snapshot. Required for save."
      },
      "overwrite": {
        "type": "boolean",
        "description": "Save: skip auto-versioning of existing slot."
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

The timestamp in versioned filenames uses dashes instead of colons (`2026-05-20T14-32-15`) for filesystem portability. The `saved_at` field inside the JSON body uses standard ISO 8601 with colons (`2026-05-20T14:35:02`) — these are deliberately different.

`list` returns only "current" entries — files whose name matches `<name>.json` with no additional `.` segments before the extension. Versioned files (which contain an extra `.<timestamp>` segment) are recovery-only and not surfaced through the tool. Recovery is a manual operation (file restore).

## Implementation Sketch

### Dependency injection

`stats` needs access to the active `ContextManagerProtocol` and `CacheMonitor`. The registry already injects `project_ctx` and `process_manager` based on function signature inspection. Extend the same mechanism with two more injectable types:

```python
def context(
    project_ctx: ProjectContext,
    context_manager: ContextManagerProtocol,
    cache_monitor: CacheMonitor | None,
    action: str,
    name: str | None = None,
    content: str | None = None,
    overwrite: bool = False,
) -> str:
    ...
```

Registry change: in `create_default_registry(...)`, accept and inject `context_manager` and `cache_monitor` the same way it does `process_manager`.

### File layout

New module: `src/ayder_cli/tools/builtins/context.py`
- `context(...)` — dispatcher on `action`
- `_save(project_ctx, name, content, overwrite)`
- `_load(project_ctx, name)`
- `_list(project_ctx)`
- `_stats(project_ctx, context_manager, cache_monitor)`
- Helper: `_get_context_dir(project_ctx)` returns `.ayder/context/`

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

### Slash command renames

In `tui/commands.py`:
- `/save-memory` → `/save-context` (call `context(action="save", ...)`)
- `/load-memory` → `/load-context` (call `context(action="load", ...)`)
- Add `/list-contexts` (call `context(action="list")`)
- Add `/context-stats` (call `context(action="stats")`)

Clean break — no aliases for the old names.

## Token Math

Approximate token cost of the tool-definition surface carried in every LLM call.

| Surface | Tokens |
|---|---|
| Current: `save_memory` + `load_memory` + `save_context_memory` + `load_context_memory` | ~260 |
| New: `context` | ~100 |
| **Saved per call** | **~160** |

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

## Migration

Single PR. No data migration — existing `.ayder/memory/` files are orphaned but not deleted (user can clean manually). The `/save-memory` and `/load-memory` slash commands break; that is an accepted breaking change since the project is pre-1.0.

## Out of Scope

- Refactoring `notes`, `tasks`, and the new `context` to share a common `project_storage` utility. The duplicate `_title_to_slug` and `_get_*_dir` helpers across those three modules are noted for a follow-up but not addressed here.
- Consolidating the four process-management tools into one polymorphic tool. Same pattern would apply but is not part of this design.
- Migrating data from the old JSONL log into the new context store. The log holds facts (different shape, different lifecycle) and `create_note` is the better landing place if any of that data needs to be preserved manually.

## Open Items for Implementation Plan

- Confirm where `CacheMonitor` is instantiated and how it reaches the registry's DI scope.
- Confirm where `ContextManagerProtocol` instance lives at runtime (per-session in the chat loop?) and how the registry obtains a reference.
- Decide whether `stats` should also include the active provider/model name (useful context, ~1 extra line in payload).
