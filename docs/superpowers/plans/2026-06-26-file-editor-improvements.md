# file_editor Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `file_editor`'s `replace` safe (unique-by-default), add optional regex and an all-operation dry-run preview, and clarify the `insert` docs.

**Architecture:** Extend the existing `file_editor` function in `src/ayder_cli/tools/builtins/filesystem.py` with three optional, default-off parameters (`replace_all`, `regex`, `dry_run`). A new module-level `_finalize` helper centralizes the write-vs-preview decision so every operation can dry-run. The JSON schema in `filesystem_definitions.py` gains the three params and clarified descriptions.

**Tech Stack:** Python 3.12, stdlib `re` + `difflib`, pytest, ruff, mypy. Tool results are `ToolSuccess` / `ToolError` (str subclasses; `ToolError` carries a `.category`).

## Global Constraints

- Adding optional params with defaults is non-breaking at the dispatch layer (`execution.py:96-111` calls `tool_func(**call_args)`).
- The **one intentional breaking change**: a bare `replace` on a non-unique `old_string` now errors instead of replacing all matches.
- Do **not** touch `prompts.py` — the schema `description` is the doc surface.
- Final gate: full suite + ruff + mypy must be clean (`uv run poe check-all`).
- Run single tests with `uv run pytest <path>::<Class>::<test> -v`.
- All commit messages end with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

## File Structure

- **Modify** `src/ayder_cli/tools/builtins/filesystem.py` — `file_editor` function: add params, add module-level `_finalize` helper, route each op through it. Add `import re`, `import difflib`.
- **Modify** `src/ayder_cli/tools/builtins/filesystem_definitions.py` — `file_editor` ToolDefinition: add `replace_all`, `regex`, `dry_run` properties; rewrite top-level description; clarify the `operation` description.
- **Modify** `tests/tools/test_impl.py` — rewrite one replace test, add replace/regex/dry-run tests, add schema-presence checks.

The existing `file_editor` is ~80 lines and cohesive; no split is warranted. `_finalize` is the only new unit.

---

## Shared test helper

Several tasks assert on the tool definition. Add this helper **once**, at the top of `tests/tools/test_impl.py` (just below the existing imports), as the first step of Task 1:

```python
def _file_editor_def():
    """Return the file_editor ToolDefinition for schema assertions."""
    from ayder_cli.tools.builtins.filesystem_definitions import TOOL_DEFINITIONS
    return next(d for d in TOOL_DEFINITIONS if d.name == "file_editor")
```

---

### Task 1: Unique-by-default replace (`replace_all`)

**Files:**
- Modify: `src/ayder_cli/tools/builtins/filesystem.py` (`file_editor` signature + `replace` branch)
- Modify: `src/ayder_cli/tools/builtins/filesystem_definitions.py` (`file_editor` properties)
- Test: `tests/tools/test_impl.py` (`TestFileEditorReplace`)

**Interfaces:**
- Consumes: existing `file_editor(project_ctx, file_path, operation, content=None, old_string=None, new_string=None, line_number=None)`.
- Produces: `file_editor(..., replace_all: bool = False)`. `replace` errors (category `"validation"`) when the literal `old_string` matches more than once and `replace_all` is False; success message is `Successfully replaced {count} occurrence(s) in {rel_path}`.

- [ ] **Step 1: Add the shared test helper** (see "Shared test helper" above) to `tests/tools/test_impl.py`.

- [ ] **Step 2: Write/rewrite the failing tests**

Replace the existing `test_multiple_occurrences_replacement` method in `TestFileEditorReplace` (currently around `tests/tools/test_impl.py:294`) with the following, and add the other three methods in the same class:

