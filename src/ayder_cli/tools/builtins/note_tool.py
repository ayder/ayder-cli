"""Consolidated ``note(action=...)`` handler (spec 04).

The task tool's lightweight, caller-named sibling: a flat note (title + body),
no Signature header, no status enum. One tool covers
``create | read | update | list | delete``. Every action returns short plain
text bounded by construction, so the chat-loop's 8192-char tool-result
truncation is never triggered (the definition sets ``max_result_chars=0``).

File-I/O lives in ``notes.py``; this module owns dispatch, per-action
validation, and output bounding (``offset`` / ``max_chars`` / ``limit``).
"""

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError, ToolResult, ToolSuccess

from .notes import (
    _title_to_slug,
    delete_note_file,
    list_note_ids,
    read_note_file,
    update_note_file,
    write_note_file,
)

_DEFAULT_READ_CHARS = 4000
_MAX_READ_CHARS = 8000
_DEFAULT_LIST_LIMIT = 30
_MAX_LIST_LIMIT = 100
VALID_MODES: tuple[str, ...] = ("append", "replace")


def _bounded(text: str, offset: int, max_chars: int) -> str:
    """Return ``text[offset:offset+max_chars]`` with a byte-offset hint if cut."""
    offset = max(0, offset)
    chunk = text[offset : offset + max_chars]
    consumed = offset + len(chunk)
    if consumed < len(text):
        chunk += f"\n… {len(text) - consumed} more chars (use offset={consumed})"
    return chunk


def _create(
    project_ctx: ProjectContext,
    note_id: str | None,
    content: str | None,
    tags: str | None,
) -> ToolResult:
    if not note_id or not note_id.strip():
        return ToolError("note_id is required for action 'create'", "validation")
    if content is None:
        return ToolError("content is required for action 'create'", "validation")
    try:
        slug = write_note_file(project_ctx, note_id.strip(), content, tags=tags, exclusive=True)
    except FileExistsError:
        sid = _title_to_slug(note_id.strip())
        return ToolError(
            f"note '{sid}' already exists — use action=read or action=update",
            "validation",
        )
    return ToolSuccess(f"note '{slug}' created")


def _read(
    project_ctx: ProjectContext,
    note_id: str | None,
    max_chars: int | None,
    offset: int | None,
) -> ToolResult:
    if not note_id or not note_id.strip():
        return ToolError("note_id is required for action 'read'", "validation")
    body = read_note_file(project_ctx, note_id.strip())
    if body is None:
        return ToolError(f"note '{_title_to_slug(note_id.strip())}' not found", "not_found")
    cap = min(max_chars or _DEFAULT_READ_CHARS, _MAX_READ_CHARS)
    return ToolSuccess(_bounded(body, max(0, int(offset or 0)), cap))


def _update(
    project_ctx: ProjectContext,
    note_id: str | None,
    content: str | None,
    mode: str | None,
) -> ToolResult:
    if not note_id or not note_id.strip():
        return ToolError("note_id is required for action 'update'", "validation")
    if content is None:
        return ToolError("content is required for action 'update'", "validation")
    m = (mode or "append").strip().lower()
    if m not in VALID_MODES:
        return ToolError(f"Invalid mode '{mode}'. Valid: append, replace", "validation")
    if not update_note_file(project_ctx, note_id.strip(), content, mode=m):
        return ToolError(
            f"note '{_title_to_slug(note_id.strip())}' not found — use action=create",
            "not_found",
        )
    return ToolSuccess(
        f"note '{_title_to_slug(note_id.strip())}' updated ({m}, {len(content)} chars)"
    )


def _list(
    project_ctx: ProjectContext,
    prefix: str | None,
    limit: int | None,
    offset: int | None,
) -> ToolResult:
    lim = _DEFAULT_LIST_LIMIT if limit is None else int(limit)
    lim = max(1, min(lim, _MAX_LIST_LIMIT))
    off = max(0, int(offset or 0))
    ids = list_note_ids(project_ctx, prefix=prefix)
    total = len(ids)
    if total == 0:
        suffix = f" with prefix '{prefix}'" if prefix else ""
        return ToolSuccess(f"No notes found{suffix}.")
    window = ids[off : off + lim]
    start, end = off + 1, off + len(window)
    footer = f"{total} total · showing {start}-{end}"
    if end < total:
        footer += f" · {total - end} more (use offset={end})"
    return ToolSuccess("\n".join([*window, footer]))


def _delete(project_ctx: ProjectContext, note_id: str | None) -> ToolResult:
    if not note_id or not note_id.strip():
        return ToolError("note_id is required for action 'delete'", "validation")
    if not delete_note_file(project_ctx, note_id.strip()):
        return ToolError(f"note '{_title_to_slug(note_id.strip())}' not found", "not_found")
    return ToolSuccess(f"note '{_title_to_slug(note_id.strip())}' deleted")


def note(
    project_ctx: ProjectContext,
    action: str,
    note_id: str | None = None,
    content: str | None = None,
    tags: str | None = None,
    mode: str | None = None,
    max_chars: int | None = None,
    offset: int | None = None,
    limit: int | None = None,
    prefix: str | None = None,
) -> ToolResult:
    """Dispatch a note action. See module docstring for the per-action contract."""
    act = (action or "").strip().lower()
    if act == "create":
        return _create(project_ctx, note_id, content, tags)
    if act == "read":
        return _read(project_ctx, note_id, max_chars, offset)
    if act == "update":
        return _update(project_ctx, note_id, content, mode)
    if act == "list":
        return _list(project_ctx, prefix, limit, offset)
    if act == "delete":
        return _delete(project_ctx, note_id)
    return ToolError(
        f"Unknown action '{action}'. Valid: create, read, update, list, delete",
        "validation",
    )
