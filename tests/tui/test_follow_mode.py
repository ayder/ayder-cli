"""ChatView follow mode: the chat stays pinned to its end while new content
arrives, until the user scrolls up, and re-pins when they return to the end.

These run the real app through Textual's Pilot because following is a property
of the mounted, laid-out widget (scroll offset vs. content height).
"""

import pytest

from ayder_cli.tui.app import AyderApp
from ayder_cli.tui.widgets import ChatView, _SubmitTextArea


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _settle(pilot):
    await pilot.pause()
    await pilot.pause()


async def _filled_app_chat(app, pilot, lines=80):
    await pilot.pause()
    chat_view = app.query_one("#chat-view", ChatView)
    for i in range(lines):
        chat_view.add_system_message(f"line {i}")
    await _settle(pilot)
    assert chat_view.max_scroll_y > 0
    assert chat_view.scroll_y == chat_view.max_scroll_y
    app.query_one("#chat-input", _SubmitTextArea).focus()
    await pilot.pause()
    return chat_view


@pytest.mark.anyio
async def test_follows_new_messages_by_default():
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 40)) as pilot:
        chat_view = await _filled_app_chat(app, pilot)
        chat_view.add_system_message("one more")
        await _settle(pilot)
        assert chat_view.scroll_y == chat_view.max_scroll_y


@pytest.mark.anyio
async def test_follows_a_streaming_message_as_it_grows():
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 40)) as pilot:
        chat_view = await _filled_app_chat(app, pilot)
        for i in range(30):
            chat_view.add_assistant_message(f"streamed paragraph {i}\n\n")
            if i % 5 == 4:
                await pilot.pause()
        await _settle(pilot)
        assert chat_view.scroll_y == chat_view.max_scroll_y


@pytest.mark.anyio
@pytest.mark.parametrize("key", ["pageup", "ctrl+pageup", "home"])
async def test_scrolling_up_stops_following(key):
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 40)) as pilot:
        chat_view = await _filled_app_chat(app, pilot)
        await pilot.press(key)
        await _settle(pilot)
        position = chat_view.scroll_y
        assert position < chat_view.max_scroll_y

        chat_view.add_system_message("arrives while reading history")
        await _settle(pilot)

        assert chat_view.scroll_y == position


@pytest.mark.anyio
async def test_end_key_resumes_following():
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 40)) as pilot:
        chat_view = await _filled_app_chat(app, pilot)
        await pilot.press("pageup")
        await _settle(pilot)
        assert chat_view.scroll_y < chat_view.max_scroll_y

        await pilot.press("end")
        await _settle(pilot)
        assert chat_view.scroll_y == chat_view.max_scroll_y

        chat_view.add_system_message("after End")
        await _settle(pilot)
        assert chat_view.scroll_y == chat_view.max_scroll_y


@pytest.mark.anyio
@pytest.mark.parametrize("key", ["pagedown", "ctrl+pagedown"])
async def test_scrolling_back_down_to_the_end_resumes_following(key):
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 40)) as pilot:
        chat_view = await _filled_app_chat(app, pilot)
        await pilot.press("pageup")
        await _settle(pilot)
        assert chat_view.scroll_y < chat_view.max_scroll_y

        for _ in range(200):
            if chat_view.scroll_y >= chat_view.max_scroll_y:
                break
            await pilot.press(key)
            await pilot.pause()
        assert chat_view.scroll_y == chat_view.max_scroll_y

        chat_view.add_system_message("after reaching the end")
        await _settle(pilot)
        assert chat_view.scroll_y == chat_view.max_scroll_y


@pytest.mark.anyio
async def test_scrolling_down_but_not_to_the_end_keeps_the_position():
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 40)) as pilot:
        chat_view = await _filled_app_chat(app, pilot)
        await pilot.press("home")
        await _settle(pilot)
        await pilot.press("pagedown")
        await _settle(pilot)
        position = chat_view.scroll_y
        assert 0 < position < chat_view.max_scroll_y

        chat_view.add_system_message("arrives mid-history")
        await _settle(pilot)

        assert chat_view.scroll_y == position


# Scrolling "down" while already at the end must not stop the chat following:
# the next content is still pinned to the end. Each case adds content AFTER the
# key, which is what a real stream does.


async def _assert_follows_new_content(chat_view, pilot):
    chat_view.add_system_message("arrives after the key")
    await _settle(pilot)
    assert chat_view.scroll_y == chat_view.max_scroll_y


@pytest.mark.anyio
@pytest.mark.parametrize("key", ["pagedown", "ctrl+pagedown"])
async def test_down_key_at_the_end_from_the_input_keeps_following(key):
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 40)) as pilot:
        chat_view = await _filled_app_chat(app, pilot)  # the input has focus

        await pilot.press(key)
        await _settle(pilot)

        await _assert_follows_new_content(chat_view, pilot)


@pytest.mark.anyio
@pytest.mark.parametrize("key", ["down", "pagedown"])
async def test_down_key_at_the_end_in_the_focused_chat_keeps_following(key):
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 40)) as pilot:
        chat_view = await _filled_app_chat(app, pilot)
        await pilot.click("#chat-view", offset=(5, 5))  # clicking focuses the chat
        await pilot.pause()
        assert app.focused is chat_view

        await pilot.press(key)
        await _settle(pilot)

        await _assert_follows_new_content(chat_view, pilot)


@pytest.mark.anyio
async def test_page_up_then_ten_page_downs_keeps_following():
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 40)) as pilot:
        chat_view = await _filled_app_chat(app, pilot)
        await pilot.press("pageup")
        await _settle(pilot)
        assert chat_view.scroll_y < chat_view.max_scroll_y

        for _ in range(10):  # more than needed to get back to the end
            await pilot.press("pagedown")
            await pilot.pause()
        await _settle(pilot)
        assert chat_view.scroll_y == chat_view.max_scroll_y

        await _assert_follows_new_content(chat_view, pilot)