```python
    def test_multiple_occurrences_without_replace_all_errors(self, tmp_path, project_context):
        """Non-unique old_string is an error unless replace_all is set."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello world! Hello world! Hello world!")

        result = impl.file_editor(
            project_context, str(test_file), "replace",
            old_string="world", new_string="Python",
        )
        assert isinstance(result, ToolError)
        assert result.category == "validation"
        assert "not unique" in result
        assert "found 3 matches" in result
        assert test_file.read_text() == "Hello world! Hello world! Hello world!"

    def test_replace_all_replaces_every_match(self, tmp_path, project_context):
        """replace_all=True rewrites all matches and reports the count."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello world! Hello world! Hello world!")

        result = impl.file_editor(
            project_context, str(test_file), "replace",
            old_string="world", new_string="Python", replace_all=True,
        )
        assert isinstance(result, ToolSuccess)
        assert "3 occurrences" in result
        assert test_file.read_text() == "Hello Python! Hello Python! Hello Python!"

    def test_replace_unique_reports_single_count(self, tmp_path, project_context):
        """A unique match replaces exactly once and says '1 occurrence'."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello world!")

        result = impl.file_editor(
            project_context, str(test_file), "replace",
            old_string="world", new_string="universe",
        )
        assert isinstance(result, ToolSuccess)
        assert "1 occurrence" in result
        assert test_file.read_text() == "Hello universe!"

    def test_replace_all_param_in_schema(self):
        """The schema exposes replace_all so the orchestrator can pass it."""
        props = _file_editor_def().parameters["properties"]
        assert "replace_all" in props
        assert props["replace_all"]["type"] == "boolean"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/tools/test_impl.py::TestFileEditorReplace -v`
Expected: FAIL — `test_multiple_occurrences_without_replace_all_errors` fails (current code replaces all and returns success), `test_replace_all_*`/`test_replace_unique_*` fail (`replace_all` not a param / count text absent), `test_replace_all_param_in_schema` fails (not in schema).

- [ ] **Step 4: Add the `replace_all` parameter to the signature**

In `src/ayder_cli/tools/builtins/filesystem.py`, change the `file_editor` signature to:

```python
def file_editor(
    project_ctx: ProjectContext,
    file_path: str,
    operation: str,
    content: str | None = None,
    old_string: str | None = None,
    new_string: str | None = None,
    line_number: int | None = None,
    replace_all: bool = False,
) -> str:
    """Modify files with specific operations."""
```

- [ ] **Step 5: Implement the uniqueness guard in the `replace` branch**

Replace the entire `elif operation == "replace":` block (currently `filesystem.py:189-204`) with:

```python
        elif operation == "replace":
            if old_string is None or new_string is None:
                return ToolError("Error: 'old_string' and 'new_string' are required for 'replace' operation.", "validation")
            rel_path = project_ctx.to_relative(abs_path)
            if not abs_path.exists():
                return ToolError(f"Error: File '{rel_path}' does not exist.")
            with open(abs_path, "r", encoding="utf-8") as f:
                file_content = f.read()
            count = file_content.count(old_string)
            if count == 0:
                return ToolError(f"Error: 'old_string' not found in {rel_path}. No changes made.")
            if count > 1 and not replace_all:
                return ToolError(
                    f"Error: 'old_string' is not unique (found {count} matches) in {rel_path}. "
                    f"Pass replace_all=true to replace all occurrences, or add surrounding "
                    f"context to make it unique. No changes made.",
                    "validation",
                )
            new_content = (
                file_content.replace(old_string, new_string)
                if replace_all
                else file_content.replace(old_string, new_string, 1)
            )
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            noun = "occurrence" if count == 1 else "occurrences"
            return ToolSuccess(f"Successfully replaced {count} {noun} in {rel_path}")
```

- [ ] **Step 6: Add `replace_all` to the schema**

In `src/ayder_cli/tools/builtins/filesystem_definitions.py`, inside the `file_editor` definition's `properties` dict (after the `line_number` entry, `filesystem_definitions.py:116-119`), add:

```python
                "replace_all": {
                    "type": "boolean",
                    "description": "For 'replace': replace every match. Default false — a non-unique old_string is an error.",
                },
```

- [ ] **Step 7: Run the replace tests and the two known dependents to verify they pass**

Run: `uv run pytest tests/tools/test_impl.py::TestFileEditorReplace tests/tools/test_registry.py::TestToolRegistryDispatch::test_dispatch_file_editor_replace tests/tools/test_impl_coverage.py -v`
Expected: PASS (the dispatch test uses a unique "old"; the empty-file test still hits the not-found branch).

- [ ] **Step 8: Commit**

