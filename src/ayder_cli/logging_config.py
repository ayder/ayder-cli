"""Loguru sink configuration and stdlib-logging bridge."""

from __future__ import annotations

import contextvars
import inspect
import logging
import sys
import tempfile
import threading
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

from loguru import logger

from ayder_cli.log import LOG_LEVELS
from ayder_cli.masking import mask

_configured = False
_current_level = "NONE"

_SUPPRESSED_LIBS = ("markdown_it", "httpcore", "httpx", "openai", "anthropic")


@dataclass(frozen=True)
class LoggingSettings:
    """Fully resolved logging configuration. The only input to setup_logging."""

    level: str = "NONE"
    channels: frozenset[str] | None = None
    channel_levels: dict[str, int | None] = field(default_factory=dict)
    trace_enabled: bool = False
    console: bool = False
    console_stream: TextIO | None = None
    file_enabled: bool = True
    file_path: str = ".ayder/log/ayder.log"
    error_path: str = ".ayder/log/errors.log"
    trace_path: str = ".ayder/log/trace.jsonl"
    rotation: str = "10 MB"
    retention: str = "7 days"


@dataclass(frozen=True)
class _SinkSpec:
    """Exactly what this process installed. Published only on full success."""

    error_file: bool
    main_file: bool
    console: bool
    default_no: int | None          # None <=> effective level NONE
    channel_levels: dict[str, int | None]
    allowed_channels: frozenset[str] | None


_sink_spec: _SinkSpec | None = None


# ---------------------------------------------------------------- private API

# Loguru's public `add()` accepts an arbitrary object sink, but mask-after-
# render needs the file sink's own rotation/retention machinery, which is
# private. §F5-R6 accepts that against an explicit `loguru>=0.7,<0.8` bound
# plus this loud guard, rather than reimplementing rotation badly.

_REQUIRED_FILE_SINK_PARAMS = frozenset({
    "path", "rotation", "retention", "compression", "delay", "watch",
    "mode", "buffering", "encoding",
})


def _loguru_private() -> tuple[Any, Any, Any]:
    """The three private Loguru objects the masking sinks are built on."""
    from loguru._file_sink import FileSink
    from loguru._handler import Message
    from loguru._simple_sinks import StreamSink

    return FileSink, Message, StreamSink


class _StopProbe:
    """A stream that HAS `stop`, used only to prove StreamSink's dispatch."""

    def stop(self) -> None:
        """Never called: only its presence is measured."""


def _core_handlers() -> dict[int, Any]:
    """Loguru's live handler dict. One private read, shape-guarded above."""
    return logger._core.handlers  # type: ignore[attr-defined]


def _shape_guard() -> None:
    """Verify Loguru's private shape BEFORE anything is torn down.

    Ordering is the whole point. This runs while the previous configuration is
    still installed, so drift raises a named RuntimeError and logging keeps
    working; running it after `logger.remove()` would leave the process silent.
    """
    try:
        file_sink, message_cls, stream_sink = _loguru_private()

        params = set(inspect.signature(file_sink.__init__).parameters)
        lost = sorted(_REQUIRED_FILE_SINK_PARAMS - params)
        if lost:
            raise RuntimeError(f"Loguru drift: FileSink.__init__ lost {lost}")
        for name in ("write", "stop"):
            if not callable(getattr(file_sink, name, None)):
                raise RuntimeError(f"Loguru drift: FileSink has no {name}()")

        if not issubclass(message_cls, str):
            raise RuntimeError("Loguru drift: Message is no longer a str subclass")
        if getattr(message_cls, "__slots__", None) != ("record",):
            raise RuntimeError("Loguru drift: Message.__slots__ is not ('record',)")

        # The console shim's whole safety argument: a sink object WITHOUT a
        # `stop` attribute is never stopped, so `logger.remove()` cannot close
        # a stream the caller owns.
        if getattr(stream_sink(object()), "_stoppable", None) is not False:
            raise RuntimeError(
                "Loguru drift: StreamSink no longer derives _stoppable from `stop`")
        if getattr(stream_sink(_StopProbe()), "_stoppable", None) is not True:
            raise RuntimeError(
                "Loguru drift: StreamSink no longer stops a stoppable sink")

        handlers = _core_handlers()
        if not isinstance(handlers, dict):
            raise RuntimeError("Loguru drift: _core.handlers is no longer a dict")
        for handler in handlers.values():
            if not isinstance(getattr(handler, "levelno", None), int):
                raise RuntimeError("Loguru drift: handlers no longer expose levelno")

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "probe.log"
            probe = MaskingFileSink(str(target), rotation="10 MB",
                                    retention="7 days")
            message = message_cls("probe token=abc123\n")
            message.record = {}
            probe.write(message)
            probe.flush()
            probe.stop()
            if "<redacted:kv>" not in target.read_text(encoding="utf-8"):
                raise RuntimeError("Loguru drift: the masking file sink wrote raw text")
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(
            f"Loguru drift: private sink probe failed with {type(e).__name__}") from e


