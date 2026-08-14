"""Process-level exception capture. Installed once, after setup_logging."""

from __future__ import annotations

import signal
import sys
from types import TracebackType

from ayder_cli.log import flush, get_logger

_log = get_logger("core")
_hooks_installed = False
_signals_installed = False


def _handle_uncaught(
    exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None
) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        return  # a user action, not a crash
    _log.opt(exception=(exc_type, exc, tb)).critical("Unhandled exception")
    flush()


def _handle_asyncio(loop, context: dict) -> None:
    exc = context.get("exception")
    message = context.get("message", "asyncio error")
    if exc is not None:
        _log.opt(exception=exc).critical("Unhandled asyncio exception: {}", message)
    else:
        _log.error("Unhandled asyncio error: {}", message)
    flush()


def install_exception_hooks() -> None:
    """Install excepthook and signal handlers. Process-wide and idempotent."""
    global _hooks_installed, _signals_installed

    if not _hooks_installed:
        previous_hook = sys.excepthook
        # The flag alone is not enough: anything that clears it while the
        # wrapper stays installed would nest a second layer and log twice.
        # Mark the wrapper and re-check it, exactly as the asyncio side does.
        if not getattr(previous_hook, "_ayder_chained", False):

            def _chained(exc_type, exc, tb):
                _handle_uncaught(exc_type, exc, tb)
                previous_hook(exc_type, exc, tb)  # keep the terminal traceback

            setattr(_chained, "_ayder_chained", True)
            sys.excepthook = _chained
        _hooks_installed = True

    if not _signals_installed:
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                previous_handler = signal.getsignal(sig)

                def _chained_signal(signum, frame, _prev=previous_handler):
                    # A signal is a termination request, not an exception:
                    # WARNING, and no traceback to attach.
                    _log.warning(
                        "Received signal {}; flushing logs", signal.Signals(signum).name
                    )
                    flush()
                    if callable(_prev):
                        _prev(signum, frame)  # Textual's terminal cleanup
                    elif _prev == signal.SIG_DFL:
                        signal.signal(signum, signal.SIG_DFL)
                        signal.raise_signal(signum)

                signal.signal(sig, _chained_signal)
            except (ValueError, OSError):
                pass  # not the main thread
        _signals_installed = True


def install_asyncio_handler(loop) -> None:
    """Attach the handler to a RUNNING loop. Call from inside the loop."""
    previous = loop.get_exception_handler()
    if getattr(previous, "_ayder_chained", False):
        return  # already installed on this loop

    def _chained(lp, context):
        _handle_asyncio(lp, context)
        if previous is not None:
            previous(lp, context)  # whatever was there first
        else:
            lp.default_exception_handler(context)  # keep the stderr traceback

    # setattr, not attribute assignment: mypy infers `Callable[[Any, Any], Any]`
    # for `_chained` and rejects `._ayder_chained = True` with [attr-defined].
    setattr(_chained, "_ayder_chained", True)
    loop.set_exception_handler(_chained)