```bash
git add src/ayder_cli/tools/builtins/filesystem.py src/ayder_cli/tools/builtins/filesystem_definitions.py tests/tools/test_impl.py
git commit -m "$(cat <<'EOF'
feat(file_editor): unique-by-default replace with replace_all opt-in

Non-unique old_string now errors unless replace_all=true; success
reports the occurrence count. Prevents silent over-broad edits.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Regex mode for replace (`regex`)

**Files:**
- Modify: `src/ayder_cli/tools/builtins/filesystem.py` (add `import re`, `regex` param, regex branch)
- Modify: `src/ayder_cli/tools/builtins/filesystem_definitions.py` (`regex` property)
- Test: `tests/tools/test_impl.py` (`TestFileEditorReplace`)

**Interfaces:**
- Consumes: `file_editor(..., replace_all=False)` from Task 1.
- Produces: `file_editor(..., regex: bool = False)`. When `regex=True`, `old_string` is a Python regex and `new_string` is an `re.sub` replacement template (backreferences `\1` / `\g<name>` work). Same uniqueness guard (match count via `finditer`). Invalid pattern → `ToolError(..., "validation")` with text `Invalid regex pattern: ...`.

- [ ] **Step 1: Write the failing tests**

Add to `TestFileEditorReplace` in `tests/tools/test_impl.py`:

```python
    def test_replace_regex_basic(self, tmp_path, project_context):
        test_file = tmp_path / "test.txt"
        test_file.write_text("foo123bar")
        result = impl.file_editor(
            project_context, str(test_file), "replace",
            old_string=r"\d+", new_string="NUM", regex=True,
        )
        assert isinstance(result, ToolSuccess)
        assert test_file.read_text() == "fooNUMbar"

    def test_replace_regex_backreference(self, tmp_path, project_context):
        test_file = tmp_path / "test.txt"
        test_file.write_text("name: Alice")
        result = impl.file_editor(
            project_context, str(test_file), "replace",
            old_string=r"name: (\w+)", new_string=r"user=\1", regex=True,
        )
        assert isinstance(result, ToolSuccess)
        assert test_file.read_text() == "user=Alice"

    def test_replace_regex_non_unique_without_replace_all_errors(self, tmp_path, project_context):
        test_file = tmp_path / "test.txt"
        test_file.write_text("a1 b2 c3")
        result = impl.file_editor(
            project_context, str(test_file), "replace",
            old_string=r"\d", new_string="#", regex=True,
        )
        assert isinstance(result, ToolError)
        assert "not unique" in result
        assert test_file.read_text() == "a1 b2 c3"

    def test_replace_regex_replace_all(self, tmp_path, project_context):
        test_file = tmp_path / "test.txt"
        test_file.write_text("a1 b2 c3")
        result = impl.file_editor(
            project_context, str(test_file), "replace",
            old_string=r"\d", new_string="#", regex=True, replace_all=True,
        )
        assert isinstance(result, ToolSuccess)
        assert test_file.read_text() == "a# b# c#"

    def test_replace_regex_invalid_pattern(self, tmp_path, project_context):
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello")
        result = impl.file_editor(
            project_context, str(test_file), "replace",
            old_string="[unterminated", new_string="x", regex=True,
        )
        assert isinstance(result, ToolError)
        assert result.category == "validation"
        assert "Invalid regex" in result
        assert test_file.read_text() == "hello"

    def test_regex_param_in_schema(self):
        props = _file_editor_def().parameters["properties"]
        assert "regex" in props
        assert props["regex"]["type"] == "boolean"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/tools/test_impl.py::TestFileEditorReplace -k regex -v`
Expected: FAIL — `regex` is not a parameter (TypeError) / not in schema.

- [ ] **Step 3: Add the import and parameter**

In `src/ayder_cli/tools/builtins/filesystem.py`, add `import re` to the top imports (after `import os`, `filesystem.py:7`):

```python
import json
import logging
import os
import re
```

Add `regex: bool = False` to the `file_editor` signature (after `replace_all`):

```python
    replace_all: bool = False,
    regex: bool = False,
) -> str:
```

- [ ] **Step 4: Implement the regex branch**

Replace the `elif operation == "replace":` block (the version from Task 1) with:

```python
        elif operation == "replace":
            if old_string is None or new_string is None:
                return ToolError("Error: 'old_string' and 'new_string' are required for 'replace' operation.", "validation")
            rel_path = project_ctx.to_relative(abs_path)
            if not abs_path.exists():
                return ToolError(f"Error: File '{rel_path}' does not exist.")
            with open(abs_path, "r", encoding="utf-8") as f:
                file_content = f.read()
            if regex:
                try:
                    pattern = re.compile(old_string)
                except re.error as e:
                    return ToolError(f"Invalid regex pattern: {e}", "validation")
                count = sum(1 for _ in pattern.finditer(file_content))
            else:
                count = file_content.count(old_string)
            if count == 0:
                return ToolError(f"Error: 'old_string' not found in {rel_path}. No changes made.")
            if count > 1 and not replace_all:
                return ToolError(
                    f"Error: 'old_string' is not unique (found {count} matches) in {rel_path}. "
                    f"Pass replace_all=true to replace all occurrences, or add surrounding "
                    f"context to make it unique. No changes made.",
                    "validation",
                )
            if regex:
                new_content = pattern.sub(new_string, file_content, count=0 if replace_all else 1)
            else:
                new_content = (
                    file_content.replace(old_string, new_string)
                    if replace_all
                    else file_content.replace(old_string, new_string, 1)
                )
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            noun = "occurrence" if count == 1 else "occurrences"
            return ToolSuccess(f"Successfully replaced {count} {noun} in {rel_path}")
