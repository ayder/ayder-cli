"""ChatView keeps following the end through the REAL turn path.

Unlike the widget-level follow tests, these submit a message through the input
bar and let the real ChatLoop stream reasoning and a Markdown reply (fenced code
block and table) from a fake provider into the app's callbacks, then check the
chat is still anchored when a panel opens. They also cover the keyboard and
mouse scrolling a real user does at the end of the chat.
"""

import asyncio

import pytest
from textual import events

from ayder_cli.providers import AIProvider, NormalizedStreamChunk
from ayder_cli.tui.app import AyderApp
from ayder_cli.tui.widgets import ChatView, _SubmitTextArea

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


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def inline_driver(monkeypatch):
    """Run the pilot the way the real app runs: inline."""
    from textual.drivers.headless_driver import HeadlessDriver

    monkeypatch.setattr(HeadlessDriver, "is_inline", property(lambda self: True))


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
    # A turn leaves the 10 fps activity timer running; it can fire after the DOM is
    # gone at teardown and raise NoMatches, so stop it once the turns are done.
    if app._activity_timer is not None:
        app._activity_timer.stop()
        app._activity_timer = None
    chat_view = app.query_one("#chat-view", ChatView)
    assert chat_view.max_scroll_y > 0
    assert chat_view.scroll_y == chat_view.max_scroll_y
    return chat_view


async def _open_thinking_panel_and_settle(app, pilot):
    app.action_toggle_thinking()
    await pilot.pause()
    await pilot.pause()


def _wheel(chat_view, direction):
    cls = events.MouseScrollUp if direction == "up" else events.MouseScrollDown
    event = cls(chat_view, 5, 5, 0, 0, 0, False, False, False)
    handler = chat_view._on_mouse_scroll_up if direction == "up" else chat_view._on_mouse_scroll_down
    handler(event)


@pytest.mark.anyio
async def test_chat_stays_anchored_through_real_turns_and_keeps_its_end_when_thinking_opens():
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 30)) as pilot:
        chat_view = await _conversation(app, pilot)
        assert chat_view.is_anchored
        assert not chat_view._anchor_released
        assert app.query_one("#thinking-panel")._buffer, "reasoning should have streamed in"

        await _open_thinking_panel_and_settle(app, pilot)

        assert chat_view.scroll_y == chat_view.max_scroll_y


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

        await _open_thinking_panel_and_settle(app, pilot)

        assert chat_view.scroll_y == chat_view.max_scroll_y


# Scrolling "down" while already at the end must not stop the chat following.


@pytest.mark.anyio
@pytest.mark.parametrize("key", ["pagedown", "ctrl+pagedown"])
async def test_scrolling_down_at_the_end_keeps_following(key):
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 30)) as pilot:
        chat_view = await _conversation(app, pilot)
        app.query_one("#chat-input", _SubmitTextArea).focus()
        await pilot.pause()

        await pilot.press(key)
        await pilot.pause()
        await pilot.pause()
        assert chat_view.scroll_y == chat_view.max_scroll_y

        await _open_thinking_panel_and_settle(app, pilot)

        assert chat_view.scroll_y == chat_view.max_scroll_y


@pytest.mark.anyio
async def test_down_arrow_in_the_focused_chat_at_the_end_keeps_following():
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 30)) as pilot:
        chat_view = await _conversation(app, pilot)
        await pilot.click("#chat-view", offset=(5, 5))  # clicking focuses the chat
        await pilot.pause()

        await pilot.press("down")
        await pilot.pause()
        await pilot.pause()

        await _open_thinking_panel_and_settle(app, pilot)

        assert chat_view.scroll_y == chat_view.max_scroll_y


async def _assert_scrolled_up_view_is_left_alone(app, pilot, chat_view):
    """The view left the end, stays released, and keeps its offset when new
    content arrives and when a panel opens."""
    assert chat_view.scroll_y < chat_view.max_scroll_y
    assert chat_view._anchor_released
    position = chat_view.scroll_y

    chat_view.add_system_message("arrives while the user reads history")
    await pilot.pause()
    await pilot.pause()
    assert chat_view.scroll_y == position
    assert chat_view._anchor_released

    await _open_thinking_panel_and_settle(app, pilot)
    assert chat_view.scroll_y == position
    assert chat_view._anchor_released


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

        await _assert_scrolled_up_view_is_left_alone(app, pilot, chat_view)


@pytest.mark.anyio
async def test_wheel_up_from_the_end_leaves_the_end_and_stays_there():
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 30)) as pilot:
        chat_view = await _conversation(app, pilot)

        _wheel(chat_view, "up")
        await pilot.pause()
        await pilot.pause()

        await _assert_scrolled_up_view_is_left_alone(app, pilot, chat_view)


def _newest_row_is_painted(chat_view):
    last = [child for child in chat_view.children if child.display][-1]
    return last.region.bottom == chat_view.region.bottom


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("panel_id", "action"),
    [
        ("thinking-panel", "action_toggle_thinking"),
        ("tool-panel", "action_toggle_tools"),
        ("agent-panel", "action_toggle_agents"),
    ],
)
async def test_newest_rows_stay_painted_through_open_close_open_cycles(panel_id, action):
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 30)) as pilot:
        chat_view = await _conversation(app, pilot)
        assert _newest_row_is_painted(chat_view)

        for cycle in range(1, 4):
            for step in ("open", "close"):
                getattr(app, action)()
                await pilot.pause()
                await pilot.pause()
                assert chat_view.scroll_y == chat_view.max_scroll_y
                assert _newest_row_is_painted(chat_view), f"cycle {cycle} {step}"

