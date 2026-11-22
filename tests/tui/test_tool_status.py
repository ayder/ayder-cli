"""A tool item shows the status the loop reports, not one guessed from the text (plan step 12, R4a).

The chat's tool item used to show ``✗ error`` for a result that began with "Error" and ``✓ ok`` for
everything else. A denied call, a skipped call, and a ``ToolError`` with no "Error" prefix showed as
successes, and a successful MCP result whose text began with "Error" showed as a failure. Now a
completion that carries a status shows its label; a plain string keeps the text rule.

Kind: baseline regression unless a docstring says preservation. Environment: local-faked (no
network; the provider is a fake, the MCP session is a third-party fake at its interface). Layer:
tui, under ``App.run_test()`` with the real ``AyderApp``, ``ChatLoop`` and callbacks adapter.

Every assertion is made after the UI queue has drained (R4d): the adapter completes a tool item
through ``call_later``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.types import CallToolResult, TextContent

from ayder_cli.core.result import ToolError, ToolResultText, ToolSuccess
from ayder_cli.tools import mcp_client
from ayder_cli.tui.app import AyderApp
from ayder_cli.tui.types import ConfirmResult
from ayder_cli.tui.widgets import ChatView, ToolBox, _SubmitTextArea
from tests.loops.turn_fakes import RecordingRegistry, ScriptedProvider, chunk, delta

_READ = '{"file_path": "a.py"}'
_WRITE = '{"file_path": "a.py", "operation": "write", "content": "x"}'


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _drain(app, pilot) -> None:
    """Wait for the turn to end and for the UI queue to empty."""
    for _ in range(300):
        await pilot.pause()
        if not app.is_turn_running and app._requests.empty():
            break
    await app.workers.wait_for_complete()
    await pilot.pause()
    await pilot.pause()


async def _run_turn(app, pilot, calls, *, registry=None, answer: ConfirmResult | None = None):
    """Submit one message; the first reply makes ``calls``, the second is a text reply."""
    await pilot.pause()
    app.chat_loop.llm = ScriptedProvider([chunk(calls=calls)], [chunk(content="done")])
    app.chat_loop.registry = registry or RecordingRegistry()
    if answer is not None:
        app._request_confirmation = AsyncMock(return_value=answer)  # the dialog is not under test
    box = app.query_one("#chat-input", _SubmitTextArea)
    box.focus()
    await pilot.pause()
    box.text = "go"
    await pilot.press("enter")
    await _drain(app, pilot)
    return app.query_one(ChatView)


def _shows(chat: ChatView, call_index: int = 0) -> str:
    """What the ``call_index``-th tool item in the chat shows."""
    return str(list(chat.query(ToolBox))[call_index].content)


# -- Results the loop knows the status of ---------------------------------------------------------


@pytest.mark.anyio
async def test_a_tool_error_without_an_error_prefix_shows_as_an_error():
    """Baseline regression, P8: ``ToolError("command is required")`` shows ``✓ ok`` today."""
    app = AyderApp(model="test")
    async with app.run_test(size=(120, 40)) as pilot:
        registry = RecordingRegistry(results={"read_file": ToolError("command is required")})
        chat = await _run_turn(app, pilot, [delta("c1", "read_file", _READ)], registry=registry)

        assert "✗ error" in _shows(chat)
        assert list(chat.query(ToolBox))[0].has_class("-error")


@pytest.mark.anyio
async def test_a_denied_call_shows_as_denied():
    """Baseline regression: "Tool call denied by user." shows ``✓ ok`` today."""
    app = AyderApp(model="test")
    async with app.run_test(size=(120, 40)) as pilot:
        chat = await _run_turn(
            app, pilot, [delta("c1", "file_editor", _WRITE)], answer=ConfirmResult("deny")
        )

        assert "✗ denied" in _shows(chat)


@pytest.mark.anyio
async def test_an_instruct_answer_shows_its_call_as_denied():
    """Baseline regression: the instruct answer's text shows ``✓ ok`` today."""
    app = AyderApp(model="test")
    async with app.run_test(size=(120, 40)) as pilot:
        chat = await _run_turn(
            app,
            pilot,
            [delta("c1", "file_editor", _WRITE), delta("c2", "read_file", _READ)],
            answer=ConfirmResult("instruct", "do it another way"),
        )

        assert "✗ denied" in _shows(chat, 0)