```

- [ ] **Step 5: Add `regex` to the schema**

In `filesystem_definitions.py`, add after the `replace_all` property:

```python
                "regex": {
                    "type": "boolean",
                    "description": "For 'replace': treat old_string as a Python regex; new_string supports backreferences like \\1.",
                },
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/tools/test_impl.py::TestFileEditorReplace -v`
Expected: PASS (all literal and regex replace tests).

- [ ] **Step 7: Commit**

```bash
git add src/ayder_cli/tools/builtins/filesystem.py src/ayder_cli/tools/builtins/filesystem_definitions.py tests/tools/test_impl.py
git commit -m "$(cat <<'EOF'
feat(file_editor): optional regex mode for replace

regex=true treats old_string as a Python pattern with backref support
in new_string; same uniqueness guard via match count.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Dry-run preview for all operations (`dry_run`)

**Files:**
- Modify: `src/ayder_cli/tools/builtins/filesystem.py` (add `import difflib`, `_finalize` helper, `dry_run` param, route all ops through `_finalize`)
- Modify: `src/ayder_cli/tools/builtins/filesystem_definitions.py` (`dry_run` property)
- Test: `tests/tools/test_impl.py` (new `TestFileEditorDryRun`)

**Interfaces:**
- Consumes: `file_editor(..., replace_all=False, regex=False)` from Tasks 1–2.
- Produces: module-level `_finalize(abs_path, rel_path, old_content: str, new_content: str, success_msg: str, dry_run: bool) -> str`. `file_editor(..., dry_run: bool = False)`. With `dry_run=True`, no operation writes; result is a unified diff prefixed `[DRY RUN] No changes written to {rel_path}.` (or `[DRY RUN] No changes would be made to {rel_path}.` when identical).

- [ ] **Step 1: Write the failing tests**

Add a new test class at the end of `tests/tools/test_impl.py`:

