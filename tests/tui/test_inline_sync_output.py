"""Synchronized output (DEC mode 2026) in inline mode.

Textual 8.2.7 only enables it outside inline mode, although it already writes
each inline frame as one terminal sequence between _begin_update/_end_update.
AyderApp opts in for inline mode too, so a frame is applied by the terminal
atomically (an experiment judged live by the operator).
"""

import pytest
from textual import messages
from textual._ansi_sequences import SYNC_END, SYNC_START
from textual.drivers.headless_driver import HeadlessDriver

from ayder_cli.tui.app import AyderApp


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def inline_driver(monkeypatch):
    monkeypatch.setattr(HeadlessDriver, "is_inline", property(lambda self: True))


@pytest.mark.anyio
async def test_terminal_sync_support_is_enabled_in_inline_mode(inline_driver):
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert app.is_inline
        assert app._sync_available is False

        app.post_message(messages.TerminalSupportsSynchronizedOutput())
        await pilot.pause()

        assert app._sync_available is True


@pytest.mark.anyio
async def test_terminal_sync_support_is_still_enabled_outside_inline_mode():
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert not app.is_inline

        app.post_message(messages.TerminalSupportsSynchronizedOutput())
        await pilot.pause()

        assert app._sync_available is True


@pytest.mark.anyio
async def test_inline_frames_are_wrapped_in_sync_markers(inline_driver, monkeypatch):
    writes: list[str] = []
    monkeypatch.setattr(HeadlessDriver, "write", lambda self, data: writes.append(data))
    # App._display skips headless drivers; let it run so the real write path is used.
    monkeypatch.setattr(HeadlessDriver, "is_headless", property(lambda self: False))

    app = AyderApp(model="test")
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.post_message(messages.TerminalSupportsSynchronizedOutput())
        await pilot.pause()
        writes.clear()

        app.action_toggle_tools()
        await pilot.pause()
        await pilot.pause()

    starts = [i for i, data in enumerate(writes) if data == SYNC_START]
    assert starts, f"no frame was written: {writes!r}"
    for start in starts:
        frame = writes[start + 1]
        assert frame not in (SYNC_START, SYNC_END) and frame
        assert writes[start + 2] == SYNC_END