class MaskingFileSink:
    """A file sink that masks credentials AFTER Loguru renders the record.

    Owns its inner `FileSink` exclusively: `stop()` cascades, and that cascade
    is what closes the file, applies the rotation rename and runs retention.
    """

    def __init__(self, path: str, *, rotation: str | None = None,
                 retention: str | None = None) -> None:
        file_sink, message_cls, _stream_sink = _loguru_private()
        self._message = message_cls
        # The constructor opens the file, so a bad path or an unparseable
        # rotation string fails HERE - before any teardown.
        self._inner = file_sink(path, rotation=rotation, retention=retention)

    def write(self, message: Any) -> None:
        out = self._message(mask(str(message)))
        # Time-based rotation reads record["time"] off the message it is
        # handed; a bare str would make the rotation function raise.
        out.record = message.record
        self._inner.write(out)

    def flush(self) -> None:
        handle = getattr(self._inner, "_file", None)
        if handle is not None:
            handle.flush()

    def stop(self) -> None:
        self._inner.stop()


class _MaskingStream:
    """Console shim: masks on the way out, owns nothing.

    Deliberately has NO `stop()` and NO `close()`. Loguru's StreamSink derives
    `_stoppable` from `callable(getattr(stream, "stop", None))`, so leaving it
    off is exactly what keeps `logger.remove()` from closing the caller's
    stream. Adding one would close somebody else's stdout.
    """

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream

    def write(self, text: str) -> None:
        self._stream.write(mask(text))

    def flush(self) -> None:
        self._stream.flush()

    def isatty(self) -> bool:
        return self._stream.isatty()


# ------------------------------------------------- diagnostics of last resort

# Content-free ON PURPOSE. A reentrant record is one whose own formatting is
# already inside this handler, so touching `record` again - even `.name` or
# `.levelname`, both arbitrary caller text - is how a hostile record gets a
# second chance to run its formatter or inject a newline.
_REENTRANT_NOTICE = "ayder logging: reentrant stdlib record dropped\n"
_FALLBACK_LAST = "ayder logging: diagnostic record unavailable\n"
_UNFORMATTABLE = "<unformattable stdlib record>"

_STD_LEVEL_NAMES = frozenset(
    {"NOTSET", "TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"})

# Thread-local, not a global flag: two threads bridging at once are ordinary,
# and a shared flag would make one thread silently drop the other's records.
_bridge_latch = threading.local()

# Set ONLY around `loop.default_exception_handler(context)` in the no-previous
# branch, so it identifies exactly one record: CPython's raw copy of an event
# this process already logged in normalized form.
_in_default_asyncio_handler: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "ayder_in_default_asyncio_handler", default=False)


def _bound_label(record: logging.LogRecord) -> str:
    """A level name for output. Custom stdlib level names are caller text."""
    name = record.levelname
    return name if name in _STD_LEVEL_NAMES else f"LEVEL {int(record.levelno)}"


def _bound_token(value: str) -> str:
    """Bound an unbounded caller-supplied name to one printable, short token.

    `isprintable()` is False for \\r, \\n and \\t, so a logger name cannot forge
    a second line of output.
    """
    return "".join(ch if ch.isprintable() else "?" for ch in str(value)[:200])