```python
class TestFileEditorDryRun:
    """dry_run previews changes as a unified diff and never writes."""

    def test_dry_run_replace(self, tmp_path, project_context):
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello world!\n")
        result = impl.file_editor(
            project_context, str(test_file), "replace",
            old_string="world", new_string="universe", dry_run=True,
        )
        assert isinstance(result, ToolSuccess)
        assert "[DRY RUN]" in result
        assert "-Hello world!" in result
        assert "+Hello universe!" in result
        assert test_file.read_text() == "Hello world!\n"

    def test_dry_run_write(self, tmp_path, project_context):
        test_file = tmp_path / "test.txt"
        test_file.write_text("original\n")
        result = impl.file_editor(
            project_context, str(test_file), "write",
            content="replaced\n", dry_run=True,
        )
        assert isinstance(result, ToolSuccess)
        assert "[DRY RUN]" in result
        assert test_file.read_text() == "original\n"

    def test_dry_run_insert(self, tmp_path, project_context):
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\n")
        result = impl.file_editor(
            project_context, str(test_file), "insert",
            line_number=2, content="Inserted", dry_run=True,
        )
        assert isinstance(result, ToolSuccess)
        assert "[DRY RUN]" in result
        assert "+Inserted" in result
        assert test_file.read_text() == "Line 1\nLine 2\n"

    def test_dry_run_delete(self, tmp_path, project_context):
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\nLine 3\n")
        result = impl.file_editor(
            project_context, str(test_file), "delete",
            line_number=2, dry_run=True,
        )
        assert isinstance(result, ToolSuccess)
        assert "[DRY RUN]" in result
        assert "-Line 2" in result
        assert test_file.read_text() == "Line 1\nLine 2\nLine 3\n"

    def test_dry_run_write_identical_reports_no_change(self, tmp_path, project_context):
        test_file = tmp_path / "test.txt"
        test_file.write_text("same\n")
        result = impl.file_editor(
            project_context, str(test_file), "write",
            content="same\n", dry_run=True,
        )
        assert isinstance(result, ToolSuccess)
        assert "No changes would be made" in result
        assert test_file.read_text() == "same\n"

    def test_dry_run_param_in_schema(self):
        props = _file_editor_def().parameters["properties"]
        assert "dry_run" in props
        assert props["dry_run"]["type"] == "boolean"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/tools/test_impl.py::TestFileEditorDryRun -v`
Expected: FAIL — `dry_run` is not a parameter (TypeError) / not in schema.

- [ ] **Step 3: Add the `difflib` import and the `_finalize` helper**

In `src/ayder_cli/tools/builtins/filesystem.py`, add `import difflib` to the imports (after `import re`):

```python
import json
import logging
import os
import re
import difflib
```

Add this module-level helper just above the `file_editor` function definition:

```python
def _finalize(
    abs_path,
    rel_path,
    old_content: str,
    new_content: str,
    success_msg: str,
    dry_run: bool,
) -> str:
    """Write *new_content* and return *success_msg*, or, when *dry_run* is set,
    return a unified diff and write nothing."""
    if dry_run:
        if old_content == new_content:
            return ToolSuccess(f"[DRY RUN] No changes would be made to {rel_path}.")
        diff = "".join(
            difflib.unified_diff(
                old_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"a/{rel_path}",
                tofile=f"b/{rel_path}",
            )
        )
        return ToolSuccess(f"[DRY RUN] No changes written to {rel_path}.\n{diff}")
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    return ToolSuccess(success_msg)
```

- [ ] **Step 4: Add the `dry_run` parameter and route every operation through `_finalize`**

Replace the **entire** `file_editor` function body (signature through the final `except`) with the version below. This hoists `rel_path` to the top and threads `dry_run` through all four operations:

