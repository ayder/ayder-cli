"""Tests for /temporal TUI command handler."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ayder_cli.tui.commands import COMMAND_MAP, handle_temporal


def _make_app() -> SimpleNamespace:
    chat_loop = SimpleNamespace(config=SimpleNamespace(max_iterations=50))
    return SimpleNamespace(
        permissions={"r", "w"},
        chat_loop=chat_loop,
        run_worker=MagicMock(return_value=SimpleNamespace(is_finished=False, cancel=MagicMock())),
    )


def test_temporal_command_registered():
    assert "/temporal" in COMMAND_MAP


def test_handle_temporal_without_args_shows_usage_when_inactive():
    app = _make_app()
    chat_view = MagicMock()

    handle_temporal(app, "", chat_view)

    chat_view.add_system_message.assert_called_once()
    assert "No temporal queue active" in chat_view.add_system_message.call_args[0][0]


def test_handle_temporal_without_args_shows_current_queue_status():
    app = _make_app()
    app._temporal_queue_name = "dev-team"
    app._temporal_worker_task = SimpleNamespace(is_finished=False)
    chat_view = MagicMock()

    handle_temporal(app, "", chat_view)

    chat_view.add_system_message.assert_called_once_with(
        "Temporal queue: dev-team (running)"
    )


def test_handle_temporal_starts_new_worker_for_queue():
    app = _make_app()
    chat_view = MagicMock()

    with patch("ayder_cli.tui.commands.TemporalWorker", create=True) as _:
        # Patch at import target location in function
        with patch("ayder_cli.services.temporal_worker.TemporalWorker") as mock_worker_cls:
            mock_worker = MagicMock()
            mock_worker.run_async.return_value = object()
            mock_worker_cls.return_value = mock_worker

            handle_temporal(app, "qa-team", chat_view)

            mock_worker_cls.assert_called_once()
            app.run_worker.assert_called_once()
            assert app._temporal_queue_name == "qa-team"
            chat_view.add_system_message.assert_called_once()
            assert "runner started: qa-team" in chat_view.add_system_message.call_args[0][0]


def test_handle_temporal_switches_queue_stops_previous_worker():
    app = _make_app()
    old_worker = MagicMock()
    old_task = MagicMock(is_finished=False)
    app._temporal_worker_instance = old_worker
    app._temporal_worker_task = old_task
    chat_view = MagicMock()

    with patch("ayder_cli.services.temporal_worker.TemporalWorker") as mock_worker_cls:
        mock_worker = MagicMock()
        mock_worker.run_async.return_value = object()
        mock_worker_cls.return_value = mock_worker

        handle_temporal(app, "arch-team", chat_view)

        old_worker.stop.assert_called_once()
        old_task.cancel.assert_called_once()
        assert app._temporal_queue_name == "arch-team"
