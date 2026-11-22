"""A failed turn the callbacks could not show is shown by the turn consumer (plan step 4, R8).

``ChatLoop.run`` reports a failure through ``on_system_message``. When that
call raises, the loop keeps the outcome with ``reported`` False (step 3) and the
message is shown nowhere. The consumer now shows ``outcome.message`` once in that
case, and adds nothing when the callbacks already showed it. It reads the outcome
only after the turn's task returned normally: a task cancelled before it started
never reset a reused loop's previous outcome, so that outcome is not this turn's.

Kind: baseline regression unless a docstring says preservation. Environment:
local-faked (no network; the provider is a fake). Layer: tui, under
``App.run_test()`` with the real ``AyderApp``, ``ChatLoop`` and callbacks adapter.

The adapter's failure is a real Textual failure: ``ChatView.mount`` (Textual's)
raises its own ``MountError`` for the first system message, the way a widget
tree that cannot take a child does.
"""

from __future__ import annotations

import asyncio

import pytest
from textual.widget import MountError

from ayder_cli.providers import AIProvider, NormalizedStreamChunk
from ayder_cli.tui.app import AyderApp
from ayder_cli.tui.widgets import ChatView, _SubmitTextArea

_MESSAGE = "Error: boom"


class _FailingProvider(AIProvider):
    """Raises on the first chunk request, as a provider whose connection fails does."""

    def __init__(self, config=None):
        super().__init__(config)
        self.calls = 0

    async def chat(self, *args, **kwargs):
        return NormalizedStreamChunk()

    async def stream_with_tools(self, *args, **kwargs):
        self.calls += 1
        raise RuntimeError("boom")
        yield  # pragma: no cover - makes this an async generator


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _system_widgets(chat_view: ChatView, text: str) -> list:
    """The mounted system messages that show ``text``."""
    return [w for w in chat_view.children if "system" in w.classes and text in str(w.content)]


def _fail_the_first_system_mount(chat_view: ChatView) -> list[str]:
    """Make Textual's ``mount`` raise once, for the first system message. Returns a log."""
    log: list[str] = []
    real_mount = chat_view.mount

    def mount(*widgets, **kwargs):
        if not log and any("system" in w.classes for w in widgets):
            log.append("raised")
            raise MountError("the chat view cannot take a child")
        return real_mount(*widgets, **kwargs)

    chat_view.mount = mount  # type: ignore[method-assign]
    return log


async def _settle(app, pilot) -> None:
    for _ in range(300):
        await pilot.pause()
        if not app.is_turn_running and app._requests.empty():
            break
    await pilot.pause()
    await pilot.pause()


async def _submit_and_wait(app, pilot, text: str) -> None:
    box = app.query_one("#chat-input", _SubmitTextArea)
    box.focus()
    await pilot.pause()
    box.text = text
    await pilot.press("enter")
    await _settle(app, pilot)


@pytest.mark.anyio
async def test_a_failure_the_adapter_could_not_show_is_shown_once_by_the_consumer():
    """Baseline regression: after step 3 the message is shown nowhere.

    Driven by a real provider failure and a real Textual failure: ``mount`` raises for the first
    system message, so the adapter's ``on_system_message`` raises and the loop reports
    ``reported`` False. After: the consumer shows ``outcome.message`` once, without a second
    ``Error:`` prefix.
    """
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.chat_loop.llm = _FailingProvider()
        chat_view = app.query_one("#chat-view", ChatView)
        injected = _fail_the_first_system_mount(chat_view)

        await _submit_and_wait(app, pilot, "hello")

        assert injected == ["raised"]
        outcome = app.chat_loop.outcome
        assert outcome is not None
        assert (outcome.status, outcome.stage, outcome.reported) == ("failed", "llm", False)
        assert outcome.message == _MESSAGE
        assert len(_system_widgets(chat_view, _MESSAGE)) == 1
        assert not _system_widgets(chat_view, "Error: Error:")


@pytest.mark.anyio
async def test_a_failure_the_adapter_showed_appears_exactly_once():
    """Preservation: with ``reported`` True the consumer adds nothing.

    The adapter shows the failure itself, so one message is in the chat before and after.
    """
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.chat_loop.llm = _FailingProvider()
        chat_view = app.query_one("#chat-view", ChatView)

        await _submit_and_wait(app, pilot, "hello")

        outcome = app.chat_loop.outcome
        assert outcome is not None and outcome.reported is True
        assert len(_system_widgets(chat_view, _MESSAGE)) == 1


@pytest.mark.anyio
async def test_a_turn_cancelled_before_it_starts_shows_nothing_from_the_previous_outcome():
    """Preservation: the consumer reads the outcome only after a turn's task returned normally.

    The reused loop's first turn failed unreported, and its message was shown. The next turn's
    task is cancelled before ``run()`` executes its first statement, by a real
    ``request_turn(interrupt=True)`` that lands between the task's creation and its first step.
    The loop still holds the first turn's outcome, and the consumer shows nothing from it again.
    """
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        provider = _FailingProvider()
        app.chat_loop.llm = provider
        chat_view = app.query_one("#chat-view", ChatView)
        _fail_the_first_system_mount(chat_view)
        await _submit_and_wait(app, pilot, "first")
        first = app.chat_loop.outcome
        shown_after_first = len(_system_widgets(chat_view, _MESSAGE))

        def run_then_cancel_before_it_starts() -> bool:
            # Runs right before the consumer creates the turn's task; the callback lands before
            # that task's first step.
            asyncio.get_running_loop().call_soon(
                lambda: app.request_turn(run_loop=False, interrupt=True)
            )
            return True

        app.request_turn(run_loop=run_then_cancel_before_it_starts)
        await _settle(app, pilot)

        assert provider.calls == 1  # the second turn never reached the provider
        assert app.chat_loop.outcome is first  # run() never reset it: it is still the first turn's
        assert len(_system_widgets(chat_view, _MESSAGE)) == shown_after_first