```python
def file_editor(
    project_ctx: ProjectContext,
    file_path: str,
    operation: str,
    content: str | None = None,
    old_string: str | None = None,
    new_string: str | None = None,
    line_number: int | None = None,
    replace_all: bool = False,
    regex: bool = False,
    dry_run: bool = False,
) -> str:
    """Modify files with specific operations."""
    try:
        abs_path = project_ctx.validate_path(file_path)
        rel_path = project_ctx.to_relative(abs_path)

        if operation == "write":
            if content is None:
                return ToolError("Error: 'content' parameter is required for 'write' operation.", "validation")
            old_content = abs_path.read_text(encoding="utf-8") if abs_path.exists() else ""
            if not dry_run:
                abs_path.parent.mkdir(parents=True, exist_ok=True)
            return _finalize(
                abs_path, rel_path, old_content, content,
                f"Successfully wrote to {rel_path}", dry_run,
            )

        elif operation == "replace":
            if old_string is None or new_string is None:
                return ToolError("Error: 'old_string' and 'new_string' are required for 'replace' operation.", "validation")
            if not abs_path.exists():
                return ToolError(f"Error: File '{rel_path}' does not exist.")
            with open(abs_path, "r", encoding="utf-8") as f:
                file_content = f.read()
            if regex:
                try:
                    pattern = re.compile(old_string)
                except re.error as e:
                    return ToolError(f"Invalid regex pattern: {e}", "validation")
                count = sum(1 for _ in pattern.finditer(file_content))
            else:
                count = file_content.count(old_string)
            if count == 0:
                return ToolError(f"Error: 'old_string' not found in {rel_path}. No changes made.")
            if count > 1 and not replace_all:
                return ToolError(
                    f"Error: 'old_string' is not unique (found {count} matches) in {rel_path}. "
                    f"Pass replace_all=true to replace all occurrences, or add surrounding "
                    f"context to make it unique. No changes made.",
                    "validation",
                )
            if regex:
                new_content = pattern.sub(new_string, file_content, count=0 if replace_all else 1)
            else:
                new_content = (
                    file_content.replace(old_string, new_string)
                    if replace_all
                    else file_content.replace(old_string, new_string, 1)
                )
            noun = "occurrence" if count == 1 else "occurrences"
            return _finalize(
                abs_path, rel_path, file_content, new_content,
                f"Successfully replaced {count} {noun} in {rel_path}", dry_run,
            )

        elif operation == "insert":
            if line_number is None or content is None:
                return ToolError("Error: 'line_number' and 'content' are required for 'insert' operation.", "validation")
            if not abs_path.exists():
                return ToolError(f"Error: File '{rel_path}' does not exist.")
            with open(abs_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if line_number < 1:
                return ToolError("Error: line_number must be >= 1.", "validation")
            old_content = "".join(lines)
            idx = min(line_number - 1, len(lines))
            ins = content
            if ins and not ins.endswith("\n"):
                ins += "\n"
            new_content = "".join(lines[:idx] + [ins] + lines[idx:])
            return _finalize(
                abs_path, rel_path, old_content, new_content,
                f"Successfully inserted content at line {line_number} in {rel_path}", dry_run,
            )

        elif operation == "delete":
            if line_number is None:
                return ToolError("Error: 'line_number' is required for 'delete' operation.", "validation")
            if not abs_path.exists():
                return ToolError(f"Error: File '{rel_path}' does not exist.")
            with open(abs_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if line_number < 1 or line_number > len(lines):
                return ToolError(f"Error: line_number {line_number} is out of range (1-{len(lines)}).", "validation")
            old_content = "".join(lines)
            deleted = lines[line_number - 1]
            new_content = "".join(lines[: line_number - 1] + lines[line_number:])
            preview = deleted.rstrip("\n")[:80]
            return _finalize(
                abs_path, rel_path, old_content, new_content,
                f"Deleted line {line_number} from {rel_path}: '{preview}'", dry_run,
            )

        else:
            return ToolError(f"Error: Unknown operation '{operation}'", "validation")

    except ValueError as e:
        return ToolError(f"Security Error: {str(e)}", "security")
    except Exception as e:
        return ToolError(f"Error executing file_editor: {str(e)}", "execution")
```

- [ ] **Step 5: Add `dry_run` to the schema**

In `filesystem_definitions.py`, add after the `regex` property:

```python
                "dry_run": {
                    "type": "boolean",
                    "description": "Preview the change as a unified diff without writing. Works for all operations.",
                },
```

- [ ] **Step 6: Run the dry-run tests and the full file_editor regression set**

Run: `uv run pytest tests/tools/test_impl.py::TestFileEditorDryRun tests/tools/test_impl.py::TestFileEditorReplace tests/tools/test_impl.py::TestFileEditorInsert tests/tools/test_impl.py::TestFileEditorDelete -v`
Expected: PASS (dry-run plus all existing write/replace/insert/delete behavior unchanged).

- [ ] **Step 7: Commit**

