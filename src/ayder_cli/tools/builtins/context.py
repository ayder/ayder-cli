"""Unified session-context tool.

Replaces save_memory, load_memory, save_context_memory, and load_context_memory
with a single polymorphic tool dispatching on ``action``.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError, ToolSuccess

logger = logging.getLogger(__name__)


_VALID_ACTIONS = frozenset({"save", "load", "list", "stats", "clear"})
_SLOT_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")

# Recovery slot written automatically before every clear (both /clear and
# context(action="clear")) so the LLM/user can `context(action="load",
# name="latest-context-before-clear")` to inspect what was wiped.
RECOVERY_SLOT_NAME = "latest-context-before-clear"
_RECOVERY_MESSAGE_CAP = 50
_RECOVERY_CONTENT_CAP = 4000


def _get_context_dir(project_ctx: ProjectContext) -> Path:
    return project_ctx.root / ".ayder" / "context"


def _iso_dashed_timestamp() -> str:
    """Filesystem-safe ISO timestamp with microsecond precision."""
    return datetime.now().isoformat().replace(":", "-").replace(".", "-")


def _validate_slot_name(name: str | None) -> str | None:
    """Return None if the slot name is safe, otherwise an error message."""
    if not name:
        return "name must be a non-empty string"
    if not _SLOT_NAME_RE.match(name):
        return (
            "name must contain only letters, digits, '.', '_', '-' "
            "(no path separators or '..')"
        )
    if name in (".", "..") or name.startswith("."):
        return "name must not be '.', '..', or start with '.'"
    return None


def context(
    project_ctx: ProjectContext,
    action: str = "",
    name: str | None = None,
    content: str | None = None,
    overwrite: bool = False,
    keep_last_n: int = 0,
    context_manager: Any = None,
    app: Any = None,
) -> str:
    if not action:
        return ToolError("action is required", "validation")
    if action not in _VALID_ACTIONS:
        return ToolError(
            f"unknown action {action!r}; expected one of {sorted(_VALID_ACTIONS)}",
            "validation",
        )

    if action == "save":
        return _save(project_ctx, name, content, overwrite)
    if action == "load":
        return _load(project_ctx, name)
    if action == "list":
        return _list(project_ctx)
    if action == "stats":
        return _stats(project_ctx, context_manager)
    if action == "clear":
        return _clear(project_ctx, name, content, keep_last_n, app)

    return ToolError(f"unhandled action {action!r}", "execution")


def _save(
    project_ctx: ProjectContext,
    name: str | None,
    content: str | None,
    overwrite: bool,
) -> str:
    err = _validate_slot_name(name)
    if err:
        return ToolError(err, "validation")
    if content is None or content == "":
        return ToolError("content is required for save", "validation")

    ctx_dir = _get_context_dir(project_ctx)
    ctx_dir.mkdir(parents=True, exist_ok=True)

    target = ctx_dir / f"{name}.json"
    versioned_path: Path | None = None
    if target.exists() and not overwrite:
        versioned_path = ctx_dir / f"{name}.{_iso_dashed_timestamp()}.json"
        target.rename(versioned_path)

    payload = {
        "name": name,
        "content": content,
        "saved_at": datetime.now().isoformat(),
    }
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if versioned_path is not None:
        return ToolSuccess(f"Saved context to {target}; previous version: {versioned_path}")
    return ToolSuccess(f"Saved context to {target}")


def _load(project_ctx: ProjectContext, name: str | None) -> str:
    err = _validate_slot_name(name)
    if err:
        return ToolError(err, "validation")

    ctx_dir = _get_context_dir(project_ctx)
    target = ctx_dir / f"{name}.json"
    if target.exists():
        payload = json.loads(target.read_text(encoding="utf-8"))
        return ToolSuccess(payload.get("content", ""))

    available = _current_slot_names(ctx_dir)
    if not available:
        return ToolError(f"no saved contexts; cannot load {name!r}", "execution")
    return ToolError(
        f"context {name!r} not found; available: {', '.join(sorted(available))}",
        "execution",
    )


def _scan_context_dir(ctx_dir: Path) -> tuple[list[tuple[str, dict, Path]], list[Path]]:
    """Scan the context directory once.

    Returns a tuple of (current slots, unreadable files):
      - current slots: list of (name, payload, path) for every `<name>.json`
        whose embedded payload `name` field matches its filename.
      - unreadable files: paths to `<name>.json` files that exist but cannot
        be parsed. Versioned predecessor files are excluded from both lists.

    Each file is read at most once.
    """
    if not ctx_dir.exists():
        return [], []
    current: list[tuple[str, dict, Path]] = []
    unreadable: list[Path] = []
    for path in sorted(ctx_dir.iterdir()):
        if not path.is_file() or path.suffix != ".json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Unreadable context slot at %s: %s", path, exc)
            unreadable.append(path)
            continue
        name = payload.get("name")
        # Current slots have a payload `name` field that matches their filename.
        # Versioned predecessors (`<name>.<timestamp>.json`) fail this check
        # because their payload still records the original `<name>`, so they
        # are correctly excluded.
        if isinstance(name, str) and path.name == f"{name}.json":
            current.append((name, payload, path))
    return current, unreadable


def _current_slot_names(ctx_dir: Path) -> list[str]:
    """Return current non-versioned context slot names (compat shim)."""
    current, _ = _scan_context_dir(ctx_dir)
    return [name for name, _, _ in current]


def _list(project_ctx: ProjectContext) -> str:
    ctx_dir = _get_context_dir(project_ctx)
    current, unreadable = _scan_context_dir(ctx_dir)

    entries: list[dict[str, Any]] = []
    for name, payload, path in current:
        entries.append(
            {
                "name": name,
                "saved_at": payload.get("saved_at", ""),
                "size_bytes": path.stat().st_size,
            }
        )
    # Surface unreadable slots so the user can act on them instead of having
    # them silently dropped. The "unreadable" flag distinguishes from real slots.
    for path in unreadable:
        entries.append(
            {
                "name": path.stem,
                "saved_at": "",
                "size_bytes": path.stat().st_size,
                "unreadable": True,
            }
        )
    return ToolSuccess(json.dumps(entries, indent=2))


def _stats(project_ctx: ProjectContext, context_manager: Any) -> str:
    if context_manager is None:
        return ToolError(
            "stats requires an active context_manager (none injected)",
            "execution",
        )

    stats = context_manager.get_stats()

    cache_state = "n/a"
    cache_hit_ratio = None
    monitor = getattr(context_manager, "_cache_monitor", None)
    if monitor is not None:
        last = getattr(monitor, "last_status", None)
        if last is not None:
            cache_state = last.state
            cache_hit_ratio = last.hit_ratio

    payload = {
        "total_tokens": stats.total_tokens,
        "available_tokens": stats.available_tokens,
        "utilization_percent": stats.utilization_percent,
        "message_count": stats.message_count,
        "compaction_count": stats.compaction_count,
        "messages_compacted": stats.messages_compacted,
        "cache_state": cache_state,
        "cache_hit_ratio": cache_hit_ratio,
        "saved_contexts_count": len(_current_slot_names(_get_context_dir(project_ctx))),
    }
    return ToolSuccess(json.dumps(payload, indent=2))


def snapshot_conversation_for_clear(
    project_ctx: ProjectContext,
    app: Any,
) -> str | None:
    """Snapshot the current conversation to the recovery slot.

    Called by both ``do_clear`` (slash command) and ``_clear`` (tool action)
    BEFORE wiping ``app.messages``, so the user/LLM can recover what was
    cleared by loading slot ``latest-context-before-clear``.

    The snapshot caps total messages at the most recent
    ``_RECOVERY_MESSAGE_CAP`` and truncates any single message body over
    ``_RECOVERY_CONTENT_CAP`` chars. ``overwrite=True`` is used so the
    recovery slot reflects only the most recent clear — versioned
    predecessors would accumulate noise.

    Returns the slot name on success, ``None`` on failure (failure is
    non-fatal — the clear path continues regardless).
    """
    if app is None:
        return None
    messages = getattr(app, "messages", None)
    if not messages:
        return None

    trimmed = list(messages[-_RECOVERY_MESSAGE_CAP:])
    rendered = []
    for msg in trimmed:
        role = msg.get("role", "unknown")
        body = msg.get("content", "")
        if isinstance(body, str) and len(body) > _RECOVERY_CONTENT_CAP:
            body = (
                body[:_RECOVERY_CONTENT_CAP]
                + f"... [truncated from {len(body)} chars]"
            )
        rendered.append({"role": role, "content": body})

    snapshot = {
        "snapshot_time": datetime.now().isoformat(),
        "message_count": len(messages),
        "kept_count": len(trimmed),
        "messages": rendered,
        "note": (
            "Conversation snapshot taken automatically before a clear. "
            "Load with context(action='load', name='latest-context-before-clear') "
            "to inspect what was cleared."
        ),
    }

    try:
        result = _save(
            project_ctx,
            RECOVERY_SLOT_NAME,
            json.dumps(snapshot, indent=2),
            overwrite=True,
        )
    except Exception as exc:
        logger.warning("Recovery snapshot failed: %s", exc)
        return None
    if isinstance(result, ToolError):
        logger.warning("Recovery snapshot save returned error: %s", result)
        return None
    return RECOVERY_SLOT_NAME


def _clear(
    project_ctx: ProjectContext,
    name: str | None,
    content: str | None,
    keep_last_n: int,
    app: Any,
) -> str:
    if content is None or content == "":
        return ToolError("content (summary text) is required for clear", "validation")
    if app is None:
        return ToolError(
            "clear requires a running TUI session (no app handle)",
            "execution",
        )

    slot_name = name or f"auto-compact-{_iso_dashed_timestamp()}"
    save_result = _save(project_ctx, slot_name, content, overwrite=False)
    if isinstance(save_result, ToolError):
        return save_result

    # Auto-snapshot the live conversation BEFORE the deferred wipe runs so
    # the LLM can recover by loading `latest-context-before-clear` after the
    # next iteration. Failure here is non-fatal — the clear still proceeds.
    recovery_slot = snapshot_conversation_for_clear(project_ctx, app)

    kept = max(0, int(keep_last_n))
    messages_before = len(getattr(app, "messages", []))
    app._pending_compact = {
        "summary_name": slot_name,
        "summary_content": content,
        "keep_last_n": kept,
    }

    payload = {
        "messages_before": messages_before,
        "kept_last_n": kept,
        "saved_as": slot_name,
        "recovery_slot": recovery_slot,
        "status": "pending - will be applied at next chat-loop iteration",
    }
    return ToolSuccess(json.dumps(payload, indent=2))
