"""Tests for CliCallbacks — TuiCallbacks adapter for the terminal."""

import asyncio

from ayder_cli.cli_callbacks import CliCallbacks, CliConfirmResult


class TestCliCallbacksProtocol:
    """CliCallbacks must satisfy the TuiCallbacks runtime-checkable protocol."""

    def test_isinstance_tui_callbacks(self):
        from ayder_cli.tui.chat_loop import TuiCallbacks

        cb = CliCallbacks()
        assert isinstance(cb, TuiCallbacks)

    def test_all_protocol_methods_present(self):
        """Every method in TuiCallbacks protocol must exist on CliCallbacks."""
        from ayder_cli.tui.chat_loop import TuiCallbacks
        import inspect

        protocol_methods = {
            name
            for name, _ in inspect.getmembers(TuiCallbacks, predicate=inspect.isfunction)
            if not name.startswith("_")
        }
        cb_methods = {
            name
            for name, _ in inspect.getmembers(CliCallbacks, predicate=inspect.isfunction)
            if not name.startswith("_")
        }
        missing = protocol_methods - cb_methods
        assert not missing, f"CliCallbacks missing protocol methods: {missing}"


class TestCliCallbacksOutput:
    """Verify each callback produces expected stdout/stderr output."""

    def test_on_assistant_content_prints_to_stdout(self, capsys):
        cb = CliCallbacks()
        cb.on_assistant_content("Hello world")
        captured = capsys.readouterr()
        assert captured.out.strip() == "Hello world"

    def test_on_system_message_prints_to_stderr(self, capsys):
        cb = CliCallbacks()
        cb.on_system_message("Warning: something happened")
        captured = capsys.readouterr()
        assert "Warning: something happened" in captured.err

    def test_on_tool_start_verbose(self, capsys):
        cb = CliCallbacks(verbose=True)
        cb.on_tool_start("id-1", "read_file", {"file_path": "a.py"})
        captured = capsys.readouterr()
        assert "[tool] read_file" in captured.err

    def test_on_tool_start_quiet(self, capsys):
        cb = CliCallbacks(verbose=False)
        cb.on_tool_start("id-1", "read_file", {"file_path": "a.py"})
        captured = capsys.readouterr()
        assert captured.err == ""
        assert captured.out == ""

    def test_on_token_usage_verbose(self, capsys):
        cb = CliCallbacks(verbose=True)
        cb.on_token_usage(1234)
        captured = capsys.readouterr()
        assert "[tokens] 1234" in captured.err

    def test_on_token_usage_quiet(self, capsys):
        cb = CliCallbacks(verbose=False)
        cb.on_token_usage(1234)
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_on_iteration_update_verbose(self, capsys):
        cb = CliCallbacks(verbose=True)
        cb.on_iteration_update(3, 50)
        captured = capsys.readouterr()
        assert "3/50" in captured.err

    def test_on_iteration_update_quiet(self, capsys):
        cb = CliCallbacks(verbose=False)
        cb.on_iteration_update(3, 50)
        captured = capsys.readouterr()
        assert captured.err == ""


class TestCliCallbacksSilentMethods:
    """Methods that produce no output."""

    def test_on_thinking_start_is_silent(self, capsys):
        cb = CliCallbacks()
        cb.on_thinking_start()
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_on_thinking_stop_is_silent(self, capsys):
        cb = CliCallbacks()
        cb.on_thinking_stop()
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_on_thinking_content_is_silent(self, capsys):
        cb = CliCallbacks()
        cb.on_thinking_content("some thought")
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_on_tool_complete_is_silent(self, capsys):
        cb = CliCallbacks()
        cb.on_tool_complete("id-1", "result text")
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_on_tools_cleanup_is_silent(self, capsys):
        cb = CliCallbacks()
        cb.on_tools_cleanup()
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""


class TestCliCallbacksConfirmation:
    """request_confirmation must auto-approve."""

    def test_auto_approves(self):
        cb = CliCallbacks()
        result = asyncio.run(
            cb.request_confirmation("write_file", {"file_path": "a.py"})
        )
        assert isinstance(result, CliConfirmResult)
        assert result.action == "approve"


class TestCliCallbacksCancellation:
    """is_cancelled state management."""

    def test_not_cancelled_by_default(self):
        cb = CliCallbacks()
        assert cb.is_cancelled() is False

    def test_can_be_cancelled(self):
        cb = CliCallbacks()
        cb._cancelled = True
        assert cb.is_cancelled() is True