```bash
git add src/ayder_cli/tools/builtins/filesystem.py src/ayder_cli/tools/builtins/filesystem_definitions.py tests/tools/test_impl.py
git commit -m "$(cat <<'EOF'
feat(file_editor): dry_run preview (unified diff) for all operations

A shared _finalize helper writes or, when dry_run is set, returns a
unified diff without touching the file.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Clarify descriptions (insert + top-level)

**Files:**
- Modify: `src/ayder_cli/tools/builtins/filesystem_definitions.py` (`file_editor` top-level `description` + `operation` description)
- Test: `tests/tools/test_impl.py`

**Interfaces:**
- Consumes: the `file_editor` ToolDefinition with `replace_all`, `regex`, `dry_run` present (Tasks 1–3).
- Produces: no code-behavior change. Documentation only.

- [ ] **Step 1: Write the failing tests**

Add to `tests/tools/test_impl.py` (top level, after `TestFileEditorDryRun`):

```python
class TestFileEditorDocs:
    """The schema description documents the real behavior."""

    def test_insert_description_clarifies_before_semantics(self):
        op_desc = _file_editor_def().parameters["properties"]["operation"]["description"]
        assert "becomes the new line" in op_desc

    def test_top_level_description_mentions_unique_and_dry_run(self):
        desc = _file_editor_def().description
        assert "replace_all" in desc
        assert "dry_run" in desc
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/tools/test_impl.py::TestFileEditorDocs -v`
Expected: FAIL — current descriptions don't contain those strings.

- [ ] **Step 3: Rewrite the top-level description**

In `filesystem_definitions.py`, replace the `file_editor` `description=( ... )` value (`filesystem_definitions.py:85-88`) with:

```python
        description=(
            "Modify files. Operations: 'write' (overwrite entirely, for new/small files), "
            "'replace' (replace an exact string — unique by default; pass replace_all=true "
            "for multiple matches, or regex=true for pattern mode), 'insert' (add a line), "
            "and 'delete' (remove a line). Pass dry_run=true on any operation to preview a "
            "unified diff without writing."
        ),
```

- [ ] **Step 4: Clarify the `operation` description**

In the same definition, replace the `operation` property's `description` (`filesystem_definitions.py:102`) with:

```python
                    "description": (
                        "The edit operation. insert: content becomes the new line N "
                        "(existing line N and below shift down); line_number past EOF appends."
                    ),
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/tools/test_impl.py::TestFileEditorDocs -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ayder_cli/tools/builtins/filesystem_definitions.py tests/tools/test_impl.py
git commit -m "$(cat <<'EOF'
docs(file_editor): clarify insert-before semantics and new options

Spell out that insert content becomes the new line N, and document
replace_all / regex / dry_run in the tool description.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Full-suite gate

**Files:** none (verification only).

- [ ] **Step 1: Run the complete check suite**

Run: `uv run poe check-all`
Expected: all tests pass (the previous `1513 passed` plus the new file_editor tests, minus the one rewritten test), ruff clean, mypy clean.

- [ ] **Step 2: If anything fails, fix and re-run**

Address any ruff/mypy finding (e.g., import ordering for `re`/`difflib`) or test failure, then re-run `uv run poe check-all` until clean. Do not commit a broken gate.

- [ ] **Step 3: Final completion**

Use the **superpowers:finishing-a-development-branch** skill to verify tests, present options, and complete the work.

---

## Self-Review

**1. Spec coverage:**
- Unique-by-default replace + `replace_all` → Task 1. ✓
- Regex mode → Task 2. ✓
- Dry-run for all ops → Task 3. ✓
- Insert docs + top-level description → Task 4. ✓
- Not-found stays a plain error → preserved in Task 1/2/3 replace branch (count == 0 path), regression-guarded by existing `test_replacement_old_string_not_found` and `test_replace_string_empty_file`. ✓
- No `prompts.py` change → none in plan. ✓
- Schema exposure of all three params → folded into Tasks 1–3. ✓

**2. Placeholder scan:** No TBD/TODO/"handle edge cases"; every code step shows complete code. ✓

**3. Type consistency:** `_finalize(abs_path, rel_path, old_content, new_content, success_msg, dry_run)` is defined in Task 3 and called with that exact arg order in all four ops. Params `replace_all`/`regex`/`dry_run` are `bool` everywhere. Success text "occurrence(s)" asserted consistently (`1 occurrence`, `3 occurrences`). `_file_editor_def()` helper defined once (Task 1) and reused. ✓
