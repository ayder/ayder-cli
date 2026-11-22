"""A cancelled turn retires its confirmation prompt (plan step 17, R14; E25, N7).

The confirmation dialog is modal. While it was open no cancel key reached the app: the dialog's
hidden instruction input held focus and Textual's modal stops the app's non-priority bindings. A
turn waiting on the dialog could not be cancelled, and a leading-``!`` command's prompt (asked while
the queue prepares the request, before any turn task exists) kept accepting approval after the user
pressed Ctrl+C. A prompt whose waiter was cancelled by other means was left on the screen stack.

Now the dialog follows the chat's Ctrl+C rule: selected text is copied, otherwise the app's cancel
action runs. When a waiter ends without an answer, ``_request_confirmation`` retires its own dialog
and no other screen: it is dismissed when it is the active screen, and marked retired when another
screen is above it (it dismisses itself once active again). A ``!`` prompt has no turn task, so
Ctrl+C rejects the prompt itself: its wait ends with no answer and the command is skipped. An answer
that arrived first is kept, and the first answer wins.

Kind: baseline regression unless a docstring says preservation. Environment: local-faked (no
network; the provider and the registries are fakes; nothing is executed). Layer: tui, under
``App.run_test()`` with the real ``AyderApp``, the real ``CLIConfirmScreen`` and real keypresses.
Textual is driven through its public API only.

Every assertion is made after the UI queue has drained (R4d).
"""

from __future__ import annotations

import asyncio

import pytest
from textual.screen import Screen
from textual.widgets import Input, Static

from ayder_cli.core.config import Config
from ayder_cli.loops.chat_loop import TurnOutcome
from ayder_cli.themes import get_theme
from ayder_cli.tui.app import AyderApp
from ayder_cli.tui.screens import CLIConfirmScreen
from ayder_cli.tui.theme_manager import ThemeManager
from ayder_cli.tui.types import MessageType
from ayder_cli.tui.widgets import ChatView, _SubmitTextArea
from tests.loops.turn_fakes import RecordingRegistry, ScriptedProvider, chunk, delta

_WRITE = '{"file_path": "a.py", "operation": "write", "content": "x"}'


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def themed_app(monkeypatch):
    """An ``AyderApp`` under the default theme, whose CSS hides the dialog's instruction input."""
    ThemeManager.reset_instance()
    ThemeManager(config=Config.model_validate({"ui": {"theme": "ayder-dark"}}))
    monkeypatch.setattr(AyderApp, "CSS", get_theme("ayder-dark").css)
    yield AyderApp(model="test")
    ThemeManager.reset_instance()


class _Overlay(Screen):
    """An unrelated screen, such as the command palette."""

    def compose(self):
        yield Static("unrelated screen")


# -- Helpers ---------------------------------------------------------------------------------------


async def _settle(app, pilot) -> None:
    """Let the app run until the queue has drained and the turn (if any) has ended."""
    for _ in range(60):
        await pilot.pause()
        if not app.is_turn_running and app._requests.empty():
            break
    await pilot.pause()
    await pilot.pause()


async def _pause(pilot, times: int = 4) -> None:
    for _ in range(times):
        await pilot.pause()


def _dialogs(app) -> list[CLIConfirmScreen]:
    return [screen for screen in app.screen_stack if isinstance(screen, CLIConfirmScreen)]


def _system_lines(app) -> list[str]:
    chat = app.query_one("#chat-view", ChatView)
    return [m["content"] for m in chat.messages if m["type"] == MessageType.SYSTEM]


async def _wait_for_the_dialog(app, pilot) -> CLIConfirmScreen:
    for _ in range(200):
        await pilot.pause()
        if isinstance(app.screen, CLIConfirmScreen):
            return app.screen
    raise AssertionError("the confirmation dialog never opened")


