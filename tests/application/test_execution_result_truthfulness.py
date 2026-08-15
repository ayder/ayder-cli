"""`ExecutionResult.success` must describe the whole operation, not just policy."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from ayder_cli.application.execution_policy import (
    ExecutionPolicy,
    ExecutionResult,
    ToolRequest,
)
from ayder_cli.core.result import ToolError, ToolSuccess

ALL = {"r", "w", "x"}


def _run(raw, *, args=None, permissions=ALL, pre_approved=True):
    registry = MagicMock()
    registry.execute.return_value = raw
    return ExecutionPolicy(permissions).execute_with_registry(
        ToolRequest("read_file", args if args is not None else {"file_path": "x"}),
        registry,
        pre_approved=pre_approved,
    )


def test_tool_success_is_success_and_keeps_its_type():
    r = _run(ToolSuccess("file contents"))
    assert r.success is True
    assert r.error is None
    assert str(r.result) == "file contents"
    assert isinstance(r.result, ToolSuccess), "str() must not erase the type"


def test_tool_error_is_a_failure_and_carries_the_error():
    r = _run(ToolError("file not found", category="io"))
    assert r.success is False, "a tool that failed did not succeed"
    assert isinstance(r.error, ToolError)
    assert r.error.category == "io"
    assert str(r.error) == "file not found"


def test_validation_failure_is_a_failure_with_a_named_error():
    r = _run(ToolSuccess("never reached"), args={"bogus": 1})
    assert r.success is False
    assert type(r.error).__name__ == "ValidationError"


def test_permission_failure_is_a_failure():
    r = _run(ToolSuccess("never reached"), permissions=set(), pre_approved=False)
    assert r.success is False
    assert r.error is not None


def test_plain_string_result_still_works():
    """`registry.execute` is typed ToolResult, but tests and plugins pass str."""
    r = _run("plain output")
    assert r.success is True
    assert str(r.result) == "plain output"


# ---------------------------------------------------------------------------
# The TUI consumer of `success`: a failed shell shortcut must still reach the
# model. Construction pattern borrowed from tests/tui/test_turn_consumer.py.
# ---------------------------------------------------------------------------


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _FakeCallbacks:
    def __init__(self):
        self.events = []

    def on_tool_start(self, call_id, name, arguments):
        self.events.append(("start", name, arguments))

    def on_tool_complete(self, call_id, result):
        self.events.append(("complete", result))

    def on_tools_cleanup(self):
        self.events.append(("cleanup",))


def _shell_app():
    from ayder_cli.tui.app import AyderApp

    app = AyderApp.__new__(AyderApp)
    app._requests = asyncio.Queue()
    app._run_task = None
    app._agent_registry = None
    app.messages = []
    app._callbacks = _FakeCallbacks()
    app.registry = MagicMock()
    app.chat_loop = MagicMock()
    app.chat_loop.config.permissions = {"x"}
    app._request_confirmation = AsyncMock()

    chat = MagicMock()
    app.query_one = lambda selector, *args, **kwargs: chat
    app._test_chat = chat
    return app


@pytest.mark.anyio
async def test_failed_shell_shortcut_still_appends_its_output_to_history(monkeypatch):
    """A failing shell shortcut appends exactly one formatted context message."""
    app = _shell_app()
    failure = ToolError("bash: nope: command not found", category="shell")

    def _fail(self, request, registry, context=None, *, pre_approved=False):
        return ExecutionResult(success=False, was_confirmed=pre_approved, error=failure)

    monkeypatch.setattr(ExecutionPolicy, "execute_with_registry", _fail)

    proceed = await app._prepare_shell_shortcut("nope")

    assert proceed is False
    expected = "Shell command executed:\n$ nope\n\nResult:\nbash: nope: command not found"
    assert expected == app._format_shell_context_message("nope", str(failure))
    assert app.messages == [{"role": "user", "content": expected}]
    app._test_chat.add_system_message.assert_called_once_with(str(failure))
