"""Consolidated ``task(action=...)`` handler (spec 01).

One tool covers ``create | list | show | status | update_status | update``.
Every action returns short **plain text** bounded by construction, so the
chat-loop's generic tool-result truncation (which *replaces* over-budget JSON
with a useless structural summary) is never triggered. The tool definition sets
``max_result_chars=0`` to opt out of generic truncation; this module owns the
bounding via ``limit`` / ``offset`` / ``section`` / ``max_chars`` clamps.

Canonical task-file format (the tool is the sole writer of the signature)::

    # <title>

    ## Signature
    - **ID:** TASK-007
    - **Status:** pending
    - **Created:** 2026-06-25 10:00:00
    - **Branch:** agent/<slug>
    - **Dependencies:** none

    <body — PRD prose, verbatim>

All helpers (``_next_id``, ``_title_to_slug``, ``resolve_task_path`` …) are
imported from ``tasks.py`` and not duplicated; the agent harness still depends
on ``read_task`` there.
"""

import re
from datetime import datetime

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError, ToolResult, ToolSuccess

from .tasks import (
    _ensure_tasks_dir,
    _extract_id,
    _get_tasks_dir,
    _ID_LOCK,
    _next_id,
    _parse_status,
    _title_to_slug,
    resolve_task_path,
)

# Status enum (D4). ``done`` is reopenable — any enum value is a legal target;
# an off-enum value is the "illegal transition".
VALID_STATUSES: tuple[str, ...] = ("pending", "in_progress", "done", "blocked")

# Output-budget clamps. The generic loop cap is never approached: show is
# capped well under it and list rows are short with a bounded count.
_DEFAULT_SHOW_CHARS = 4000
_MAX_SHOW_CHARS = 8000
_DEFAULT_LIST_LIMIT = 30
_MAX_LIST_LIMIT = 100


# --------------------------------------------------------------------------- #
# rendering / parsing helpers
# --------------------------------------------------------------------------- #
def _canonical_id(path) -> str:
    tid = _extract_id(path.name)
    return f"TASK-{tid:03d}" if tid is not None else path.stem


def _normalize_deps(dependencies: str | None) -> str:
    """Normalize ``"3, TASK-004 , 5"`` → ``"TASK-003, TASK-004, TASK-005"``."""
    if not dependencies or not dependencies.strip():
        return "none"
    out: list[str] = []
    for raw in dependencies.split(","):
        tok = raw.strip()
        if not tok:
            continue
        m = re.fullmatch(r"(?:TASK-)?0*(\d+)", tok, re.IGNORECASE)
        out.append(f"TASK-{int(m.group(1)):03d}" if m else tok)
    return ", ".join(out) if out else "none"


def _strip_caller_signature(body: str) -> str:
    """Strip a leading H1 and any ``## Signature`` block from caller body.

    Keeps the tool authoritative over the H1 title and the signature, so a
    caller pasting a full PRD (with its own header) does not double up.
    """
    lines = body.splitlines()
    i, n = 0, len(lines)
    while i < n and lines[i].strip() == "":
        i += 1
    if i < n and lines[i].lstrip().startswith("# ") and not lines[
        i
    ].lstrip().startswith("## "):
        i += 1
    out: list[str] = []
    while i < n:
        if re.match(r"^\s*##\s+Signature\s*$", lines[i], re.IGNORECASE):
            i += 1
            while i < n and not re.match(r"^\s*#{1,2}\s+\S", lines[i]):
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out).strip("\n")


def _render_task(
    task_id: int, title: str, status: str, branch: str, deps: str, body: str
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = "\n".join(
        [
            f"# {title}",
            "",
            "## Signature",
            f"- **ID:** TASK-{task_id:03d}",
            f"- **Status:** {status}",
            f"- **Created:** {now}",
            f"- **Branch:** {branch}",
            f"- **Dependencies:** {deps}",
        ]
    )
    text = header + "\n"
    if body:
        text += "\n" + body.strip("\n") + "\n"
    return text


def _find_section(content: str, name: str):
    """Locate a heading ``name`` (any level, case-insensitive).

    Returns ``(start_line, end_line, level)`` spanning the heading through the
    line before the next heading of the same-or-shallower level, or ``None``.
    """
    lines = content.splitlines()
    target = name.strip().lower()
    for idx, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.*?)\s*$", line)
        if m and m.group(2).strip().lower() == target:
            level = len(m.group(1))
            end = len(lines)
            for j in range(idx + 1, len(lines)):
                m2 = re.match(r"^(#{1,6})\s+", lines[j])
                if m2 and len(m2.group(1)) <= level:
                    end = j
                    break
            return idx, end, level
    return None