async def _a_turn_waits_on_the_dialog(app, pilot, registry: RecordingRegistry) -> CLIConfirmScreen:
    """Submit a message whose reply calls a tool that needs confirmation; return the open dialog."""
    await pilot.pause()
    app.chat_loop.llm = ScriptedProvider(
        [chunk(calls=[delta("c1", "file_editor", _WRITE)])], [chunk(content="done")]
    )
    app.chat_loop.registry = registry
    box = app.query_one("#chat-input", _SubmitTextArea)
    box.focus()
    await pilot.pause()
    box.text = "go"
    await pilot.press("enter")
    return await _wait_for_the_dialog(app, pilot)


async def _a_shell_prompt_is_open(app, pilot, registry: RecordingRegistry, second: list) -> CLIConfirmScreen:
    """Queue ``!ls`` and a second request behind it; return the prompt the first one opened.

    The shell command and its registry are fakes: ``registry`` records what would execute. An
    approved command starts an LLM turn, so the provider is a fake too: nothing leaves the process.
    """
    await pilot.pause()
    app.chat_loop.llm = ScriptedProvider([chunk(content="done")])
    app.registry = registry
    app._handle_shell_shortcut("!ls")
    app.request_turn(prepare=lambda: second.append(1), run_loop=False)
    return await _wait_for_the_dialog(app, pilot)


async def _end_what_is_left_open(app, pilot) -> None:
    """Close a dialog a test left open, so the app can shut down cleanly."""
    for dialog in _dialogs(app):
        if dialog is app.screen:
            dialog.dismiss(None)
    await _pause(pilot)


# -- A turn waiting on the dialog: Ctrl+C --------------------------------------------------------


@pytest.mark.anyio
async def test_ctrl_c_with_nothing_selected_retires_the_dialog_the_turn_waits_on(themed_app):
    """Baseline regression, E25: no cancel key reaches the turn while the dialog is open.

    Driven by a real Ctrl+C with nothing selected, while a turn waits on the dialog and a second
    request is queued. After: the dialog is gone.
    """
    app, registry, second = themed_app, RecordingRegistry(), []
    async with app.run_test(size=(120, 40)) as pilot:
        await _a_turn_waits_on_the_dialog(app, pilot, registry)
        app.request_turn(prepare=lambda: second.append(1), run_loop=False)

        await pilot.press("ctrl+c")
        await _settle(app, pilot)

        try:
            assert not _dialogs(app)
        finally:
            await _end_what_is_left_open(app, pilot)


@pytest.mark.anyio
async def test_ctrl_c_on_the_dialog_lets_the_queued_request_run(themed_app):
    """Baseline regression, E25: the turn keeps waiting today, so the queue behind it never runs."""
    app, registry, second = themed_app, RecordingRegistry(), []
    async with app.run_test(size=(120, 40)) as pilot:
        await _a_turn_waits_on_the_dialog(app, pilot, registry)
        app.request_turn(prepare=lambda: second.append(1), run_loop=False)

        await pilot.press("ctrl+c")
        await _settle(app, pilot)

        try:
            assert second == [1]
        finally:
            await _end_what_is_left_open(app, pilot)


@pytest.mark.anyio
async def test_the_call_the_user_never_approved_does_not_run(themed_app):
    """Preservation: the cancelled turn's call never executes (holds today, because nothing is
    approved; it guards the fix against an answer that approves)."""
    app, registry, second = themed_app, RecordingRegistry(), []
    async with app.run_test(size=(120, 40)) as pilot:
        await _a_turn_waits_on_the_dialog(app, pilot, registry)

        await pilot.press("ctrl+c")
        await _settle(app, pilot)

        try:
            assert registry.calls == []
        finally:
            await _end_what_is_left_open(app, pilot)


