"""Consolidated ``background_process(action=...)`` handler (spec 06).

One tool covers ``start | logs | stop | list | info`` for background processes,
delegating to the lifecycle handlers in ``process_manager.py`` and self-bounding
``logs`` so the chat-loop's generic tool-result truncation is never triggered
(the definition sets ``max_result_chars=0``).
"""

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError, ToolResult, ToolSuccess
from ayder_cli.process_manager import (
    ProcessManager,
    get_background_output,
    info_background_process,
    kill_background_process,
    list_background_processes,
    run_background_process,
)

_DEFAULT_LOG_TAIL = 10
_DEFAULT_LOG_CHARS = 4000
_MAX_LOG_CHARS = 8000


def _bounded(text: str, offset: int, max_chars: int) -> str:
    """Return ``text[offset:offset+max_chars]`` with a char-offset hint if cut."""
    offset = max(0, offset)
    chunk = text[offset : offset + max_chars]
    consumed = offset + len(chunk)
    if consumed < len(text):
        chunk += f"\n… {len(text) - consumed} more chars (use offset={consumed})"
    return chunk


def _start(
    project_ctx: ProjectContext,
    process_manager: ProcessManager,
    command: str | None,
) -> ToolResult:
    if not command or not command.strip():
        return ToolError("command is required for action 'start'", "validation")
    return run_background_process(process_manager, project_ctx, command)


def _logs(
    process_manager: ProcessManager,
    process_id: int | None,
    tail: int | None,
    max_chars: int | None,
    offset: int | None,
) -> ToolResult:
    if process_id is None:
        return ToolError("process_id is required for action 'logs'", "validation")
    eff_tail = _DEFAULT_LOG_TAIL if tail is None else int(tail)
    res = get_background_output(process_manager, int(process_id), tail=eff_tail)
    if isinstance(res, ToolError):
        return res
    cap = min(max_chars or _DEFAULT_LOG_CHARS, _MAX_LOG_CHARS)
    return ToolSuccess(_bounded(str(res), max(0, int(offset or 0)), cap))


def _stop(process_manager: ProcessManager, process_id: int | None) -> ToolResult:
    if process_id is None:
        return ToolError("process_id is required for action 'stop'", "validation")
    return kill_background_process(process_manager, int(process_id))


def _list(process_manager: ProcessManager) -> ToolResult:
    return list_background_processes(process_manager)


def _info(process_manager: ProcessManager, process_id: int | None) -> ToolResult:
    if process_id is None:
        return ToolError("process_id is required for action 'info'", "validation")
    return info_background_process(process_manager, int(process_id))


def background_process(
    project_ctx: ProjectContext,
    process_manager: ProcessManager,
    action: str,
    command: str | None = None,
    process_id: int | None = None,
    tail: int | None = None,
    max_chars: int | None = None,
    offset: int | None = None,
) -> ToolResult:
    """Dispatch a background-process action. See module docstring for the contract."""
    act = (action or "").strip().lower()
    if act == "start":
        return _start(project_ctx, process_manager, command)
    if act == "logs":
        return _logs(process_manager, process_id, tail, max_chars, offset)
    if act == "stop":
        return _stop(process_manager, process_id)
    if act == "list":
        return _list(process_manager)
    if act == "info":
        return _info(process_manager, process_id)
    return ToolError(
        f"Unknown action '{action}'. Valid: start, logs, stop, list, info",
        "validation",
    )