def _bounded(text: str, offset: int, max_chars: int) -> str:
    """Return ``text[offset:offset+max_chars]`` with a byte-offset hint if cut."""
    offset = max(0, offset)
    chunk = text[offset : offset + max_chars]
    consumed = offset + len(chunk)
    if consumed < len(text):
        remaining = len(text) - consumed
        chunk += f"\n… {remaining} more chars (use offset={consumed})"
    return chunk


# --------------------------------------------------------------------------- #
# actions
# --------------------------------------------------------------------------- #
def _create(
    project_ctx: ProjectContext,
    title: str | None,
    body: str | None,
    dependencies: str | None,
    branch: str | None,
    status: str | None,
) -> ToolResult:
    if not title or not title.strip():
        return ToolError("title is required for action 'create'", "validation")
    title = title.strip()
    st = (status or "pending").strip().lower()
    if st not in VALID_STATUSES:
        return ToolError(
            f"Invalid status '{status}'. Valid: {', '.join(VALID_STATUSES)}",
            "validation",
        )
    slug = _title_to_slug(title)
    br = (branch or f"agent/{slug}").strip()
    deps = _normalize_deps(dependencies)
    clean_body = _strip_caller_signature(body) if body else ""

    _ensure_tasks_dir(project_ctx)
    last_err: Exception | None = None
    # Hold the shared allocation lock across allocate-then-claim so concurrent
    # creates (worker threads) serialize and each gets a unique id. The per-file
    # O_EXCL is the second line of defense (leftover same-slug files).
    with _ID_LOCK:
        for _ in range(5):
            task_id = _next_id(project_ctx)
            path = _get_tasks_dir(project_ctx) / f"TASK-{task_id:03d}-{slug}.md"
            try:
                with open(path, "x", encoding="utf-8") as fh:  # O_EXCL: atomic claim
                    fh.write(_render_task(task_id, title, st, br, deps, clean_body))
            except FileExistsError as exc:
                last_err = exc
                continue
            return ToolSuccess(f"TASK-{task_id:03d} created · {br} · {st}")
    return ToolError(
        f"Could not allocate a unique task ID after retries ({last_err})",
        "execution",
    )


def _list(
    project_ctx: ProjectContext,
    status: str | None,
    limit: int | None,
    offset: int | None,
) -> ToolResult:
    _ensure_tasks_dir(project_ctx)
    flt = (status or "pending").strip().lower()
    lim = _DEFAULT_LIST_LIMIT if limit is None else int(limit)
    lim = max(1, min(lim, _MAX_LIST_LIMIT))
    off = max(0, int(offset or 0))

    rows: list[tuple[int, str, str]] = []
    for path in _get_tasks_dir(project_ctx).glob("*.md"):
        tid = _extract_id(path.name)
        if tid is None:
            continue
        st = _parse_status(path)
        if flt != "all" and st.lower() != flt:
            continue
        stem = path.stem
        prefix = f"TASK-{tid:03d}-"
        slug = stem[len(prefix):] if stem.startswith(prefix) else stem
        rows.append((tid, st, slug))
    rows.sort(key=lambda r: r[0])

    total = len(rows)
    if total == 0:
        suffix = "" if flt == "all" else f" with status '{flt}'"
        return ToolSuccess(f"No tasks found{suffix}.")

    window = rows[off : off + lim]
    lines = [f"TASK-{tid:03d} [{st}] {slug}" for tid, st, slug in window]
    start = off + 1
    end = off + len(window)
    footer = f"{total} total · showing {start}-{end}"
    if end < total:
        footer += f" · {total - end} more (use offset={end})"
    return ToolSuccess("\n".join(lines + [footer]))


def _show(
    project_ctx: ProjectContext,
    identifier: str | None,
    section: str | None,
    meta_only: bool,
    max_chars: int | None,
    offset: int | None,
) -> ToolResult:
    if not identifier:
        return ToolError("identifier is required for action 'show'", "validation")
    path = resolve_task_path(project_ctx, identifier)
    if path is None:
        return ToolError(f"Task not found: {identifier}", "not_found")
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover - unexpected IO
        return ToolError(f"Error reading task file: {exc}", "execution")

    if meta_only:
        found = _find_section(content, "Signature")
        if found is None:
            return ToolError("No Signature section in task file", "not_found")
        s, e, _ = found
        text = "\n".join(content.splitlines()[s:e]).strip("\n")
    elif section:
        found = _find_section(content, section)
        if found is None:
            return ToolError(f"Section not found: {section}", "not_found")
        s, e, _ = found
        text = "\n".join(content.splitlines()[s:e]).strip("\n")
    else:
        text = content

    cap = min(max_chars or _DEFAULT_SHOW_CHARS, _MAX_SHOW_CHARS)
    return ToolSuccess(_bounded(text, max(0, int(offset or 0)), cap))


