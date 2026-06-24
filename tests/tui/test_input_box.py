"""Behavioural tests for the chat input box (_SubmitTextArea / CLIInputBar).

Covers the two fixes on fix/tui-display-inputs:
  * Shift+Enter and Ctrl+J insert a newline (Enter still submits).
  * Up/Down navigate command history only at the true *visual* edge — so they
    walk soft-wrapped visual rows first, and only reach history at the first /
    last character. Previously the boundary used the document row, which is
    always 0 for a wrapped single-paragraph message, hijacking history mid-edit.

These run the real app through Textual's Pilot because the behaviour depends on
cursor geometry (wrapping, visual rows) that only exists once mounted.
"""

import pytest

from ayder_cli.tui.app import AyderApp
from ayder_cli.tui.widgets import CLIInputBar, _SubmitTextArea


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _seed_history(app, entries):
    """Give the input bar a deterministic history (avoids reading ~/.ayder_chat_history)."""
    bar = app.query_one("#input-bar", CLIInputBar)
    bar._history = list(entries)
    bar._history_index = len(bar._history)
    bar._current_input = ""
    return bar


@pytest.mark.anyio
async def test_shift_enter_and_ctrl_j_insert_newline():
    app = AyderApp(model="test")
    async with app.run_test() as pilot:
        ta = app.query_one("#chat-input", _SubmitTextArea)
        ta.focus()
        await pilot.pause()
        await pilot.press("h", "i")
        await pilot.press("shift+enter")
        await pilot.press("y", "o")
        await pilot.press("ctrl+j")
        await pilot.press("z")
        await pilot.pause()
        assert ta.text == "hi\nyo\nz"


@pytest.mark.anyio
async def test_up_moves_within_real_multiline_without_history():
    app = AyderApp(model="test")
    async with app.run_test() as pilot:
        _seed_history(app, ["older command"])
        ta = app.query_one("#chat-input", _SubmitTextArea)
        ta.focus()
        ta.text = "aaa\nbbb\nccc"
        ta.move_cursor((2, 1))
        await pilot.pause()
        await pilot.press("up")
        await pilot.pause()
        # cursor walked up one document line; text untouched (no history hijack)
        assert ta.text == "aaa\nbbb\nccc"
        assert ta.cursor_location[0] == 1


@pytest.mark.anyio
async def test_up_walks_soft_wrapped_visual_rows_without_history():
    app = AyderApp(model="test")
    async with app.run_test(size=(60, 24)) as pilot:
        _seed_history(app, ["older command"])
        ta = app.query_one("#chat-input", _SubmitTextArea)
        ta.focus()
        ta.text = "word " * 40  # one long logical line -> several visual rows
        ta.move_cursor((0, 200))
        await pilot.pause()
        await pilot.press("up")
        await pilot.pause()
        # Still the typed text (NOT replaced by history), cursor moved up a visual row.
        assert ta.text.startswith("word ")
        assert ta.cursor_location != (0, 200)


@pytest.mark.anyio
async def test_up_at_first_char_navigates_history():
    app = AyderApp(model="test")
    async with app.run_test() as pilot:
        _seed_history(app, ["older command"])
        ta = app.query_one("#chat-input", _SubmitTextArea)
        ta.focus()
        ta.text = "draft"
        ta.move_cursor((0, 0))
        await pilot.pause()
        await pilot.press("up")
        await pilot.pause()
        assert ta.text == "older command"


@pytest.mark.anyio
async def test_down_at_last_char_navigates_history_back_to_draft():
    app = AyderApp(model="test")
    async with app.run_test() as pilot:
        _seed_history(app, ["older command"])
        ta = app.query_one("#chat-input", _SubmitTextArea)
        ta.focus()
        ta.text = "draft"
        ta.move_cursor((0, 0))
        await pilot.pause()
        await pilot.press("up")  # -> "older command"
        await pilot.pause()
        ta.move_cursor(ta.document.end)  # last char
        await pilot.press("down")  # -> back to the in-progress draft
        await pilot.pause()
        assert ta.text == "draft"
