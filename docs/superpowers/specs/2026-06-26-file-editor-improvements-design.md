# file_editor Improvements — Design Spec

**Date:** 2026-06-26
**Branch:** `feat/agent-harness-workflow`
**Status:** Approved (Section C dropped per review)

## Background

The orchestrator LLM reported friction with the `file_editor` tool
(`src/ayder_cli/tools/builtins/filesystem.py:167`). Investigation confirmed:

- `replace` uses `str.replace()` (`filesystem.py:200`) with **no uniqueness
  check** — a non-unique `old_string` silently rewrites *every* occurrence.
  This is codified today by `test_multiple_occurrences_replacement`
  (`tests/tools/test_impl.py:294`). This silent over-broad edit is the
  highest-value problem.
- No regex support (literal `str.replace` only).
- No dry-run / preview; every operation writes immediately.
- The `insert` schema description ("add content at line") is ambiguous about
  before/after, though the behavior is well-defined and tested (insert-before).

The registry dispatches tools via `tool_func(**call_args)` with signature
inspection (`src/ayder_cli/tools/execution.py:96-111`), so **new function
parameters with defaults flow through automatically** and are backward
compatible at the call layer. `prompts.py` contains no per-tool `replace`
guidance, so the tool's schema `description` is the documentation surface.

## Goals

1. Make `replace` safe by default: error on a non-unique match unless the
   caller explicitly opts into replacing all matches.
2. Add an optional regex mode to `replace`.
3. Add a dry-run (preview, no write) mode to every operation.
4. Clarify the `insert` description (docs only; behavior unchanged).

## Non-Goals

- Enriched not-found errors / near-miss suggestions (considered, dropped).
  A not-found `old_string` keeps the current plain error and behavior.
- Changing `insert` / `delete` / `write` semantics.
- Any change to `prompts.py` or the agentic system prompt.

## New Parameters

All optional, added to `file_editor` (function signature **and** the JSON
schema in `filesystem_definitions.py`).

| Param | Type | Default | Applies to | Meaning |
|-------|------|---------|-----------|---------|
| `replace_all` | bool | `False` | `replace` | Allow more than one match. Without it, a non-unique `old_string` is an error. |
| `regex` | bool | `False` | `replace` | Treat `old_string` as a Python regex pattern; `new_string` supports backreferences (`\1`, `\g<name>`). |
| `dry_run` | bool | `False` | all operations | Compute the change, write nothing, return a unified diff. |

## Behavior

### replace (the safety fix)

Order of operations:

1. Validate `old_string` and `new_string` are present (existing check).
2. File must exist (existing check).
3. Read file content.
4. Count matches:
   - literal: `file_content.count(old_string)`
   - regex: `sum(1 for _ in pattern.finditer(file_content))`
5. **0 matches** → existing plain error, unchanged:
   `Error: 'old_string' not found in {rel_path}. No changes made.`
6. **>1 match and not `replace_all`** → error:
   `Error: 'old_string' is not unique (found N matches) in {rel_path}. Pass replace_all=true to replace all occurrences, or add surrounding context to make it unique. No changes made.`
7. Otherwise compute `new_content`:
   - literal: `file_content.replace(old_string, new_string)` (replaces the
     single match when unique; all matches when `replace_all`)
   - regex: `pattern.sub(new_string, file_content, count=0 if replace_all else 1)`
8. Finalize (write or dry-run, see below). Success message reports the count:
   `Successfully replaced N occurrence(s) in {rel_path}`

Invalid regex pattern → `ToolError("Invalid regex pattern: {error}", "validation")`
(raised when compiling, before any match work).

### regex details

- `regex=True` compiles `old_string` with `re.compile(old_string)`.
- Match counting and substitution both use the compiled pattern.
- `new_string` is passed to `re.sub` as the replacement template, so
  backreferences (`\1`, `\g<name>`) work.
- The same uniqueness guard applies: more than one match without `replace_all`
  is an error.

### dry_run (all operations)

Each operation computes its resulting `new_content` exactly as the real path
would (after all validation/guards pass), then a shared finalizer decides:

- `dry_run=False` → write `new_content`, return the operation's normal success
  message.
- `dry_run=True` → write nothing, return a unified diff:

```
[DRY RUN] No changes written to {rel_path}.
--- a/{rel_path}
+++ b/{rel_path}
@@ ... @@
-    old
+    new
```

Diff is produced with `difflib.unified_diff` over `splitlines(keepends=True)`.
When the operation would not change the file, return:
`[DRY RUN] No changes would be made to {rel_path}.`

For `write`, the "before" side of the diff is the file's current content if it
exists, else empty. For `delete`/`insert`/`replace`, dry-run runs only after the
operation's existence and validation guards pass (so a dry-run delete of an
out-of-range line still returns the normal validation error).

### insert (docs only)

Behavior unchanged: content becomes the new line N; the existing line N and
below shift down; `line_number` past EOF appends; `line_number < 1` is rejected;
content without a trailing newline gets one. Only the schema description is
clarified.

## Code Structure

`file_editor` in `src/ayder_cli/tools/builtins/filesystem.py`:

- Add params `replace_all: bool = False`, `regex: bool = False`,
  `dry_run: bool = False` to the signature.
- Introduce a module-level helper:

  ```python
  def _finalize(abs_path, rel_path, old_content, new_content, success_msg, dry_run):
      """Write new_content (returning success_msg) or, when dry_run, return a
      unified diff and write nothing."""
  ```

- Each operation block computes `new_content` (and, where relevant,
  `old_content` for the diff) and delegates to `_finalize`.
- Add `import re` and `import difflib` at module top.

## Schema / Definition Changes

`src/ayder_cli/tools/builtins/filesystem_definitions.py`, `file_editor`
definition:

- Add `replace_all`, `regex` (booleans, replace-only) and `dry_run` (boolean,
  all ops) to `properties`.
- Update the top-level `description` to state: replace is unique-by-default
  (use `replace_all` for multiple), regex mode is available, and `dry_run`
  previews any operation as a diff.
- Update the `operation` enum description for `insert` to the insert-before
  wording above.

## Testing

`tests/tools/test_impl.py`:

- **Rewrite** `test_multiple_occurrences_replacement` → now asserts a
  `ToolError` (not-unique) and that the file is unchanged.
- **Add:**
  - replace unique match → replaces exactly one, success message reports count.
  - replace non-unique without `replace_all` → error, file unchanged.
  - replace non-unique with `replace_all=True` → replaces all, count in message.
  - replace `regex=True` basic pattern substitution.
  - replace `regex=True` with a backreference in `new_string`.
  - replace `regex=True` with an invalid pattern → validation error.
  - `dry_run=True` for replace → returns diff, file unchanged.
  - `dry_run=True` for write, insert, delete → returns diff, file unchanged.
  - not-found `old_string` → existing plain error (regression guard).
- **Keep green:** all existing insert / delete / write / path-security tests.

Run the full suite plus ruff + mypy as the final gate.

## Backward Compatibility

- Adding optional parameters with defaults is non-breaking at the dispatch
  layer (`tool_func(**call_args)`).
- The **one intentional breaking change**: a bare `replace` on a non-unique
  `old_string` now errors instead of replacing all occurrences. This is the
  point of the fix and is reflected in the rewritten test.
