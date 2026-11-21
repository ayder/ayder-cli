"""A cancelled turn tells the user the partial reply was not saved (plan step 10, D2).

The receiver that displays the notice is the chat view: when the user cancels while the answer is
streaming, the chat shows "The partial reply above was not saved.". The cancel key is Ctrl+C with
nothing selected, which ``test_ctrl_c_cancels_when_nothing_is_selected`` pins. Ctrl+X in the
focused chat input runs the TextArea's cut and never reaches ``action_cancel``, so it is not used.

Kind: baseline regression. Environment: local-faked (no network; the provider is a fake). Layer:
tui, under ``App.run_test()`` with the real ``AyderApp``, ``ChatLoop`` and callbacks adapter.
"""

from __future__ import annotations

import asyncio

import pytest

from ayder_cli.providers import AIProvider, NormalizedStreamChunk
from ayder_cli.tui.app import AyderApp
from ayder_cli.tui.types import MessageType
from ayder_cli.tui.widgets import ChatView, _SubmitTextArea

NOTICE = "The partial reply above was not saved."


class _StreamsThenWaitsProvider(AIProvider):
    """Streams part of an answer, then waits until the turn is cancelled."""

    async def chat(self, *args, **kwargs):
        return NormalizedStreamChunk()

    async def stream_with_tools(self, *args, **kwargs):
        yield NormalizedStreamChunk(content="The first half of an answer, ")
        await asyncio.Event().wait()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_cancelling_while_the_answer_streams_shows_the_partial_reply_notice():
    """Baseline regression: nothing says so today. After: the chat view shows the notice.

    Driven by Ctrl+C with nothing selected while content streams (premises: the turn is cancelled
    and the shown content is in the chat).
    """
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.chat_loop.llm = _StreamsThenWaitsProvider(config=None)
        chat_view = app.query_one("#chat-view", ChatView)
        box = app.query_one("#chat-input", _SubmitTextArea)
        box.focus()
        await pilot.pause()
        box.text = "tell me something"
        await pilot.press("enter")
        for _ in range(300):
            await pilot.pause()
            if any(m["type"] == MessageType.ASSISTANT for m in chat_view.messages):
                break
        assert app.is_turn_running

        await pilot.press("ctrl+c")
        for _ in range(300):
            await pilot.pause()
            if not app.is_turn_running and app._requests.empty():
                break
        await pilot.pause()

        contents = [m["content"] for m in chat_view.messages if m["type"] == MessageType.SYSTEM]
        assert "Turn cancelled." in contents
        assert contents.count(NOTICE) == 1
