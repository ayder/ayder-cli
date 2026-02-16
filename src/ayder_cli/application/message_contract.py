"""Normalized message-access contract for CLI and TUI paths.

Provides safe accessor helpers that work with both dict messages and
provider/SDK message objects, preventing dict/object shape regressions
in checkpoint, compaction, and memory flows.
"""

from __future__ import annotations


def get_message_role(message: dict | object) -> str:
    """Return the role field from a message (dict or object).

    Returns:
        Role string, or "unknown" when truly absent.
    """
    if isinstance(message, dict):
        return str(message.get("role", "unknown"))
    role = getattr(message, "role", None)
    return str(role) if role is not None else "unknown"


def get_message_content(message: dict | object) -> str:
    """Return the content field from a message (dict or object).

    Returns:
        Content string, or "" when absent or None.
    """
    if isinstance(message, dict):
        content = message.get("content", "")
    else:
        content = getattr(message, "content", "")
    if content is None:
        return ""
    return str(content)


def get_message_tool_calls(message: dict | object) -> list:
    """Return the tool_calls list from a message (dict or object).

    Always returns a list. Returns empty list if tool_calls is absent or None.
    Handles both dict messages and provider object messages safely.

    Returns:
        List of tool call objects/dicts, or [] when absent.
    """
    if isinstance(message, dict):
        tool_calls = message.get("tool_calls")
        return tool_calls if isinstance(tool_calls, list) else []
    tool_calls = getattr(message, "tool_calls", None)
    return tool_calls if isinstance(tool_calls, list) else []


def to_message_dict(message: dict | object) -> dict[str, object]:
    """Convert a message (dict or object) to a plain dict.

    Preserves role, content, tool_calls, tool_call_id, and name fields
    when present. Skips fields that are None or absent.

    Returns:
        Plain dict suitable for appending to a messages list.
    """
    if isinstance(message, dict):
        return dict(message)

    result: dict[str, object] = {
        "role": get_message_role(message),
        "content": get_message_content(message),
    }

    tool_calls = get_message_tool_calls(message)
    if tool_calls:
        result["tool_calls"] = tool_calls

    for field in ("tool_call_id", "name"):
        value = getattr(message, field, None)
        if value is not None:
            result[field] = value

    return result