@pytest.mark.anyio
async def test_the_call_after_an_instruct_answer_shows_as_skipped():
    """Baseline regression: "Tool call skipped." shows ``✓ ok`` today."""
    app = AyderApp(model="test")
    async with app.run_test(size=(120, 40)) as pilot:
        chat = await _run_turn(
            app,
            pilot,
            [delta("c1", "file_editor", _WRITE), delta("c2", "read_file", _READ)],
            answer=ConfirmResult("instruct", "do it another way"),
        )

        assert "○ skipped" in _shows(chat, 1)


@pytest.mark.anyio
async def test_an_mcp_result_that_begins_with_error_but_succeeded_shows_as_ok(
    tmp_path, probe_tool
):
    """Baseline regression: the text rule shows a successful MCP reply as ``✗ error`` today.

    The MCP client's handler is the production one; only the server's session is faked, replying
    successfully with text that begins with "Error".
    """
    probe_tool("mcp_lookup")  # the name an MCP server's tool gets, so the policy accepts the call
    client = mcp_client.MCPClient(tmp_path)
    try:
        session = MagicMock()
        session.call_tool = AsyncMock(
            return_value=CallToolResult(
                content=[TextContent(type="text", text="Error: this is the document's own text")],
                isError=False,
            )
        )
        client.sessions["docs"] = session
        handler = client.make_handler("docs", "lookup")

        class McpRegistry(RecordingRegistry):
            def execute(self, name, arguments):
                self.calls.append((name, dict(arguments)))
                return handler(**arguments)

        app = AyderApp(model="test")
        async with app.run_test(size=(120, 40)) as pilot:
            chat = await _run_turn(
                app, pilot, [delta("c1", "mcp_lookup", "{}")], registry=McpRegistry()
            )

            assert "✓ ok" in _shows(chat)
            assert not list(chat.query(ToolBox))[0].has_class("-error")
    finally:
        client.close()


# -- Each label ----------------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "label"),
    [
        pytest.param("ok", "✓ ok", id="ok"),
        pytest.param("error", "✗ error", id="error"),
        pytest.param("denied", "✗ denied", id="denied"),
        pytest.param("skipped", "○ skipped", id="skipped"),
        pytest.param("not_run", "○ not run", id="not-run"),
        pytest.param("interrupted", "✗ interrupted", id="interrupted"),
    ],
)
async def test_a_completion_with_a_status_shows_that_status(status, label):
    """Baseline regression: the chat ignores a status and applies its text rule (here, ``✓ ok``).

    The completion is delivered to the chat view exactly as the adapter delivers the loop's:
    the carrier object itself. The text is not an error, so only the status can say otherwise.
    """
    app = AyderApp(model="test")
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        chat = app.query_one(ChatView)
        chat.tool_started("c1", "read_file", {"file_path": "a.py"})
        chat.tool_completed("c1", ToolResultText("a plain line", status))
        await pilot.pause()
        await pilot.pause()

        assert label in _shows(chat)
        assert list(chat.query(ToolBox))[0].has_class("-error") == (status in ("error", "interrupted"))


# -- What does not change (preservation) ------------------------------------------------------------


@pytest.mark.anyio
async def test_a_tool_success_that_reads_like_a_skip_stays_ok():
    """Preservation: the text "Tool call skipped." is never read as a status.

    A ``ToolSuccess`` with that text shows ``✓ ok``, before and after.
    """
    app = AyderApp(model="test")
    async with app.run_test(size=(120, 40)) as pilot:
        registry = RecordingRegistry(results={"read_file": ToolSuccess("Tool call skipped.")})
        chat = await _run_turn(app, pilot, [delta("c1", "read_file", _READ)], registry=registry)

        assert "✓ ok" in _shows(chat)


@pytest.mark.anyio
async def test_a_plain_error_string_from_a_tool_that_returns_text_stays_an_error():
    """Preservation: a plain ``str`` has no status, so the text rule shows ``✗ error``.

    This is the agent tool's handler, which returns plain "Error: ..." strings.
    """
    app = AyderApp(model="test")
    async with app.run_test(size=(120, 40)) as pilot:
        registry = RecordingRegistry(results={"read_file": "Error: the agent failed"})
        chat = await _run_turn(app, pilot, [delta("c1", "read_file", _READ)], registry=registry)

        assert "✗ error" in _shows(chat)
