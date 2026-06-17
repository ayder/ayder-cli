# Agent Deliverable Notes — Design Spec

**Date:** 2026-06-18
**Status:** Approved (brainstorming) — pending spec review
**Related:** `docs/superpowers/plans/2026-06-17-agent-result-push-delivery.md` (this rides on the final-message capture defined there)

## Goal

Every agent run leaves a durable, human-investigable note of its deliverable in `.ayder/notes/`, browsable via the existing `/notes` command, with the note path surfaced to the main LLM so it can re-read the full deliverable on demand.

This solves two problems at once:
1. **Investigation:** the user can open any agent's full output later, even after it scrolls out of the conversation.
2. **Context pressure (review finding):** the injected `[agent-result]` block can be compacted out of the model's window; a `note:` path lets the main LLM `read_file` the full deliverable on demand. "Delivered once" no longer has to mean "kept in context forever."

## Existing infrastructure (reused, not rebuilt)

- **`create_note` tool** — `src/ayder_cli/tools/builtins/notes.py:32`. Writes `.ayder/notes/<slug>.md` with YAML frontmatter (`title`, `date`, `tags`). Tagged `("metadata",)`, permission `"w"`.
- **`_get_notes_dir`** — `notes.py:16` → `project_ctx.root / ".ayder" / "notes"`.
- **`/notes` command** — `src/ayder_cli/tui/commands.py:554` (`handle_notes`). No-arg → interactive picker over `.ayder/notes/*.md`; `/notes <name>` → opens the note in the in-app editor (`_open_note_in_editor`, `commands.py:526`).
- **`.ayder/notes/`** exists and is gitignored (`.gitignore:30`). Scratch area.

**Known gotcha being fixed:** `create_note` derives the filename from the title slug only (`notes.py:50-52`), so same-titled notes silently overwrite. Agent notes use a collision-proof filename instead (see Filename).

## Architecture — one capture, three destinations

The push-delivery plan already captures the agent's **final assistant message** (`AgentRunner._final_message`). That single capture now feeds three places:

1. **Inject** into the conversation (push delivery — existing plan).
2. **Persist** to disk as a note (this spec).
3. **Reference** — the note's relative path is attached to the result and rendered in the injected block.

No second capture, no agent cooperation, deterministic.

## Components

### 1. `write_agent_note(...)` — `src/ayder_cli/tools/builtins/notes.py`

Lives next to `create_note`. A shared `_write_note(notes_dir, filename, frontmatter, body)` core is extracted so `create_note` and `write_agent_note` stay DRY (both build the same YAML-frontmatter + body shape).

```
def write_agent_note(
    project_ctx: ProjectContext,
    *,
    agent_name: str,
    run_id: int,
    cycle_id: int,
    status: str,
    task: str,
    content: str,
    timestamp: str,          # "YYYYMMDD-HHMMSS"; passed in (testable, no hidden clock)
    error: str | None = None,
) -> str | None:             # project-relative path, or None on write failure
```

- Builds the filename `{timestamp}-{agent_slug}-run{run_id}.md` (agent_slug via the existing `_title_to_slug`).
- Writes frontmatter + body (see Note Format).
- Returns `project_ctx.to_relative(path)`.
- Writes for **every** terminal status (completed / timeout / error) — partial or failed output is exactly what the user investigates. On non-completed status, the body includes the error.
- Best-effort: if writing fails, it logs and returns `None`; a note-write failure must never fail the agent run (the runner sets `note_path = None`).

### 2. `AgentRunner.run` — `src/ayder_cli/agents/runner.py`

After computing the final `content` in each terminal branch, calls `write_agent_note(self._project_ctx, ...)` with the run's metadata and the captured final message, captures the returned relative path, and passes it to `AgentResult(note_path=...)`. The runner already holds `self._project_ctx`. The timestamp is produced at the call site (`datetime.now().strftime("%Y%m%d-%H%M%S")`) and passed in.

