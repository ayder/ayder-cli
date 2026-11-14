"""ChatView keeps following the end through the REAL turn path.

Unlike the widget-level follow tests, these submit a message through the input
bar and let the real ChatLoop stream reasoning, a tool call and a Markdown reply
(fenced code block and table) from a fake provider into the app's callbacks. The
chat must hold the thinking, tool and reply items in order, and keep following
the end: a message added afterwards is at the end of the view. They also cover
the mouse wheel and PageUp a real user does at the end of the chat.
"""

import asyncio

import pytest
from textual import events

from ayder_cli.providers import AIProvider, NormalizedStreamChunk
from ayder_cli.providers.base import ToolCallDef
from ayder_cli.tui.app import AyderApp
from ayder_cli.tui.widgets import (
    AssistantReply,
    ChatView,
    ThinkingItem,
    ToolBox,
    _SubmitTextArea,
)

REPLY = """Here is the plan.

```python
def hello(name):
    print(f"hello {name}")
    return 42
```

| col a | col b | col c |
|-------|-------|-------|
| 1     | 2     | 3     |
| 4     | 5     | 6     |

Some trailing prose that makes the reply long enough to wrap across a few lines in
a narrow terminal window, so that the conversation overflows the chat view.
"""


class _FakeProvider(AIProvider):
    """Streams a few reasoning chunks, then the reply in small content chunks."""

    async def chat(self, *args, **kwargs):
        return NormalizedStreamChunk()

    async def stream_with_tools(self, *args, **kwargs):
        for i in range(6):
            yield NormalizedStreamChunk(reasoning=f"thinking step {i}\n")
        for i in range(0, len(REPLY), 40):
            yield NormalizedStreamChunk(content=REPLY[i : i + 40])
            await asyncio.sleep(0)


class _ToolProvider(AIProvider):
    """Reasons, lists a directory with a read-only tool, then answers."""

    def __init__(self, config=None):
        super().__init__(config)
        self.turn = 0

    async def chat(self, *args, **kwargs):
        return NormalizedStreamChunk()

    async def stream_with_tools(self, *args, **kwargs):
        self.turn += 1
        if self.turn == 1:
            yield NormalizedStreamChunk(reasoning="I should look around first.\n")
            yield NormalizedStreamChunk(
                tool_calls=[ToolCallDef("call_1", "file_explorer", '{"path": "."}')]
            )
        else:
            yield NormalizedStreamChunk(content="Here is what I found.")


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _submit_and_wait(app, pilot, text):
    box = app.query_one("#chat-input", _SubmitTextArea)
    box.focus()
    await pilot.pause()
    box.text = text
    await pilot.press("enter")
    for _ in range(300):
        await pilot.pause()
        if not app.is_turn_running and app._requests.empty():
            break
    await pilot.pause()
    await pilot.pause()


async def _conversation(app, pilot, turns=3):
    await pilot.pause()
    app.chat_loop.llm = _FakeProvider(config=None)
    for n in range(turns):
        await _submit_and_wait(app, pilot, f"question number {n}")
    chat_view = app.query_one("#chat-view", ChatView)
    assert chat_view.max_scroll_y > 0
    assert chat_view.scroll_y == chat_view.max_scroll_y
    return chat_view


async def _still_following(pilot, chat_view):
    """A message added now is at the end of the view."""
    chat_view.add_system_message("one more message at the end")
    await pilot.pause()
    await pilot.pause()
    assert chat_view.scroll_y == chat_view.max_scroll_y


def _wheel(chat_view, direction):
    cls = events.MouseScrollUp if direction == "up" else events.MouseScrollDown
    event = cls(chat_view, 5, 5, 0, 0, 0, False, False, False)
    handler = chat_view._on_mouse_scroll_up if direction == "up" else chat_view._on_mouse_scroll_down
    handler(event)


@pytest.mark.anyio
async def test_real_turns_leave_thinking_then_reply_in_the_chat_and_it_keeps_following():
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 30)) as pilot:
        chat_view = await _conversation(app, pilot, turns=3)

        items = [
            type(child).__name__
            for child in chat_view.children
            if isinstance(child, (ThinkingItem, ToolBox, AssistantReply))
        ]
        assert items == ["ThinkingItem", "AssistantReply"] * 3
        assert not any(w.display for w in app.query("#tool-panel, #thinking-panel, #agent-panel"))

        await _still_following(pilot, chat_view)


@pytest.mark.anyio
async def test_a_real_tool_call_leaves_a_tool_box_between_thinking_and_the_reply():
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.chat_loop.llm = _ToolProvider()

        await _submit_and_wait(app, pilot, "what is in this directory?")

        chat_view = app.query_one("#chat-view", ChatView)
        items = [
            child
            for child in chat_view.children
            if isinstance(child, (ThinkingItem, ToolBox, AssistantReply))
        ]
        assert [type(i).__name__ for i in items] == ["ThinkingItem", "ToolBox", "AssistantReply"]
        thinking, tool, reply = items
        assert "I should look around first." in str(thinking.content)
        assert str(tool.content).startswith("● file_explorer ✓ ok ")
        assert reply.source == "Here is what I found."


@pytest.mark.anyio
async def test_wheel_up_and_back_down_to_the_end_keeps_following():
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 30)) as pilot:
        chat_view = await _conversation(app, pilot)
        for _ in range(3):
            _wheel(chat_view, "up")
            await pilot.pause()
        assert chat_view.scroll_y < chat_view.max_scroll_y
        for _ in range(8):  # more notches than needed, as an inertial trackpad sends
            _wheel(chat_view, "down")
            await pilot.pause()
        await pilot.pause()

        await _still_following(pilot, chat_view)


async def _assert_scrolled_up_view_is_left_alone(pilot, chat_view):
    """The view left the end and keeps its offset when new content arrives."""
    assert chat_view.scroll_y < chat_view.max_scroll_y
    position = chat_view.scroll_y

    chat_view.add_system_message("arrives while the user reads history")
    await pilot.pause()
    await pilot.pause()
    assert chat_view.scroll_y == position


@pytest.mark.anyio
async def test_page_up_from_the_end_leaves_the_end_and_stays_there():
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 30)) as pilot:
        chat_view = await _conversation(app, pilot)
        app.query_one("#chat-input", _SubmitTextArea).focus()
        await pilot.pause()

        await pilot.press("pageup")
        await pilot.pause()
        await pilot.pause()

        await _assert_scrolled_up_view_is_left_alone(pilot, chat_view)


@pytest.mark.anyio
async def test_wheel_up_from_the_end_leaves_the_end_and_stays_there():
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 30)) as pilot:
        chat_view = await _conversation(app, pilot)

        _wheel(chat_view, "up")
        await pilot.pause()
        await pilot.pause()

        await _assert_scrolled_up_view_is_left_alone(pilot, chat_view)


@pytest.mark.anyio
async def test_activity_timer_is_stopped_when_a_real_turn_ends():
    """The 10 fps spinner timer used to outlive every turn: the stop check ran
    before the activity state was cleared, so the timer kept ticking."""
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.chat_loop.llm = _FakeProvider(config=None)

        await _submit_and_wait(app, pilot, "one question")

        assert app._activity_timer is None
