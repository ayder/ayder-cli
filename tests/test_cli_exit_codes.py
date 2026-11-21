"""Exit codes of a single-command run (``ayder "prompt"``, ``--stdin``).

Kind: baseline regression. ``ChatLoop.run`` reports every failure through a callback
and returns normally, and ``_run_loop`` returned 0 unconditionally, so a scripted run
exited 0 after a stream error. Ctrl+C escaped as a KeyboardInterrupt traceback.

A real ``ChatLoop`` and ``CliCallbacks`` run under a stub runtime; the provider is
faked, so no network is used (environment: local-faked).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ayder_cli.cli_runner import _run_loop, run_command
from tests.loops.test_chat_loop_errors import _Raising
from tests.loops.test_chat_loop_guards import _Context, _Provider, _Registry


def _runtime(provider) -> MagicMock:
    rt = MagicMock()
    rt.config.model = "m"
    rt.config.provider = "ollama"
    rt.config.num_ctx = 4096
    rt.config.max_output_tokens = 2048
    rt.config.stop_sequences = []
    rt.config.verbose = False
    rt.config.tool_tags = None
    rt.config.max_history_messages = 0
    rt.config.max_iterations = 0
    rt.config.agents = {}
    rt.system_prompt = "system"
    rt.llm_provider = provider
    rt.tool_registry = _Registry()
    rt.context_manager = _Context()
    return rt


def _exit_code(provider) -> int:
    with patch("ayder_cli.cli_runner.create_runtime", return_value=_runtime(provider)):
        return _run_loop("hello", permissions={"r"})


def test_a_stream_error_exits_1(capsys):
    """Baseline regression: exit 0 today."""
    assert _exit_code(_Raising(RuntimeError("boom"))) == 1
    assert "Error: boom" in capsys.readouterr().err


def test_the_max_iterations_stop_exits_1():
    """Baseline regression: exit 0 today."""
    rt = _runtime(_Provider({"tool": ("read_file", '{"file_path": "a.py"}')}))
    rt.config.max_iterations = 2
    with patch("ayder_cli.cli_runner.create_runtime", return_value=rt):
        assert _run_loop("hello", permissions={"r"}) == 1


def test_an_empty_response_exits_1():
    """Baseline regression: exit 0 today."""
    assert _exit_code(_Provider({})) == 1


def test_a_text_reply_exits_0():
    """Preservation: a successful turn exits 0."""
    assert _exit_code(_Provider({"content": "hi"})) == 0


def test_run_command_returns_the_error_exit_code():
    """Baseline regression: the single-command entry point inherits the 0."""
    with patch(
        "ayder_cli.cli_runner.create_runtime",
        return_value=_runtime(_Raising(RuntimeError("boom"))),
    ):
        assert run_command("hello", permissions={"r"}) == 1


def test_ctrl_c_exits_130_and_prints_interrupted(capsys):
    """Baseline regression: KeyboardInterrupt escapes as a traceback today."""

    def interrupt(coro):
        coro.close()  # the un-awaited _drive() would warn on garbage collection
        raise KeyboardInterrupt

    with patch(
        "ayder_cli.cli_runner.create_runtime", return_value=_runtime(_Provider({"content": "x"}))
    ), patch("ayder_cli.cli_runner.asyncio.run", side_effect=interrupt):
        assert _run_loop("hello", permissions={"r"}) == 130

    assert "Interrupted." in capsys.readouterr().err

