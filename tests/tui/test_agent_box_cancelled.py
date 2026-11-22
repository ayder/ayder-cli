"""An agent run that was cancelled shows as cancelled, not failed (plan step 18, R8).

The agent box knew two outcomes: ``✓ done`` and ``✗ failed`` for every other status. A run the user
cancelled (``/agent cancel``) now settles ``cancelled``, and its box shows ``○ cancelled <secs>`` in
the warning colour, without the error class.

Kind: baseline regression unless a docstring says preservation. Environment: local-faked (no
network). Layer: tui, under ``App.run_test()`` with the real ``AyderApp`` chat view.
"""

from __future__ import annotations

import pytest

from ayder_cli.tui.app import AyderApp
from ayder_cli.tui.widgets import AgentBox, ChatView


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _finished_box(status: str, result: str) -> tuple[AgentBox, str]:
    """The agent box of one run settled with ``status``, and what it shows."""
    app = AyderApp(model="test")
    async with app.run_test(size=(120, 40)) as pilot:
        chat = app.query_one(ChatView)
        chat.agent_event(1, "coder", "tool_start", {"call_id": "c1"}, assignment="the task")
        chat.agent_completed(1, "coder", result, status)
        await pilot.pause()
        await pilot.pause()
        (box,) = chat.query(AgentBox)
        return box, str(box.content)


@pytest.mark.anyio
async def test_a_cancelled_run_shows_cancelled():
    """Baseline regression: every status that is not ``done`` shows ``✗ failed`` today."""
    _, shown = await _finished_box("cancelled", "Agent cancelled before finishing.")

    assert "○ cancelled" in shown


@pytest.mark.anyio
async def test_a_cancelled_run_does_not_carry_the_error_class():
    """Baseline regression: the box is styled as an error today."""
    box, _ = await _finished_box("cancelled", "Agent cancelled before finishing.")

    assert not box.has_class("-error")


@pytest.mark.anyio
async def test_a_failed_run_still_shows_failed():
    """Preservation: an ``error`` run keeps its label and error class."""
    box, shown = await _finished_box("error", "boom")

    assert "✗ failed" in shown and box.has_class("-error")


@pytest.mark.anyio
async def test_a_done_run_still_shows_done():
    """Preservation: a ``done`` run keeps its label and has no error class."""
    box, shown = await _finished_box("done", "all good")

    assert "✓ done" in shown and not box.has_class("-error")
