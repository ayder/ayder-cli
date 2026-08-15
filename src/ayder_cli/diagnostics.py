"""Process-level exception capture. Installed once, after setup_logging."""

from __future__ import annotations

import signal
import sys
from types import TracebackType

from ayder_cli.log import flush, get_logger, level_no
from ayder_cli.logging_config import (
    _in_default_asyncio_handler,
    _stderr_fallback,
    is_logging_configured,
    would_reach_prose,
)

_log = get_logger("core")
_hooks_installed = False
_signals_installed = False

# B2-prime (§F5-R7). An asyncio `context["message"]` is framework text, but the
# framework interpolates callback reprs and transport state into some of them -
# which is how a request body or a credential ends up in a "diagnostic".
#
# So the allowlist is EXACT, not prefix-based: a message that is not one of
# these known constants degrades to type/length metadata rather than being
# trusted. A message added by a newer Python simply degrades until it is
# reviewed into this table; it can never leak by default.
_ASYNCIO_DEFAULT = "asyncio error"

_ASYNCIO_MESSAGES = frozenset({
    "Task was destroyed but it is pending!",          # asyncio/tasks.py
    "Task exception was never retrieved",             # asyncio/futures.py
    "Future exception was never retrieved",           # asyncio/futures.py
    "Unhandled error in exception handler",           # asyncio/base_events.py
    "Accept failed on a socket",                      # asyncio/proactor_events.py
    "Error on reading from the event loop self pipe",  # asyncio/proactor_events.py
    "Error on transport creation for incoming connection",  # selector_events.py
    "socket.accept() out of system resource",         # asyncio/selector_events.py
    "protocol.pause_writing() failed",                # transports.py, sslproto.py
    "protocol.resume_writing() failed",               # transports.py, sslproto.py
    "Unhandled exception in client_connected_cb",     # asyncio/streams.py
    "Unknown exception in SIGCHLD handler",           # asyncio/unix_events.py
    "unhandled exception during asyncio.run() shutdown",   # asyncio/runners.py
    "Fatal error on transport",                       # transports (_fatal_error)
    "Fatal error on pipe transport",                  # proactor/unix_events.py
    "Cancelling a future failed",                     # windows_events shape
    "Cancelling an overlapped future failed",         # asyncio/windows_events.py
    "Failed to unregister the wait handle",           # asyncio/windows_events.py
    "Pipe accept failed",                             # asyncio/windows_events.py
    _ASYNCIO_DEFAULT,                                 # ayder's own absent default
})

# Interpolating messages: the PREFIX is framework text, the tail is the repr
# that leaks. Keep the prefix, elide the tail to its length.
_ASYNCIO_PREFIXES = (
    "Exception in callback ",                 # asyncio/events.py - the leak vector
    "Executing ",                             # asyncio/base_events.py debug mode
    "an error occurred during closing of ",   # base_events async-gen close
)


def _safe_type_name(value: object) -> str:
    """A bounded, single-token type name for metadata output.

    `__name__` is attacker-reachable on a crafted class, so it is validated
    rather than trusted: anything that is not a short identifier becomes
    `object`, which cannot carry a newline or a credential.
    """
    name = type(value).__name__
    if isinstance(name, str) and name.isidentifier() and len(name) <= 64:
        return name
    return "object"


def _normalize_asyncio_message(message: object) -> str:
    """Reduce an asyncio context message to reviewed text or safe metadata."""
    if message is None:
        return _ASYNCIO_DEFAULT
    if isinstance(message, str):
        if message in _ASYNCIO_MESSAGES:
            return message
        for prefix in _ASYNCIO_PREFIXES:
            if message.startswith(prefix):
                return f"{prefix}<{len(message) - len(prefix)} chars elided>"
        return f"<str, {len(message)} chars>"
    # ONE `str()` attempt, guarded: a hostile `__str__` gets no second chance
    # and cannot take the process down with it.
    try:
        rendered = str(message)
    except Exception:  # noqa: BLE001 - AYDER-EXC hostile __str__; degrade to bounded metadata, never crash diagnostics
        return f"<{_safe_type_name(message)}, unprintable>"
    return f"<{_safe_type_name(message)}, {len(rendered)} chars>"


def _handle_uncaught(
    exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None
) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        return  # a user action, not a crash
    _log.opt(exception=(exc_type, exc, tb)).critical("Unhandled exception")
    flush()


def _handle_asyncio(loop, context: dict) -> None:
    exc = context.get("exception")
    normalized = _normalize_asyncio_message(context.get("message"))
    if exc is not None:
        _log.opt(exception=exc).critical("Unhandled asyncio exception: {}", normalized)
        level, label = level_no("CRITICAL"), "CRITICAL"
    else:
        _log.error("Unhandled asyncio error: {}", normalized)
        level, label = level_no("ERROR"), "ERROR"

    # With every sink off, the record above reaches nobody. Fall back to stderr
    # - built ONLY from the normalized message and the rendered exception, so
    # the fallback can never carry what normalization just removed.
    if not would_reach_prose("core", level, exc is not None):
        _stderr_fallback(
            label, "ayder.core", normalized,
            (type(exc), exc, exc.__traceback__) if exc is not None else None)
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
            # The ORIGINAL context, deliberately UNFLAGGED: a custom handler
            # belongs to someone else, and suppressing its own stdlib records
            # would hide output this process never owned.
            previous(lp, context)
        elif is_logging_configured():
            # Parity for anything the embedder attached to stdlib logging. The
            # flag makes CPython's raw copy identifiable so the bridge drops
            # exactly that one record instead of printing raw context reprs.
            token = _in_default_asyncio_handler.set(True)
            try:
                lp.default_exception_handler(context)
            finally:
                _in_default_asyncio_handler.reset(token)
        # Before setup there is no bridge to identify the copy, so calling the
        # default handler would print raw reprs through `lastResort`. The
        # normalized record above already reached Loguru's own stderr sink.

    # setattr, not attribute assignment: mypy infers `Callable[[Any, Any], Any]`
    # for `_chained` and rejects `._ayder_chained = True` with [attr-defined].
    setattr(_chained, "_ayder_chained", True)
    loop.set_exception_handler(_chained)
