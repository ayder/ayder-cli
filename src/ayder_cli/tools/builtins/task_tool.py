"""Consolidated ``task(action=...)`` handler (spec 01).

One tool covers ``create | list | show | status | update_status | update |
update_dependencies``.
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

from ayder_cli.core.context import PathOutsideSandboxError, ProjectContext
from ayder_cli.core.result import ToolError, ToolResult, ToolSuccess

from .filesystem import _atomic_write, _path_lock
from .tasks import (
    _ensure_tasks_dir,
    _extract_id,
    _get_tasks_dir,
    _ID_LOCK,
    _next_id,
    _confined_task_files,
    _parse_status,
    _title_to_slug,
    ambiguous_task_ids,
    resolve_task_path,
)
from ayder_cli.log import get_logger

logger = get_logger("tool")

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


_DEPS_LINE = re.compile(r"(-\s+\*\*Dependencies:\*\*[ \t]+).*")


def _parse_deps(dependencies: str | None) -> list[int] | ToolError:
    """Parse ``"3, TASK-004 , 5"`` → ``[3, 4, 5]`` (duplicates dropped)."""
    ids: list[int] = []
    for raw in (dependencies or "").split(","):
        tok = raw.strip()
        if not tok:
            continue
        m = re.fullmatch(r"(?:TASK-)?0*(\d+)", tok, re.IGNORECASE)
        if m is None:
            return ToolError(
                f"Dependency '{tok}' is not a task ID (use 'TASK-003' or '3')",
                "validation",
            )
        if int(m.group(1)) not in ids:
            ids.append(int(m.group(1)))
    return ids


def _format_deps(ids: list[int]) -> str:
    return ", ".join(f"TASK-{i:03d}" for i in ids) if ids else "none"


def _dependency_graph(project_ctx: ProjectContext) -> dict[int, list[int]]:
    """Every task id mapped to the ids on its Dependencies line."""
    graph: dict[int, list[int]] = {}
    for path in _confined_task_files(_get_tasks_dir(project_ctx)):
        tid = _extract_id(path.name)
        if tid is None:
            continue
        m = _DEPS_LINE.search(path.read_text(encoding="utf-8"))
        line = m.group(0) if m else ""
        graph[tid] = [int(d) for d in re.findall(r"TASK-0*(\d+)", line, re.IGNORECASE)]
    return graph


def _check_deps(
    project_ctx: ProjectContext, task_id: int, deps: list[int]
) -> ToolError | None:
    """Reject a dependency on the task itself, on a missing task, or one that closes a cycle.

    Callers hold ``_ID_LOCK`` so the graph cannot change underneath the check.
    """
    if task_id in deps:
        return ToolError(f"TASK-{task_id:03d} cannot depend on itself", "validation")
    graph = _dependency_graph(project_ctx)
    missing = [d for d in deps if d not in graph]
    if missing:
        # Parallel creates are numbered in completion order, so a dependency
        # must already exist when the task that needs it is created.
        return ToolError(
            f"Unknown dependency {_format_deps(missing)}: create a task only after "
            "the tasks it depends on exist",
            "validation",
        )
    graph[task_id] = deps
    seen: set[int] = set()
    stack = list(deps)
    while stack:
        tid = stack.pop()
        if tid == task_id:
            return ToolError(
                f"These dependencies would make a cycle back to TASK-{task_id:03d}",
                "validation",
            )
        if tid not in seen:
            seen.add(tid)
            stack.extend(graph.get(tid, []))
    return None


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


def _not_found(project_ctx: ProjectContext, identifier: str) -> ToolError:
    """Name the matches of an ambiguous identifier; otherwise report not found."""
    ids = ambiguous_task_ids(project_ctx, identifier)
    if ids:
        return ToolError(
            f"Ambiguous task identifier '{identifier}': matches {', '.join(ids)}; use the ID",
            "validation",
        )
    return ToolError(f"Task not found: {identifier}", "not_found")


def _find_section(content: str, name: str):
    """Locate a heading ``name`` (level 2-6, case-insensitive).

    The H1 title is never a section, but it still ends one.

    Returns ``(start_line, end_line, level)`` spanning the heading through the
    line before the next heading of the same-or-shallower level, or ``None``.
    """
    lines = content.splitlines()
    target = name.strip().lower()
    for idx, line in enumerate(lines):
        m = re.match(r"^(#{2,6})\s+(.*?)\s*$", line)
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
    deps = _parse_deps(dependencies)
    if isinstance(deps, ToolError):
        return deps
    clean_body = _strip_caller_signature(body) if body else ""

    _ensure_tasks_dir(project_ctx)
    last_err: Exception | None = None
    # Hold the shared allocation lock across allocate-then-claim so concurrent
    # creates (worker threads) serialize and each gets a unique id. The per-file
    # O_EXCL is the second line of defense (leftover same-slug files).
    with _ID_LOCK:
        for _ in range(5):
            task_id = _next_id(project_ctx)
            invalid = _check_deps(project_ctx, task_id, deps)
            if invalid is not None:
                return invalid
            path = _get_tasks_dir(project_ctx) / f"TASK-{task_id:03d}-{slug}.md"
            try:
                with open(path, "x", encoding="utf-8") as fh:  # O_EXCL: atomic claim
                    fh.write(
                        _render_task(task_id, title, st, br, _format_deps(deps), clean_body)
                    )
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
    for path in _confined_task_files(_get_tasks_dir(project_ctx)):
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
        return _not_found(project_ctx, identifier)
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - tool boundary: any task-file read failure becomes a ToolError  # pragma: no cover
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
        return _not_found(project_ctx, identifier)
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
        return _not_found(project_ctx, identifier)
    with _path_lock(path.resolve()):
        current = _parse_status(path)
        content = path.read_text(encoding="utf-8")
        new_content, n = re.subn(
            r"(-\s+\*\*Status:\*\*\s+).+", rf"\g<1>{target}", content, count=1
        )
        if n == 0:
            return ToolError("No Status line found in task file", "execution")
        _atomic_write(path, new_content)
    return ToolSuccess(f"{_canonical_id(path)}: {current} → {target}")


def _update_dependencies(
    project_ctx: ProjectContext, identifier: str | None, dependencies: str | None
) -> ToolResult:
    if not identifier:
        return ToolError(
            "identifier is required for action 'update_dependencies'", "validation"
        )
    deps = _parse_deps(dependencies)
    if isinstance(deps, ToolError):
        return deps
    path = resolve_task_path(project_ctx, identifier)
    task_id = _extract_id(path.name) if path is not None else None
    if path is None or task_id is None:
        return _not_found(project_ctx, identifier)
    with _ID_LOCK:
        invalid = _check_deps(project_ctx, task_id, deps)
        if invalid is not None:
            return invalid
        with _path_lock(path.resolve()):
            text = path.read_text(encoding="utf-8")
            new_text, n = _DEPS_LINE.subn(rf"\g<1>{_format_deps(deps)}", text, count=1)
            if n == 0:
                return ToolError("No Dependencies line found in task file", "execution")
            _atomic_write(path, new_text)
    return ToolSuccess(f"TASK-{task_id:03d} · dependencies: {_format_deps(deps)}")


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
        return _not_found(project_ctx, identifier)

    with _path_lock(path.resolve()):
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
        _atomic_write(path, "\n".join(new_lines).rstrip("\n") + "\n")
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
    try:
        _get_tasks_dir(project_ctx)  # refuse an unconfined dir for every action
        return _dispatch(
            project_ctx, action, title, body, dependencies, branch, status,
            identifier, section, meta_only, max_chars, offset, limit, content,
        )
    except PathOutsideSandboxError as exc:
        # An unconfined .ayder/tasks (e.g. a symlink leaving the project).
        return ToolError(f"Security Error: {exc}", "security")
    except ValueError as exc:
        return ToolError(f"Error: {exc}", "validation")


def _dispatch(
    project_ctx: ProjectContext,
    action: str,
    title: str | None,
    body: str | None,
    dependencies: str | None,
    branch: str | None,
    status: str | None,
    identifier: str | None,
    section: str | None,
    meta_only: bool,
    max_chars: int | None,
    offset: int | None,
    limit: int | None,
    content: str | None,
) -> ToolResult:
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
    if act == "update_dependencies":
        return _update_dependencies(project_ctx, identifier, dependencies)
    return ToolError(
        f"Unknown action '{action}'. Valid: create, list, show, status, "
        "update_status, update, update_dependencies",
        "validation",
    )
