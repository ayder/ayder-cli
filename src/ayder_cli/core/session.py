"""Save and restore TUI chat sessions under .ayder/sessions/.

A session file stores the conversation verbatim (including the system prompt
and all tool calls/results) plus the settings needed to resume it without any
CLI flags. Ids are short `xxxx-xxxx` hex strings; resume matches by exact id or
unique prefix.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


class SessionError(Exception):
    """Base error for session save/load problems."""


class SessionNotFound(SessionError):
    """No saved session matches the given id or prefix."""


class SessionAmbiguous(SessionError):
    """More than one saved session matches the given prefix."""


@dataclass(frozen=True)
class SessionData:
    session_id: str
    messages: list[dict]
    model: str | None
    agent_mode: bool
    safe_mode: bool
    permissions: set[str]
    created_at: str
    updated_at: str
    path: Path


def sessions_dir(root: Path | None = None) -> Path:
    """Return <root>/.ayder/sessions (root defaults to cwd)."""
    base = root if root is not None else Path.cwd()
    return base / ".ayder" / "sessions"


def new_session_id(root: Path | None = None) -> str:
    """Generate a collision-free 'xxxx-xxxx' id within the sessions dir."""
    directory = sessions_dir(root)
    while True:
        raw = uuid.uuid4().hex[:8]
        sid = f"{raw[:4]}-{raw[4:]}"
        if not (directory / f"{sid}.json").exists():
            return sid


def list_sessions(root: Path | None = None) -> list[str]:
    """Return saved session ids (filename stems), sorted."""
    directory = sessions_dir(root)
    if not directory.is_dir():
        return []
    return sorted(p.stem for p in directory.glob("*.json"))


def save_session(
    messages: list[dict],
    *,
    root: Path | None = None,
    session_id: str | None = None,
    model: str | None = None,
    agent_mode: bool = False,
    safe_mode: bool = False,
    permissions: set[str] | None = None,
) -> str:
    """Write *messages* + settings to .ayder/sessions/<id>.json; return the id.

    Reusing an existing *session_id* updates that file in place, preserving its
    original ``created_at`` and bumping ``updated_at``.
    """
    directory = sessions_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    if session_id is None:
        session_id = new_session_id(root)
    path = directory / f"{session_id}.json"

    now = datetime.now().isoformat()
    created_at = now
    if path.exists():
        try:
            created_at = json.loads(path.read_text(encoding="utf-8")).get(
                "created_at", now
            )
        except (OSError, json.JSONDecodeError):
            created_at = now

    base = root if root is not None else Path.cwd()
    payload = {
        "schema_version": 1,
        "session_id": session_id,
        "created_at": created_at,
        "updated_at": now,
        "model": model,
        "agent_mode": bool(agent_mode),
        "safe_mode": bool(safe_mode),
        "permissions": sorted(permissions) if permissions else [],
        "cwd": str(base.resolve()),
        "message_count": len(messages),
        "messages": messages,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return session_id


def resolve_session_id(token: str, root: Path | None = None) -> str:
    """Resolve *token* to a full session id by exact match or unique prefix.

    Matching ignores dashes and case. Raises SessionNotFound / SessionAmbiguous.
    """
    norm = token.strip().lower().replace("-", "")
    ids = list_sessions(root)
    for sid in ids:
        if sid.lower().replace("-", "") == norm:
            return sid
    matches = [sid for sid in ids if sid.lower().replace("-", "").startswith(norm)]
    if len(matches) == 1:
        return matches[0]
    available = ", ".join(ids) if ids else "(none)"
    if not matches:
        raise SessionNotFound(
            f"no session matching '{token}'. Available: {available}"
        )
    raise SessionAmbiguous(
        f"'{token}' matches multiple sessions: {', '.join(matches)}"
    )


def load_session(token: str, root: Path | None = None) -> SessionData:
    """Resolve *token* and load the session file into a SessionData."""
    sid = resolve_session_id(token, root)
    path = sessions_dir(root) / f"{sid}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SessionError(f"could not read session {sid}: {exc}") from exc
    return SessionData(
        session_id=data.get("session_id", sid),
        messages=data.get("messages", []),
        model=data.get("model"),
        agent_mode=bool(data.get("agent_mode", False)),
        safe_mode=bool(data.get("safe_mode", False)),
        permissions=set(data.get("permissions", [])),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
        path=path,
    )


def should_save_session(messages: list[dict]) -> bool:
    """True if the conversation has at least one user turn worth saving."""
    return any(m.get("role") == "user" for m in messages)


def resume_hint(session_id: str) -> str:
    """The exit message telling the user how to resume the saved session."""
    return f"Session saved. Resume with:\n  ayder --resume {session_id}"


def persist_and_announce(
    messages: list[dict],
    *,
    root: Path | None = None,
    session_id: str | None = None,
    model: str | None = None,
    agent_mode: bool = False,
    safe_mode: bool = False,
    permissions: set[str] | None = None,
    out=print,
) -> str | None:
    """Save the session on exit and print the resume hint.

    Returns the session id, or None when there is nothing worth saving.
    """
    if not should_save_session(messages):
        return None
    sid = save_session(
        messages,
        root=root,
        session_id=session_id,
        model=model,
        agent_mode=agent_mode,
        safe_mode=safe_mode,
        permissions=permissions,
    )
    out(resume_hint(sid))
    return sid


def messages_to_replay_items(messages: list[dict]) -> list[tuple[str, str]]:
    """Map saved messages to ('user'|'assistant', text) pairs for replay.

    Skips the system prompt, tool messages, and empty (tool-call-only) turns.
    """
    items: list[tuple[str, str]] = []
    for m in messages:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        content = m.get("content")
        if isinstance(content, str) and content.strip():
            items.append((role, content))
    return items
