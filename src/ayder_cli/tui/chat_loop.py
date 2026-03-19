"""Backward-compatibility re-exports.

The canonical implementation has moved to ``ayder_cli.loops.chat_loop``.
These aliases ensure existing imports continue to work.
"""

from ayder_cli.loops.chat_loop import ChatLoop as TuiChatLoop
from ayder_cli.loops.chat_loop import ChatCallbacks as TuiCallbacks
from ayder_cli.loops.chat_loop import ChatLoopConfig as TuiLoopConfig

# Re-export module-level helpers that some tests or consumers may reference
from ayder_cli.loops.chat_loop import (  # noqa: F401
    _parse_arguments,
    _repair_truncated_json,
    _check_required_args,
    _unwrap_exec_result,
    _is_escalation_result,
)

__all__ = [
    "TuiChatLoop",
    "TuiCallbacks",
    "TuiLoopConfig",
    "_parse_arguments",
    "_repair_truncated_json",
    "_check_required_args",
    "_unwrap_exec_result",
    "_is_escalation_result",
]