def _stderr_fallback(label: str, name: str, message: str,
                     exc_info: Any) -> None:
    """Render one DIAGNOSTIC to stderr when no prose sink would receive it.

    Callers decide what counts as a diagnostic; this only renders. Deliberately
    silenced low-severity traffic must never be routed here - see the bridge's
    `is_diagnostic` gate.

    Exception-total by design: this is the path that exists BECAUSE logging is
    already broken, so every stage degrades to fixed safe text instead of
    raising. It never calls stdlib logging and `mask()` is pure regex, so it
    cannot recurse back through the bridge.
    """
    try:
        text = f"{label} {name}: {message}\n"
        if exc_info:
            try:
                text += "".join(traceback.format_exception(*exc_info))
            except Exception:  # noqa: BLE001 - AYDER-EXC hostile traceback object; degrade to fixed text, never raise
                text += "<traceback unavailable>\n"
        out = mask(text)
    except Exception:  # noqa: BLE001 - AYDER-EXC hostile message/mask failure; degrade to the fixed last resort
        out = _FALLBACK_LAST
    try:
        sys.stderr.write(out)
    except Exception:  # noqa: BLE001 - AYDER-EXC closed/encoding-broken stderr; diagnostics never crash the process
        pass


def _level_no_of(level: str | int) -> int:
    """Resolve exactly as the forward does: a known name, else the raw number."""
    return logger.level(level).no if isinstance(level, str) else int(level)


class _InterceptHandler(logging.Handler):
    """Bridge stdlib logging records into loguru on the `external` channel."""

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(_bridge_latch, "active", False):
            # Re-entry means a sink, filter or formatter below us logged through
            # stdlib. Forwarding again would recurse until the stack blew.
            try:
                sys.stderr.write(_REENTRANT_NOTICE)
            except Exception:  # noqa: BLE001 - AYDER-EXC closed stderr on the drop path; nothing left to try
                pass
            return

        _bridge_latch.active = True
        try:
            if _in_default_asyncio_handler.get():
                # CPython's raw copy of an asyncio event we already logged in
                # normalized form. It carries unnormalized context reprs, so it
                # is dropped rather than forwarded - never used as a fallback.
                return

            try:
                level: str | int = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno
            forwarded_no = _level_no_of(level)      # resolved ONCE, reused below

            frame, depth = inspect.currentframe(), 0
            while frame and (depth == 0
                             or frame.f_code.co_filename == logging.__file__):
                frame = frame.f_back
                depth += 1

            # Called EXACTLY once: a hostile `getMessage` must not get a second
            # run, and the fallback below reuses this same value.
            try:
                message = record.getMessage()
            except Exception:  # noqa: BLE001 - AYDER-EXC hostile record formatter; degrade to fixed text, keep the record
                message = _UNFORMATTABLE

            logger.bind(channel="external", lib=record.name).opt(
                depth=depth, exception=record.exc_info
            ).log(level, message)

            # The fallback protects DIAGNOSTICS, not everything unrouted. A
            # below-WARNING record with no exception that no sink accepts was
            # deliberately silenced - by level NONE, by the channel allowlist,
            # or by a threshold - and surfacing it would turn the default run
            # into stderr noise, straight through Textual in the TUI.
            is_diagnostic = (forwarded_no >= logger.level("WARNING").no
                             or record.exc_info is not None)
            if is_diagnostic and not would_reach_prose(
                    "external", forwarded_no, record.exc_info is not None):
                _stderr_fallback(_bound_label(record), _bound_token(record.name),
                                 message, record.exc_info)
        finally:
            _bridge_latch.active = False


def _normalize_level(level: str | None) -> str:
    if level is None:
        return "NONE"
    normalized = level.strip().upper()
    if not normalized:
        return "NONE"
    if normalized not in LOG_LEVELS:
        raise ValueError(
            f"Invalid log level '{level}'. Expected one of: {', '.join(LOG_LEVELS)}"
        )
    return normalized


def _add_sink_with_fallback(sink: Any, **kwargs: Any) -> int:
    """Add sink with enqueue=True, fallback to enqueue=False on fd limitations.

    Returns the handler id: Phase B needs it to unwind a partial install.
    """
    try:
        return logger.add(sink, enqueue=True, **kwargs)
    except ValueError as e:
        if "fds_to_keep" not in str(e):
            raise
        return logger.add(sink, enqueue=False, **kwargs)


def _error_filter(record) -> bool:
    """WARNING+ OR anything carrying an exception, at any level."""
    return (
        record["level"].no >= logger.level("WARNING").no
        or record["exception"] is not None
    )


