"""Hook management — middleware and execution callbacks.

Extracted from tools/registry.py. Single responsibility: manage ordered lists
of middleware and pre/post execution callbacks, and invoke them safely.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

MiddlewareFunc = Callable[[str, Dict[str, Any]], None]
PreExecuteCallback = Callable[[str, Dict[str, Any]], None]


# ---------------------------------------------------------------------------
# Execution result DTO (shared by hooks and execution)
# ---------------------------------------------------------------------------


class ToolExecutionStatus(Enum):
    """Status of a tool execution, passed to post-execute callbacks."""

    STARTED = "started"
    SUCCESS = "success"
    ERROR = "error"


@dataclass
class ToolExecutionResult:
    """Result object passed to post-execute callbacks."""

    tool_name: str
    arguments: Dict[str, Any]
    status: ToolExecutionStatus
    result: Any = None
    error: Optional[str] = None
    duration_ms: Optional[float] = None


PostExecuteCallback = Callable[[ToolExecutionResult], None]


# ---------------------------------------------------------------------------
# HookManager
# ---------------------------------------------------------------------------


class HookManager:
    """Manages ordered lists of middleware and execution callbacks.

    All invocations are exception-safe: failures are logged as warnings
    and do not interrupt the execution pipeline.

    PermissionError from middleware is re-raised (it is an intentional gate).
    """

    def __init__(self) -> None:
        self._middlewares: List[MiddlewareFunc] = []
        self._pre_callbacks: List[PreExecuteCallback] = []
        self._post_callbacks: List[PostExecuteCallback] = []

    # -- Registration --------------------------------------------------------

    def add_middleware(self, mw: MiddlewareFunc) -> None:
        self._middlewares.append(mw)

    def remove_middleware(self, mw: MiddlewareFunc) -> None:
        if mw in self._middlewares:
            self._middlewares.remove(mw)

    def clear_middlewares(self) -> None:
        self._middlewares.clear()

    def get_middlewares(self) -> List[MiddlewareFunc]:
        return self._middlewares.copy()

    def add_pre_callback(self, cb: PreExecuteCallback) -> None:
        self._pre_callbacks.append(cb)

    def add_post_callback(self, cb: PostExecuteCallback) -> None:
        self._post_callbacks.append(cb)

    def remove_pre_callback(self, cb: PreExecuteCallback) -> None:
        if cb in self._pre_callbacks:
            self._pre_callbacks.remove(cb)

    def remove_post_callback(self, cb: PostExecuteCallback) -> None:
        if cb in self._post_callbacks:
            self._post_callbacks.remove(cb)

    # -- Invocation ----------------------------------------------------------

    def run_pre_callbacks(self, tool_name: str, args: dict) -> None:
        """Invoke all pre-execute callbacks. Failures are logged, not raised."""
        for cb in self._pre_callbacks:
            try:
                cb(tool_name, args)
            except Exception as e:
                logger.warning(f"Pre-execute callback failed for {tool_name}: {e}")

    def run_middlewares(self, tool_name: str, args: dict) -> None:
        """Invoke all middlewares. PermissionError is re-raised; others are logged."""
        for mw in self._middlewares:
            try:
                mw(tool_name, args)
            except PermissionError:
                raise
            except Exception as e:
                logger.warning(f"Middleware failed for {tool_name}: {e}")

    def run_post_callbacks(self, result: ToolExecutionResult) -> None:
        """Invoke all post-execute callbacks. Failures are logged, not raised."""
        for cb in self._post_callbacks:
            try:
                cb(result)
            except Exception as e:
                logger.warning(
                    f"Post-execute callback failed for {result.tool_name}: {e}"
                )
