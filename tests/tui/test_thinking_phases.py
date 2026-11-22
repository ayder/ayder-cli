"""A reopened thinking phase is closed by the stop that ends it (plan step 7, R5a).

Content, then late reasoning, then the end of the stream: the late reasoning opens a second
thinking item in the chat. It must be finished (not live) when the turn is over. Before step 7 the
doubled stop at the end of every stream closed it; now the stop for the reopened phase does.

Kind: preservation. Environment: local-faked (no network; the provider is a fake). Layer: tui,
under ``App.run_test()`` with the real ``AyderApp``, ``ChatLoop`` and callbacks adapter.
"""

from __future__ import annotations

import pytest

from ayder_cli.providers import AIProvider, NormalizedStreamChunk
from ayder_cli.tui.app import AyderApp
from ayder_cli.tui.widgets import ChatView, ThinkingItem, _SubmitTextArea


class _LateReasoningProvider(AIProvider):
    """Streams the answer, then a late thought, then ends."""

    async def chat(self, *args, **kwargs):
        return NormalizedStreamChunk()

    async def stream_with_tools(self, *args, **kwargs):
        yield NormalizedStreamChunk(content="Here is the answer.")
        yield NormalizedStreamChunk(reasoning="a late thought\n")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_content_then_late_reasoning_then_the_end_leaves_no_live_thinking_item():
    """Preservation: the reopened phase's item is finished after the turn. Passes before and after."""
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.chat_loop.llm = _LateReasoningProvider(config=None)

        box = app.query_one("#chat-input", _SubmitTextArea)
        box.focus()
        await pilot.pause()
        box.text = "question"
        await pilot.press("enter")
        for _ in range(300):
            await pilot.pause()
            if not app.is_turn_running and app._requests.empty():
                break
        await pilot.pause()
        await pilot.pause()

        chat_view = app.query_one("#chat-view", ChatView)
        items = [child for child in chat_view.children if isinstance(child, ThinkingItem)]
        assert len(items) == 1
        assert not items[0].live
        assert chat_view._thinking_item is None
