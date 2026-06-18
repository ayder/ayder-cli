"""Regression tests for /clear and context-manager coordination."""

import json
from unittest.mock import MagicMock

from ayder_cli.core.context import ProjectContext


def _run_prepare_now(app: MagicMock) -> None:
    """Make app.request_turn run the deferred prepare synchronously.

    do_clear now enqueues its state mutation via request_turn(prepare=...);
    these regression tests assert the immediate effect, so run the prepare.
    """
    app.request_turn.side_effect = lambda prepare=None, **kw: prepare() if prepare else None


def test_do_clear_calls_context_manager_clear():
    from ayder_cli.tui.commands import do_clear

    app = MagicMock()
    _run_prepare_now(app)
    app.messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u"},
    ]
    app.context_manager = MagicMock()
    chat_view = MagicMock()

    do_clear(app, chat_view)

    app.context_manager.clear.assert_called_once()


def test_do_clear_writes_recovery_snapshot(tmp_path):
    """`/clear` must snapshot the live conversation to
    `latest-context-before-clear` BEFORE wiping so recovery is possible."""
    from ayder_cli.tui.commands import do_clear

    app = MagicMock()
    _run_prepare_now(app)
    app.registry.project_ctx = ProjectContext(tmp_path)
    app.context_manager = MagicMock()
    app.messages = [
        {"role": "system", "content": "You are Claude"},
        {"role": "user", "content": "doing work"},
        {"role": "assistant", "content": "in progress"},
    ]
    chat_view = MagicMock()

    do_clear(app, chat_view)

    recovery = tmp_path / ".ayder" / "context" / "latest-context-before-clear.json"
    assert recovery.exists()
    snapshot = json.loads(json.loads(recovery.read_text())["content"])
    assert snapshot["message_count"] == 3
    assert snapshot["messages"][1]["content"] == "doing work"
    # System message added to chat_view should mention the slot.
    sys_msg_calls = [
        c.args[0] for c in chat_view.add_system_message.call_args_list
    ]
    assert any("latest-context-before-clear" in m for m in sys_msg_calls)


def test_do_clear_continues_when_snapshot_fails(tmp_path):
    """Snapshot failure must NOT block the clear — chat history wipe and
    context-manager reset still happen."""
    from ayder_cli.tui.commands import do_clear

    app = MagicMock()
    _run_prepare_now(app)
    app.registry.project_ctx = None  # forces snapshot to no-op
    app.context_manager = MagicMock()
    app.messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u"},
    ]

    do_clear(app, MagicMock())

    # Wipe and reset still happened.
    assert app.messages == [{"role": "system", "content": "sys"}]
    app.context_manager.clear.assert_called_once()


def test_do_clear_preserves_system_message():
    from ayder_cli.tui.commands import do_clear

    app = MagicMock()
    _run_prepare_now(app)
    system_message = {"role": "system", "content": "sys"}
    app.messages = [system_message, {"role": "user", "content": "u"}]
    app.context_manager = MagicMock()

    do_clear(app, MagicMock())

    assert app.messages == [system_message]


def test_do_clear_handles_missing_context_manager():
    from ayder_cli.tui.commands import do_clear

    app = MagicMock(spec=["messages", "request_turn"])
    _run_prepare_now(app)
    app.messages = []

    do_clear(app, MagicMock())