def _trace_filter(record) -> bool:
    """Structured events only - the trace sink is not a prose sink."""
    return "evt" in record["extra"]


def _main_filter(allowed: frozenset[str] | None,
                 levels: dict[str, int | None],
                 default_no: int):
    """Event exclusion, then allowlist, then per-channel threshold."""

    def _filter(record) -> bool:
        if "evt" in record["extra"]:
            return False
        # NEVER index directly: a raw loguru record has an empty extra, and a
        # KeyError here makes loguru drop the record and spew to stderr.
        ch = record["extra"].get("channel", "external")
        if allowed is not None and ch not in allowed:
            return False
        threshold = levels.get(ch, default_no)
        if threshold is None:
            return False
        return record["level"].no >= threshold

    return _filter


def would_reach_prose(channel: str, level_no: int, has_exception: bool) -> bool:
    """Would a record of this shape reach ANY prose sink right now?

    Mirrors `_error_filter` and `_main_filter` against the spec this process
    published, rather than counting handlers - a handler count cannot tell a
    prose sink from the trace sink, and cannot apply the channel allowlist.
    Three states are covered by exactly one branch each: never configured,
    configured, and the safe state a failed setup publishes.
    """
    spec = _sink_spec
    if spec is None:
        # Pre-setup or failed-setup. Loguru's OWN default stderr handler is
        # present until the first `remove()`, so a record that reaches it is
        # already visible and must not be duplicated by a fallback.
        handlers = _core_handlers()
        if not handlers:
            return False
        return level_no >= min(h.levelno for h in handlers.values())
    if spec.error_file and (level_no >= logger.level("WARNING").no or has_exception):
        return True
    if spec.default_no is None:
        return False                          # level NONE: no main/console sink
    if spec.allowed_channels is not None and channel not in spec.allowed_channels:
        return False
    threshold = spec.channel_levels.get(channel, spec.default_no)
    if threshold is None:
        return False
    return (spec.main_file or spec.console) and level_no >= threshold


def _ensure_parent(path: str) -> str:
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


def _stop_owned(sinks: list[Any], failure: BaseException, stage: str) -> None:
    """Close owned sinks, newest first, best effort. Never raises, never logs.

    Content-free by construction: a cleanup failure contributes only its stage
    and exception TYPE to the original failure's notes. Logging here would push
    a record through the very sinks being torn down.
    """
    for sink in reversed(sinks):
        try:
            sink.stop()
        except Exception as e:  # noqa: BLE001 - AYDER-EXC best-effort cleanup; type-only note, caller re-raises the original
            failure.add_note(
                f"ayder setup cleanup ({stage}): {type(e).__name__} stopping a sink")


def _remove_handlers(handler_ids: list[int], failure: BaseException) -> None:
    """Remove handlers this call added, best effort. Never raises, never logs."""
    for hid in handler_ids:
        try:
            logger.remove(hid)
        except Exception as e:  # noqa: BLE001 - AYDER-EXC best-effort cleanup; type-only note, caller re-raises the original
            failure.add_note(
                f"ayder setup cleanup (install): {type(e).__name__} removing "
                f"handler {hid}")


