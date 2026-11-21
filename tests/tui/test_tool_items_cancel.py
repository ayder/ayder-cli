"""A tool item that is still running when its turn is cancelled ends finished (plan step 16, R4b).

The chat's tool box says ``… running`` until a completion reaches it. A turn cancelled while its tool
runs finished nothing, so the box kept running forever (P1 F12e). Now the turn's end finishes it, and
a box keeps the first terminal state it was given: a later completion for the same box changes
nothing, so an ``Error…`` text can no longer turn an ``✓ ok`` box into an error box.

Kind: baseline regression unless a docstring says preservation. Environment: local-faked (no network;
the provider and the held registry are fakes). Layer: tui, under ``App.run_test()`` with the real
``AyderApp``, ``ChatLoop`` and callbacks adapter.

Every assertion is made after the UI queue has drained (R4d): the adapter completes a tool item
through ``call_later``.
"""

from __future__ import annotations

import pytest

from ayder_cli.core.result import ToolResultText
from ayder_cli.tui.app import AyderApp
from ayder_cli.tui.widgets import ChatView, ToolBox, _SubmitTextArea
from tests.loops.turn_fakes import HeldRegistry, ScriptedProvider, chunk, delta

_READ = '{"file_path": "a.py"}'


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


@pytest.mark.anyio
async def test_the_cancel_key_while_a_tool_runs_leaves_no_running_box():
    """Baseline regression, P1 F12e: the box stays ``… running`` today.

    Driven by Ctrl+C with nothing selected while a tool's worker is held. After the UI queue drains
    the box shows ``✗ interrupted`` or ``○ not run``, never ``✓ ok`` and never running.
    """
    app = AyderApp(model="test")
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        registry = HeldRegistry()
        app.chat_loop.llm = ScriptedProvider(
            [chunk(calls=[delta("c1", "read_file", _READ)])], [chunk(content="done")]
        )
        app.chat_loop.registry = registry
        box = app.query_one("#chat-input", _SubmitTextArea)
        box.focus()
        await pilot.pause()
        box.text = "go"
        await pilot.press("enter")
        for _ in range(300):
            await pilot.pause()
            if registry.entered.is_set():
                break
        assert registry.entered.is_set()

        await pilot.press("ctrl+c")
        await _drain(app, pilot)
        registry.release.set()

        (tool,) = app.query_one(ChatView).query(ToolBox)
        shown = str(tool.content)
        assert "… running" not in shown
        assert "✗ interrupted" in shown or "○ not run" in shown
        assert "✓ ok" not in shown


@pytest.mark.anyio
async def test_a_box_finished_ok_keeps_its_status_when_it_is_finished_again():
    """Baseline regression: a second finish turns the box into ``✗ error`` today."""
    app = AyderApp(model="test")
    async with app.run_test(size=(120, 40)) as pilot:
        chat = app.query_one(ChatView)
        chat.tool_started("c1", "read_file", {"file_path": "a.py"})
        chat.tool_completed("c1", ToolResultText("fine", "ok"))
        chat.tool_completed("c1", "Error: x")
        await pilot.pause()
        await pilot.pause()

        (tool,) = chat.query(ToolBox)
        assert "✓ ok" in str(tool.content)
        assert not tool.has_class("-error")


@pytest.mark.anyio
async def test_a_box_finished_ok_keeps_its_first_result_when_it_is_finished_again():
    """Baseline regression: the second finish replaces the result today."""
    app = AyderApp(model="test")
    async with app.run_test(size=(120, 40)) as pilot:
        chat = app.query_one(ChatView)
        chat.tool_started("c1", "read_file", {"file_path": "a.py"})
        chat.tool_completed("c1", ToolResultText("fine", "ok"))
        chat.tool_completed("c1", "Error: x")
        await pilot.pause()
        await pilot.pause()

        (tool,) = chat.query(ToolBox)
        assert tool.result == "fine"
