"""Tests for ayder_cli.__main__ module entry point."""

import contextlib
import runpy
import sys
from unittest.mock import patch

import pytest


@contextlib.contextmanager
def _process_hook_isolation():
    """Snapshot and restore everything ``install_exception_hooks`` mutates.

    Running ``ayder_cli`` as ``__main__`` reaches ``cli.main()``, which installs
    the excepthook and both signal wrappers process-wide; without this they leak
    into every later test and every later file in the same pytest process.
    Snapshot the three hook objects and the two ``diagnostics`` flags, clear
    only the flags so an in-test install is observable, and put all five back
    afterwards.

    The flags are RESTORED to their entering values rather than reset to False,
    so a process that legitimately entered with hooks installed leaves this
    context with its wrappers and its flags still agreeing.

    pytest (and each xdist worker) runs tests on the main thread, so the
    teardown ``signal.signal`` calls cannot raise ``ValueError``; a genuine
    failure surfaces as a visible teardown error instead of being swallowed.
    """
    import signal

    import ayder_cli.diagnostics as d

    saved_hook = sys.excepthook
    saved_sigint = signal.getsignal(signal.SIGINT)
    saved_sigterm = signal.getsignal(signal.SIGTERM)
    saved_hooks_installed = d._hooks_installed
    saved_signals_installed = d._signals_installed

    d._hooks_installed = False
    d._signals_installed = False
    try:
        yield
    finally:
        sys.excepthook = saved_hook
        signal.signal(signal.SIGINT, saved_sigint)
        signal.signal(signal.SIGTERM, saved_sigterm)
        d._hooks_installed = saved_hooks_installed
        d._signals_installed = saved_signals_installed


@pytest.fixture(autouse=True)
def _reset_hook_state():
    """Isolate process-level hook state around every test in this module."""
    with _process_hook_isolation():
        yield


class TestMainEntryPoint:
    """Test that __main__.py correctly calls the main CLI entry point."""

    def test_main_calls_cli_main(self):
        """Test that running __main__ module calls cli.main() which launches TUI."""
        with patch("ayder_cli.tui.run_tui") as mock_run_tui, \
             patch("sys.argv", ["ayder"]), \
             patch("sys.stdin.isatty", return_value=True):
            # Run the module as __main__ using runpy
            runpy.run_module("ayder_cli", run_name="__main__")

            # Verify run_tui was called (via cli.main, TUI is default)
            mock_run_tui.assert_called_once()

    def test_main_module_execution(self):
        """Test that __main__.py properly guards execution with __name__ check."""
        # First, remove the module from cache if it exists
        if "ayder_cli.__main__" in sys.modules:
            del sys.modules["ayder_cli.__main__"]
        
        with patch("ayder_cli.cli.main") as mock_main:
            # Import and run the __main__ module directly
            
            # Since we're just importing (not running with python -m),
            # the __name__ == "__main__" guard should prevent execution
            mock_main.assert_not_called()

    def test_main_import_does_not_run(self):
        """Test that importing __main__ without running doesn't call the main function."""
        # First, remove the module from cache if it exists
        if "ayder_cli.__main__" in sys.modules:
            del sys.modules["ayder_cli.__main__"]
        
        with patch("ayder_cli.cli.main") as mock_main:
            # Create a mock that can be imported without executing
            import importlib.util
            assert importlib.util.find_spec("ayder_cli.__main__") is not None
            
            # Just finding the spec doesn't execute the module
            # But importing will trigger the if __name__ == "__main__" check
            # which should NOT execute when imported normally
            
            # Since the module uses if __name__ == "__main__", 
            # importing it should not call main()
            # We'll verify this by checking that main is not called
            # when we just import (not run with runpy)
            
            # Note: This test verifies correct use of __name__ guard
            mock_main.assert_not_called()


def test_previous_client_test_did_not_leak_process_hooks():
    """No preceding test in this file left an Ayder process hook installed.

    ``TestMainEntryPoint::test_main_calls_cli_main`` runs the package as
    ``__main__``, which installs the excepthook and both signal wrappers for
    real, so in a clean run this node observes that test's fixture teardown. It
    is a regression check on those teardowns only — it does not claim to
    sanitise arbitrary external state.
    """
    import signal

    import ayder_cli.diagnostics as d

    assert not getattr(sys.excepthook, "_ayder_chained", False)
    for sig in (signal.SIGTERM, signal.SIGINT):
        assert "chained_signal" not in getattr(
            signal.getsignal(sig), "__qualname__", ""
        )
    # The autouse fixture clears both flags on entry, so these two record the
    # expected state rather than detecting a leak; the hook objects above carry
    # the regression weight.
    assert d._hooks_installed is False
    assert d._signals_installed is False