@pytest.mark.anyio
async def test_ctrl_c_with_dialog_text_selected_copies_it_and_the_turn_keeps_waiting(themed_app):
    """Preservation: the inherited copy binding. Holds today.

    A triple click selects the dialog's description. Ctrl+C copies it; nothing is cancelled.
    """
    app, registry = themed_app, RecordingRegistry()
    async with app.run_test(size=(120, 40)) as pilot:
        dialog = await _a_turn_waits_on_the_dialog(app, pilot, registry)
        await pilot.click(dialog.query(".description").first(), times=3)
        await _pause(pilot)
        selected = dialog.get_selected_text()
        assert selected, "the click selected nothing"

        await pilot.press("ctrl+c")
        await _pause(pilot)

        try:
            assert app.clipboard == selected
            assert app.screen is dialog and app.is_turn_running
            assert "Turn cancelled." not in _system_lines(app)
        finally:
            await _end_what_is_left_open(app, pilot)


@pytest.mark.anyio
async def test_ctrl_c_with_the_instruction_inputs_text_selected_copies_it_and_the_turn_keeps_waiting(
    themed_app,
):
    """Preservation: the same with the instruction input's own selection. Holds today."""
    app, registry = themed_app, RecordingRegistry()
    async with app.run_test(size=(120, 40)) as pilot:
        dialog = await _a_turn_waits_on_the_dialog(app, pilot, registry)
        box = dialog.query_one("#instruction-input", Input)
        box.display = True
        box.value = "keep this"
        box.focus()
        await _pause(pilot)
        box.select_all()
        await _pause(pilot)

        await pilot.press("ctrl+c")
        await _pause(pilot)

        try:
            assert app.clipboard == "keep this"
            assert app.screen is dialog and app.is_turn_running
            assert "Turn cancelled." not in _system_lines(app)
        finally:
            await _end_what_is_left_open(app, pilot)


# -- An unrelated screen above the dialog -------------------------------------------------------


@pytest.mark.anyio
async def test_an_unrelated_screen_above_the_dialog_stays_when_the_turn_is_cancelled(themed_app):
    """Preservation: the screen the user opened is not closed by the cancel. Holds today."""
    app, registry = themed_app, RecordingRegistry()
    async with app.run_test(size=(120, 40)) as pilot:
        await _a_turn_waits_on_the_dialog(app, pilot, registry)
        app.push_screen(_Overlay())
        await _pause(pilot)

        app.action_cancel()
        await _settle(app, pilot)

        try:
            assert isinstance(app.screen, _Overlay)
        finally:
            app.pop_screen()
            await _pause(pilot)  # a retired dialog dismisses itself once it is active again
            await _end_what_is_left_open(app, pilot)


@pytest.mark.anyio
async def test_no_dialog_is_left_once_the_screen_above_it_closes(themed_app):
    """Baseline regression, R14: the dialog is still on the stack today, answering nothing.

    The turn is cancelled (``action_cancel()`` called directly) while an unrelated screen is above
    the dialog. The dialog is marked retired, and dismisses itself when it is active again.
    """
    app, registry = themed_app, RecordingRegistry()
    async with app.run_test(size=(120, 40)) as pilot:
        await _a_turn_waits_on_the_dialog(app, pilot, registry)
        app.push_screen(_Overlay())
        await _pause(pilot)
        app.action_cancel()
        await _settle(app, pilot)

        app.pop_screen()
        await _pause(pilot)

        try:
            assert not _dialogs(app)
        finally:
            await _end_what_is_left_open(app, pilot)


# -- A leading-! command's prompt: no turn task exists ---------------------------------------


@pytest.mark.anyio
async def test_ctrl_c_on_a_shell_prompt_skips_the_command(themed_app):
    """Baseline regression, E25 (the prompt's other owner): nothing happens today.

    Driven by a queued ``!ls`` whose prompt is open, a second request behind it, and a real
    Ctrl+C with nothing selected. After: the prompt is retired and the command is skipped.
    """
    app, registry, second = themed_app, RecordingRegistry(), []
    async with app.run_test(size=(120, 40)) as pilot:
        await _a_shell_prompt_is_open(app, pilot, registry, second)

        await pilot.press("ctrl+c")
        await _settle(app, pilot)

        try:
            assert _system_lines(app).count("Shell command skipped.") == 1
        finally:
            await _end_what_is_left_open(app, pilot)


