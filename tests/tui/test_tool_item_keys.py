"""Two calls with the same provider id show as two items (plan step 15, R9c).

The chat view keys its tool items by the call's id for the whole chat. A provider that restarts its
ids on every response, or sends a placeholder for a call that has no id, made a later call reuse an
earlier call's box: one box, overwritten. Now each call has one key that is unique in the chat
session, and every start and completion of its item uses it.

Kind: baseline regression unless a docstring says preservation. Environment: local-faked (no
network; the provider is a fake). Layer: tui, under ``App.run_test()`` with the real ``AyderApp``,
``ChatLoop`` and callbacks adapter.

Every assertion is made after the UI queue has drained (R4d): the adapter completes a tool item
through ``call_later``.
"""

from __future__ import annotations

import pytest

from ayder_cli.tui.app import AyderApp
from ayder_cli.tui.widgets import ChatView, ToolBox, _SubmitTextArea
from tests.loops.turn_fakes import RecordingRegistry, ScriptedProvider, chunk, delta

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


async def _run_turn(app, pilot, *responses) -> ChatView:
    """Submit one message; each reply makes the calls of one ``responses`` entry, then a text reply."""
    await pilot.pause()
    scripts = [[chunk(calls=list(calls))] for calls in responses] + [[chunk(content="done")]]
    app.chat_loop.llm = ScriptedProvider(*scripts)
    app.chat_loop.registry = RecordingRegistry()
    box = app.query_one("#chat-input", _SubmitTextArea)
    box.focus()
    await pilot.pause()
    box.text = "go"
    await pilot.press("enter")
    await _drain(app, pilot)
    return app.query_one(ChatView)


def _finished_boxes(chat: ChatView) -> list[ToolBox]:
    return [box for box in chat.query(ToolBox) if "✓ ok" in str(box.content)]


@pytest.mark.anyio
async def test_two_responses_that_each_send_the_placeholder_idx_0_show_two_items():
    """Baseline regression, spec \u00a78: the second ``idx_0`` reuses the first box, overwritten.

    Driven by the OpenAI shape for a call whose id the provider never sent: the placeholder
    ``idx_0``, in two consecutive responses. After: two boxes, both finished.
    """
    app = AyderApp(model="test")
    async with app.run_test(size=(120, 40)) as pilot:
        chat = await _run_turn(
            app,
            pilot,
            [delta("idx_0", "read_file", _READ, index=0)],
            [delta("idx_0", "read_file", _READ, index=0)],
        )

        assert len(list(chat.query(ToolBox))) == 2
        assert len(_finished_boxes(chat)) == 2


@pytest.mark.anyio
async def test_two_responses_that_each_send_call_0_show_two_items():
    """Baseline regression: native Ollama restarts its ids on every request (``ollama.py:268``).

    Two consecutive responses each send ``call_0``. Today the second reuses the first box. After:
    two boxes, both finished.
    """
    app = AyderApp(model="test")
    async with app.run_test(size=(120, 40)) as pilot:
        chat = await _run_turn(
            app,
            pilot,
            [delta("call_0", "read_file", _READ)],
            [delta("call_0", "read_file", _READ)],
        )

        assert len(list(chat.query(ToolBox))) == 2
        assert len(_finished_boxes(chat)) == 2


@pytest.mark.anyio
async def test_two_responses_with_different_ids_show_two_finished_items():
    """Preservation: ids that are unique in the session are their own keys, so nothing changes."""
    app = AyderApp(model="test")
    async with app.run_test(size=(120, 40)) as pilot:
        chat = await _run_turn(
            app,
            pilot,
            [delta("c1", "read_file", _READ)],
            [delta("c2", "read_file", _READ)],
        )

        assert len(list(chat.query(ToolBox))) == 2
        assert len(_finished_boxes(chat)) == 2