def _status(project_ctx: ProjectContext, identifier: str | None) -> ToolResult:
    if not identifier:
        return ToolError("identifier is required for action 'status'", "validation")
    path = resolve_task_path(project_ctx, identifier)
    if path is None:
        return ToolError(f"Task not found: {identifier}", "not_found")
    return ToolSuccess(f"{_canonical_id(path)}: {_parse_status(path)}")


def _update_status(
    project_ctx: ProjectContext, identifier: str | None, status: str | None
) -> ToolResult:
    if not status:
        return ToolError(
            "status is required for action 'update_status'", "validation"
        )
    target = status.strip().lower()
    if target not in VALID_STATUSES:
        return ToolError(
            f"Invalid status '{status}'. Valid: {', '.join(VALID_STATUSES)}",
            "validation",
        )
    if not identifier:
        return ToolError(
            "identifier is required for action 'update_status'", "validation"
        )
    path = resolve_task_path(project_ctx, identifier)
    if path is None:
        return ToolError(f"Task not found: {identifier}", "not_found")
    current = _parse_status(path)
    content = path.read_text(encoding="utf-8")
    new_content, n = re.subn(
        r"(-\s+\*\*Status:\*\*\s+).+", rf"\g<1>{target}", content, count=1
    )
    if n == 0:
        return ToolError("No Status line found in task file", "execution")
    path.write_text(new_content, encoding="utf-8")
    return ToolSuccess(f"{_canonical_id(path)}: {current} → {target}")


def _update(
    project_ctx: ProjectContext,
    identifier: str | None,
    section: str | None,
    content_arg: str | None,
) -> ToolResult:
    if not identifier:
        return ToolError("identifier is required for action 'update'", "validation")
    if not section or not section.strip():
        return ToolError("section is required for action 'update'", "validation")
    if content_arg is None:
        return ToolError("content is required for action 'update'", "validation")
    if section.strip().lower() == "signature":
        return ToolError(
            "Cannot edit the Signature section (tool-owned)", "validation"
        )
    path = resolve_task_path(project_ctx, identifier)
    if path is None:
        return ToolError(f"Task not found: {identifier}", "not_found")

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    block = [f"## {section.strip()}", "", content_arg.strip("\n")]
    found = _find_section(text, section)
    if found:
        s, e, _ = found
        after = lines[e:]
        new_lines = lines[:s] + block + ([""] + after if after else [])
    else:
        new_lines = lines + ["", *block]
    path.write_text("\n".join(new_lines).rstrip("\n") + "\n", encoding="utf-8")
    return ToolSuccess(
        f'{_canonical_id(path)} · updated section "{section.strip()}" '
        f"({len(content_arg)} chars)"
    )


# --------------------------------------------------------------------------- #
# dispatch
# --------------------------------------------------------------------------- #
def task(
    project_ctx: ProjectContext,
    action: str,
    title: str | None = None,
    body: str | None = None,
    dependencies: str | None = None,
    branch: str | None = None,
    status: str | None = None,
    identifier: str | None = None,
    section: str | None = None,
    meta_only: bool = False,
    max_chars: int | None = None,
    offset: int | None = None,
    limit: int | None = None,
    content: str | None = None,
) -> ToolResult:
    """Dispatch a task action. See module docstring for the per-action contract."""
    act = (action or "").strip().lower()
    if act == "create":
        return _create(project_ctx, title, body, dependencies, branch, status)
    if act == "list":
        return _list(project_ctx, status, limit, offset)
    if act == "show":
        return _show(project_ctx, identifier, section, meta_only, max_chars, offset)
    if act == "status":
        return _status(project_ctx, identifier)
    if act == "update_status":
        return _update_status(project_ctx, identifier, status)
    if act == "update":
        return _update(project_ctx, identifier, section, content)
    return ToolError(
        f"Unknown action '{action}'. Valid: create, list, show, status, "
        "update_status, update",
        "validation",
    )