@pytest.mark.anyio
async def test_ctrl_c_on_a_shell_prompt_lets_the_queued_request_run(themed_app):
    """Baseline regression: the prompt keeps the queue waiting today."""
    app, registry, second = themed_app, RecordingRegistry(), []
    async with app.run_test(size=(120, 40)) as pilot:
        await _a_shell_prompt_is_open(app, pilot, registry, second)

        await pilot.press("ctrl+c")
        await _settle(app, pilot)

        try:
            assert second == [1]
        finally:
            await _end_what_is_left_open(app, pilot)


@pytest.mark.anyio
async def test_ctrl_c_on_a_shell_prompt_does_not_execute_the_command(themed_app):
    """Preservation: nothing executes (holds today, because the prompt just stays open)."""
    app, registry, second = themed_app, RecordingRegistry(), []
    async with app.run_test(size=(120, 40)) as pilot:
        await _a_shell_prompt_is_open(app, pilot, registry, second)

        await pilot.press("ctrl+c")
        await _settle(app, pilot)

        try:
            assert registry.calls == []
        finally:
            await _end_what_is_left_open(app, pilot)


@pytest.mark.anyio
async def test_ctrl_c_on_a_shell_prompt_adds_no_turn_cancelled_line(themed_app):
    """Preservation: no turn was cancelled, so none is announced (holds today, because nothing
    happens; it guards the fix against the bindings alone, which print the line and leave the
    prompt open)."""
    app, registry, second = themed_app, RecordingRegistry(), []
    async with app.run_test(size=(120, 40)) as pilot:
        await _a_shell_prompt_is_open(app, pilot, registry, second)

        await pilot.press("ctrl+c")
        await _settle(app, pilot)

        try:
            assert "Turn cancelled." not in _system_lines(app)
        finally:
            await _end_what_is_left_open(app, pilot)


# -- The same prompt with a screen above it ---------------------------------------------------------


async def _ctrl_c_on_a_screen_above_the_shell_prompt(app, pilot, registry, second) -> None:
    await _a_shell_prompt_is_open(app, pilot, registry, second)
    app.push_screen(_Overlay())
    await _pause(pilot)
    await pilot.press("ctrl+c")
    await _settle(app, pilot)


@pytest.mark.anyio
async def test_ctrl_c_on_a_screen_above_a_shell_prompt_skips_the_command_at_once(themed_app):
    """Baseline regression, P6: "Turn cancelled." appears today and the prompt keeps waiting.

    After: while the screen is still open, the command is skipped.
    """
    app, registry, second = themed_app, RecordingRegistry(), []
    async with app.run_test(size=(120, 40)) as pilot:
        await _ctrl_c_on_a_screen_above_the_shell_prompt(app, pilot, registry, second)

        try:
            assert isinstance(app.screen, _Overlay)
            assert _system_lines(app).count("Shell command skipped.") == 1
        finally:
            app.pop_screen()
            await _pause(pilot)  # a retired dialog dismisses itself once it is active again
            await _end_what_is_left_open(app, pilot)


@pytest.mark.anyio
async def test_ctrl_c_on_a_screen_above_a_shell_prompt_lets_the_queued_request_run(themed_app):
    """Baseline regression: the covered prompt keeps the queue waiting today."""
    app, registry, second = themed_app, RecordingRegistry(), []
    async with app.run_test(size=(120, 40)) as pilot:
        await _ctrl_c_on_a_screen_above_the_shell_prompt(app, pilot, registry, second)

        try:
            assert second == [1]
        finally:
            app.pop_screen()
            await _pause(pilot)  # a retired dialog dismisses itself once it is active again
            await _end_what_is_left_open(app, pilot)