### 3. `AgentResult.note_path: str | None` — `src/ayder_cli/agents/summary.py`

New optional field. `format_for_injection` adds a `note="<rel_path>"` attribute to the block header **only when present**:

```
[agent-result name="reviewer" run="3" status="completed" note=".ayder/notes/20260618-143022-reviewer-run3.md"]
<final message, verbatim>
[/agent-result]
```

The path is sanitized via the same `_sanitize_attr` used for the other header attributes.

### 4. Capability prompt — `src/ayder_cli/agents/registry.py` (`get_capability_prompts`)

One added line: each `[agent-result]` block carries a `note="…"` path; if the deliverable has scrolled out of context, read that file with `read_file` rather than re-dispatching the agent.

### 5. `/notes` — unchanged

No code change required. Because filenames are timestamp-prefixed, the existing `sorted(...glob("*.md"))` ordering is chronological for free. (Optional, deferred: reverse to newest-first — not in this phase.)

## Note Format

File `.ayder/notes/20260618-143022-reviewer-run3.md`:

```markdown
---
title: "reviewer — run 3"
date: 2026-06-18 14:30:22
agent: reviewer
run_id: 3
cycle_id: 1
status: completed
tags: [agent-result]
---
## Task
<the dispatched task, verbatim>

## Result
<the agent's final message, verbatim — never truncated>
```

- For `status` ≠ `completed`, append a `## Error` section with the error metadata.
- Frontmatter holds scalar metadata only; the (possibly long/multiline) task and deliverable live in the body as sections.

## Filename

`{YYYYMMDD-HHMMSS}-{agent-slug}-run{run_id}.md`

`run_id` is unique within a registry instance, so the filename is collision-proof even if two agents finish in the same second. This deliberately differs from `create_note`'s title-slug-only scheme.

## Data Flow

```
agent run completes (any status)
  → AgentRunner._final_message(messages)        # the deliverable
  → write_agent_note(project_ctx, ...)          # persist to .ayder/notes/
  → note_path (relative)
  → AgentResult(content, note_path, ...)
  → inject_agent_results → [agent-result ... note="..."] block in conversation
  → user: /notes  (browse/open)   |   main LLM: read_file(note_path) on demand
```

## Testing

- `write_agent_note`: writes a file under `.ayder/notes/`, with correct frontmatter and `## Task` / `## Result` sections; filename matches `{ts}-{slug}-run{id}.md`; returns the project-relative path; unique across two runs with the same agent name + title.
- `write_agent_note` error branch: includes `## Error`; a write failure returns empty and does not raise.
- `AgentRunner.run`: sets `note_path` on the returned `AgentResult` (use a `tmp_path` project context; assert the file exists and `note_path` points to it).
- `AgentResult.format_for_injection`: includes `note="..."` when `note_path` is set; omits the attribute when `None`; path is sanitized.
- `inject_agent_results`: the `note=` attribute survives into the injected message.

## Scope

**In scope:** runner-authored deterministic note per run (all statuses); note path surfaced in the result block + capability prompt; reuse of existing `notes.py` writer and `/notes` browser.

**Out of scope (YAGNI):**
- Retention / auto-cleanup — notes accumulate in gitignored `.ayder/notes/`; the user manages them. (Revisit only if it becomes a problem.)
- A separate agent-callable note tool — the deterministic writer covers the stated requirement; `create_note` already exists if an agent wants extra working notes.
- Newest-first `/notes` ordering — timestamp prefix already gives chronological order.

## Integration with the push-delivery plan

This is ~1.5 tasks appended to `2026-06-17-agent-result-push-delivery.md`:
- `AgentResult.note_path` field + `format_for_injection` `note=` attribute → folds into that plan's **Task 1**.
- `write_agent_note` + `_write_note` extraction + `AgentRunner` wiring → a **new task** after Task 2.
- Capability-prompt `note:` line → joins that plan's **Task 7**.

No conflict with the push-delivery design; it consumes the same final-message capture and the same `cycle_id`.
