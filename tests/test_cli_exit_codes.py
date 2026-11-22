"""Exit codes of a single-command run (``ayder "prompt"``, ``--stdin``).

Kind: baseline regression. ``ChatLoop.run`` reports every failure through a callback
and returns normally, and ``_run_loop`` returned 0 unconditionally, so a scripted run
exited 0 after a stream error. Ctrl+C escaped as a KeyboardInterrupt traceback.

A real ``ChatLoop`` and ``CliCallbacks`` run under a stub runtime; the provider is
faked, so no network is used (environment: local-faked).
"""

from __future__ import annotations

import asyncio
import errno
import signal
import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

from ayder_cli.cli_runner import _run_loop, run_command
from ayder_cli.providers.base import NormalizedStreamChunk
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



# -- The outcome decides the exit code and the fallback message (plan step 4, R8) ------------


class _FullPipe:
    """A stderr whose first write fails as a full non-blocking pipe does; later writes are kept."""

    def __init__(self) -> None:
        self.failed = False
        self.kept: list[str] = []

    def write(self, text: str) -> int:
        if not self.failed:
            self.failed = True
            raise BlockingIOError(errno.EAGAIN, "write could not complete without blocking")
        self.kept.append(text)
        return len(text)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False


def test_a_failure_the_callbacks_could_not_print_still_reaches_stderr(monkeypatch):
    """Baseline regression: after step 3 the exit code is 1 and nothing is on stderr.

    Driven by a real I/O failure: the first write to stderr raises ``BlockingIOError``, so
    ``CliCallbacks.on_system_message`` raises, the loop reports ``reported`` False, and the later
    writes are kept. After: exit 1, with the message on stderr from ``_run_loop``'s fallback.
    """
    pipe = _FullPipe()
    monkeypatch.setattr(sys, "stderr", pipe)

    code = _exit_code(_Raising(RuntimeError("boom")))

    assert pipe.failed
    assert code == 1
    assert "Error: boom" in "".join(pipe.kept)


def test_a_failure_the_callbacks_printed_is_printed_once(capsys):
    """Preservation: with ``reported`` True the fallback adds nothing."""
    assert _exit_code(_Raising(RuntimeError("boom"))) == 1

    assert capsys.readouterr().err.count("Error: boom") == 1


class _StallingProvider:
    """Streams one chunk, tells the test it is awaiting, then waits; Ctrl+C lands here."""

    def __init__(self, awaiting: threading.Event) -> None:
        self.awaiting = awaiting

    async def stream_with_tools(self, *args, **kwargs):
        chunk = NormalizedStreamChunk()
        chunk.content = "partial"
        yield chunk
        self.awaiting.set()
        await asyncio.sleep(5)


def _ctrl_c_during_the_stream() -> tuple[int | None, bool]:
    """Run ``_run_loop`` while a helper thread sends SIGINT once the stream is awaiting.

    ``_run_loop`` runs in the test's main thread. Returns its exit code and whether a
    ``KeyboardInterrupt`` escaped it (a regression then fails the test, not the session).
    """
    awaiting = threading.Event()
    main_thread = threading.main_thread().ident
    assert main_thread is not None

    def send_sigint() -> None:
        if awaiting.wait(5):
            signal.pthread_kill(main_thread, signal.SIGINT)

    sender = threading.Thread(target=send_sigint, daemon=True)
    sender.start()
    interrupted = False
    code = None
    try:
        with patch(
            "ayder_cli.cli_runner.create_runtime",
            return_value=_runtime(_StallingProvider(awaiting)),
        ):
            code = _run_loop("hello", permissions={"r"})
    except KeyboardInterrupt:
        interrupted = True
    finally:
        sender.join(5)
    assert awaiting.is_set()
    return code, interrupted


def test_ctrl_c_with_the_default_handler_exits_130(default_sigint_handler):
    """Baseline regression, E17: after step 3 the exit code is 0.

    Driven by a real SIGINT with Python's default handler installed: a helper thread waits until
    the stream is awaiting, then signals the main thread, where ``_run_loop`` runs under
    ``asyncio.run``. Its runner cancels the turn's task; the stream swallows the cancellation and
    ``run()`` returns with the outcome ``cancelled``, which ``loop.error`` does not show. After:
    exit 130, from the outcome.
    """
    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler

    code, interrupted = _ctrl_c_during_the_stream()

    assert not interrupted
    assert code == 130


def test_ctrl_c_with_the_default_handler_prints_interrupted(default_sigint_handler, capsys):
    """Baseline regression, E17 (step 6): the cancellation did not reach ``asyncio.run``.

    Same harness as above. Today the stream swallows the cancellation, so ``asyncio.run`` returns
    normally and ``_run_loop`` exits 130 from the outcome without its ``Interrupted.`` line.
    After: the cancellation propagates, ``asyncio.run`` raises ``KeyboardInterrupt``, and
    ``_run_loop`` prints ``Interrupted.``.
    """
    _ctrl_c_during_the_stream()

    assert "Interrupted." in capsys.readouterr().err


def test_ctrl_c_with_the_diagnostics_hook_exits_130_and_prints_interrupted(
    diagnostics_sigint_handler, capsys
):
    """Preservation, E17: with the CLI's own SIGINT handler the same Ctrl+C is the same.

    Diagnostics' handler raises ``KeyboardInterrupt`` in the main thread, so ``asyncio.run``
    raises it and ``_run_loop`` prints ``Interrupted.`` and exits 130, before and after.
    """
    code, interrupted = _ctrl_c_during_the_stream()

    assert not interrupted
    assert code == 130
    assert "Interrupted." in capsys.readouterr().err