@pytest.mark.anyio
async def test_ctrl_c_on_a_screen_above_a_shell_prompt_executes_nothing(themed_app):
    """Preservation: nothing executes (holds today)."""
    app, registry, second = themed_app, RecordingRegistry(), []
    async with app.run_test(size=(120, 40)) as pilot:
        await _ctrl_c_on_a_screen_above_the_shell_prompt(app, pilot, registry, second)

        try:
            assert registry.calls == []
        finally:
            app.pop_screen()
            await _pause(pilot)  # a retired dialog dismisses itself once it is active again
            await _end_what_is_left_open(app, pilot)


@pytest.mark.anyio
async def test_no_dialog_and_no_second_skip_message_remain_once_the_screen_above_the_prompt_closes(
    themed_app,
):
    """Baseline regression, P6: the prompt is still waiting after the screen closes today.

    After: the dialog dismisses itself when it is active again, and the skip was announced once.
    """
    app, registry, second = themed_app, RecordingRegistry(), []
    async with app.run_test(size=(120, 40)) as pilot:
        await _ctrl_c_on_a_screen_above_the_shell_prompt(app, pilot, registry, second)

        app.pop_screen()
        await _settle(app, pilot)

        try:
            assert not _dialogs(app)
            assert _system_lines(app).count("Shell command skipped.") == 1
        finally:
            await _end_what_is_left_open(app, pilot)


# -- Answered dialogs behave as today ---------------------------------------------------------------


@pytest.mark.anyio
async def test_enter_on_the_default_option_approves_the_shell_prompt(themed_app):
    """Preservation: the default option approves and the command runs once. Holds today."""
    app, registry, second = themed_app, RecordingRegistry(), []
    async with app.run_test(size=(120, 40)) as pilot:
        await _a_shell_prompt_is_open(app, pilot, registry, second)

        await pilot.press("enter")
        await _settle(app, pilot)

        assert [name for name, _ in registry.calls] == ["bash"]
        assert second == [1]


@pytest.mark.anyio
async def test_an_approval_that_arrived_before_the_cancel_still_runs_the_command_once(themed_app):
    """Preservation, probes P7 and P9: approval first, then the cancel action.

    The default option approves the prompt, and ``action_cancel`` is queued with ``call_soon``
    before the answer reaches the waiter. The dialog is already off the stack, so the answer
    stands: the command runs once, today and after.
    """
    app, registry, second = themed_app, RecordingRegistry(), []
    async with app.run_test(size=(120, 40)) as pilot:
        dialog = await _a_shell_prompt_is_open(app, pilot, registry, second)

        dialog._select_current()
        asyncio.get_running_loop().call_soon(app.action_cancel)
        await _settle(app, pilot)

        assert [name for name, _ in registry.calls] == ["bash"]


# -- Quitting with a dialog open ---------------------------------------------------------------------


@pytest.mark.anyio
async def test_quitting_with_a_dialog_open_still_lets_the_turn_and_the_consumer_end(themed_app):
    """Preservation: the app's shutdown cancels what is left, and nothing may swallow it.

    A turn waits on the dialog and the app exits. The screens are gone by then, so the waiter's
    cleanup finds none; it must not raise in place of the cancellation, or the turn would end
    normally, the consumer's own cancellation would be lost, and the process would hang at exit.
    The leftover tasks are cancelled the way ``asyncio.run`` does when it closes.
    """
    app, registry = themed_app, RecordingRegistry()
    async with app.run_test(size=(120, 40)) as pilot:
        await _a_turn_waits_on_the_dialog(app, pilot, registry)
        turn, consumer = app._run_task, app._engine_task
        app.exit()
        await _pause(pilot)

    for task in (turn, consumer):
        task.cancel()
    _, pending = await asyncio.wait({turn, consumer}, timeout=5)
    assert not pending
    # Done is not enough: a task that ended by an error, or that swallowed the cancellation and
    # returned, is done too. Each ended by the cancellation, and the turn says it was cancelled.
    assert {"turn": turn.cancelled(), "consumer": consumer.cancelled()} == {"turn": True, "consumer": True}
    assert app.chat_loop.outcome == TurnOutcome("cancelled")
