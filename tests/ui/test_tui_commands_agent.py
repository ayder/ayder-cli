"""Tests for /agent TUI command handler (no-args popup path)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from ayder_cli.tui.commands import COMMAND_MAP, handle_agent
from ayder_cli.tui.screens import AgentListScreen


def _make_registry(names):
    reg = MagicMock()
    reg.agents = {n: MagicMock() for n in names}
    reg.list_agents.return_value = [
        {"name": n, "description": "", "status": "idle", "running_count": 0}
        for n in names
    ]
    reg.get_status.return_value = "idle"
    reg.get_running_count.return_value = 0
    return reg


def _make_app(registry=None):
    input_widget = MagicMock()
    input_widget.text = ""
    input_widget.focus = MagicMock()

    def query_one(selector, *args, **kwargs):
        if selector == "#chat-input":
            return input_widget
        return MagicMock()

    app = SimpleNamespace(
        _agent_registry=registry,
        push_screen=MagicMock(),
        query_one=MagicMock(side_effect=query_one),
    )
    return app, input_widget


def test_agent_command_registered():
    assert "/agent" in COMMAND_MAP


def test_handle_agent_no_args_with_no_registry_warns():
    app, _input = _make_app(registry=None)
    chat_view = MagicMock()
    handle_agent(app, "", chat_view)
    chat_view.add_system_message.assert_called_once()
    msg = chat_view.add_system_message.call_args[0][0]
    assert "No agents configured" in msg
    app.push_screen.assert_not_called()


def test_handle_agent_no_args_pushes_agent_list_screen():
    reg = _make_registry(["reviewer", "planner"])
    app, _input = _make_app(registry=reg)
    chat_view = MagicMock()
    handle_agent(app, "", chat_view)
    app.push_screen.assert_called_once()
    screen, callback = app.push_screen.call_args[0]
    assert isinstance(screen, AgentListScreen)


def test_handle_agent_screen_selection_prefills_input():
    reg = _make_registry(["reviewer"])
    app, input_widget = _make_app(registry=reg)
    chat_view = MagicMock()
    handle_agent(app, "", chat_view)
    _screen, callback = app.push_screen.call_args[0]
    callback("reviewer")
    assert input_widget.text == "/agent reviewer "
    input_widget.focus.assert_called_once()


def test_handle_agent_screen_cancel_does_not_touch_input():
    reg = _make_registry(["reviewer"])
    app, input_widget = _make_app(registry=reg)
    chat_view = MagicMock()
    handle_agent(app, "", chat_view)
    _screen, callback = app.push_screen.call_args[0]
    callback(None)
    assert input_widget.text == ""
    input_widget.focus.assert_not_called()


def test_handle_agent_dispatch_path_unchanged():
    reg = _make_registry(["reviewer"])
    reg.dispatch.return_value = 7  # success path returns int run_id
    app, _input = _make_app(registry=reg)
    # Avoid AgentPanel/ActivityBar query failures by raising on those:
    app.query_one = MagicMock(side_effect=Exception("no widgets in test"))
    app._start_activity_timer = MagicMock()
    chat_view = MagicMock()

    handle_agent(app, "reviewer fix the parser bug", chat_view)
    reg.dispatch.assert_called_once_with("reviewer", "fix the parser bug")
    chat_view.add_system_message.assert_called()


def test_handle_agent_list_subcommand_unchanged():
    reg = _make_registry(["reviewer"])
    app, _input = _make_app(registry=reg)
    chat_view = MagicMock()
    handle_agent(app, "list", chat_view)
    chat_view.add_system_message.assert_called_once()
    msg = chat_view.add_system_message.call_args[0][0]
    assert "Configured agents" in msg
    assert "reviewer" in msg