def setup_logging(settings: LoggingSettings) -> str:
    """Configure all sinks from fully-resolved settings. Returns effective level.

    Transactional. Every failure converges to one of exactly two observable
    states: the PREVIOUS configuration fully intact (anything that fails before
    the teardown boundary), or the explicit safe state - zero handlers, no
    published spec, `_configured` False, level "NONE" (anything after it).
    Loguru cannot re-add a removed handler, so restoring the old sinks after
    teardown is refused rather than faked.
    """
    global _configured, _current_level, _sink_spec

    # ---- Phase A: pure computation. No published state is touched. ----------
    effective_level = _normalize_level(settings.level)
    _shape_guard()

    allowed = settings.channels
    # ONE snapshot, shared by the filter closure and the published spec, so the
    # predicate can never disagree with the sinks about a channel threshold -
    # and a later mutation of the caller's dict changes neither.
    levels = dict(settings.channel_levels)
    default_no = (logger.level(effective_level).no
                  if effective_level != "NONE" else None)

    constructed: list[Any] = []
    error_sink = trace_sink = console_sink = main_sink = None
    try:
        if settings.file_enabled:
            # ALWAYS constructed, before any level gate: the no-silent-failure
            # guarantee.
            error_sink = MaskingFileSink(_ensure_parent(settings.error_path),
                                         rotation=settings.rotation,
                                         retention=settings.retention)
            constructed.append(error_sink)
            if settings.trace_enabled:
                # Raw and UNMASKED, but preconstructed like the rest so that a
                # bad trace path still fails before the teardown boundary.
                file_sink, _message_cls, _stream_sink = _loguru_private()
                trace_sink = file_sink(_ensure_parent(settings.trace_path),
                                       rotation=settings.rotation,
                                       retention=settings.retention)
                constructed.append(trace_sink)
        if default_no is not None:
            if settings.console and settings.console_stream is not None:
                console_sink = _MaskingStream(settings.console_stream)  # not owned
            if settings.file_enabled:
                main_sink = MaskingFileSink(_ensure_parent(settings.file_path),
                                            rotation=settings.rotation,
                                            retention=settings.retention)
                constructed.append(main_sink)
    except BaseException as failure:
        _stop_owned(constructed, failure, "construct")
        raise                       # old handlers and all published state intact

    main_filter = (_main_filter(allowed, levels, default_no)
                   if default_no is not None else None)
    # Rotation and retention now live INSIDE the constructed sinks, so an add
    # carries only the dispatch options.
    planned: list[tuple[Any, dict[str, Any]]] = []
    if error_sink is not None:
        planned.append((error_sink, {"level": 0, "filter": _error_filter,
                                     "backtrace": True, "diagnose": False}))
    if trace_sink is not None:
        planned.append((trace_sink, {"level": 0, "serialize": True,
                                     "filter": _trace_filter,
                                     "backtrace": False, "diagnose": False}))
    if console_sink is not None:
        planned.append((console_sink, {"level": 0, "filter": main_filter,
                                       "backtrace": False, "diagnose": False}))
    if main_sink is not None:
        planned.append((main_sink, {"level": 0, "filter": main_filter,
                                    "backtrace": False, "diagnose": False}))

    next_spec = _SinkSpec(
        error_file=error_sink is not None,
        main_file=main_sink is not None,
        console=console_sink is not None,
        default_no=default_no,
        channel_levels=levels,
        allowed_channels=allowed,
    )

    # ---- Phase B: teardown and install, inside ONE failure boundary. --------
    added_ids: list[int] = []
    added_sinks: set[int] = set()
    try:
        teardown_failure: BaseException | None = None
        # Per id, not a bare `logger.remove()`: Loguru pops the handler and
        # republishes the dict BEFORE calling stop(), so a raising stop() still
        # leaves that handler deregistered. One at a time keeps that property
        # for every handler instead of losing the rest to the first failure.
        for hid in list(_core_handlers()):
            try:
                logger.remove(hid)
            except Exception as e:  # noqa: BLE001 - AYDER-EXC best-effort teardown; first failure raised, the rest noted by type
                if teardown_failure is None:
                    teardown_failure = e
                else:
                    teardown_failure.add_note(
                        f"ayder setup: also failed removing handler {hid}: "
                        f"{type(e).__name__}")
        if teardown_failure is not None:
            raise teardown_failure

        for sink, kwargs in planned:
            added_ids.append(_add_sink_with_fallback(sink, **kwargs))
            added_sinks.add(id(sink))

        logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
        for logger_name in _SUPPRESSED_LIBS:
            logging.getLogger(logger_name).setLevel(logging.INFO)
    except BaseException as failure:
        _remove_handlers(added_ids, failure)
        _stop_owned([s for s in constructed if id(s) not in added_sinks],
                    failure, "install")
        # Spec FIRST: `would_reach_prose` reads only `_sink_spec`, in a single
        # read, so publishing it first makes the safe state atomic with respect
        # to every predicate evaluation.
        _sink_spec = None
        _configured = False
        _current_level = "NONE"
        raise

    # ---- Phase C: publish only after handlers AND the bridge are installed. -
    _sink_spec = next_spec
    _configured = True
    _current_level = effective_level
    return effective_level


def is_logging_configured() -> bool:
    """Return whether logging has been configured for this process."""
    return _configured


def get_effective_log_level() -> str:
    """Return the active log level."""
    return _current_level
