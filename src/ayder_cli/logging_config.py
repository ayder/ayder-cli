"""Loguru sink configuration and stdlib-logging bridge."""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

from loguru import logger

from ayder_cli.log import LOG_LEVELS

_configured = False
_current_level = "NONE"


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


class _InterceptHandler(logging.Handler):
    """Bridge stdlib logging records into loguru on the `external` channel."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.bind(channel="external", lib=record.name).opt(
            depth=depth, exception=record.exc_info
        ).log(level, record.getMessage())


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


def _add_sink_with_fallback(sink: Any, **kwargs: Any) -> None:
    """Add sink with enqueue=True, fallback to enqueue=False on fd limitations."""
    try:
        logger.add(sink, enqueue=True, **kwargs)
    except ValueError as e:
        if "fds_to_keep" not in str(e):
            raise
        logger.add(sink, enqueue=False, **kwargs)


def _error_filter(record) -> bool:
    """WARNING+ OR anything carrying an exception, at any level."""
    return (
        record["level"].no >= logger.level("WARNING").no
        or record["exception"] is not None
    )


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


def _ensure_parent(path: str) -> str:
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


def setup_logging(settings: LoggingSettings) -> str:
    """Configure all sinks from fully-resolved settings. Returns effective level."""
    global _configured, _current_level

    effective_level = _normalize_level(settings.level)
    logger.remove()

    if settings.file_enabled:
        # ALWAYS added, before any level gate: the no-silent-failure guarantee.
        _add_sink_with_fallback(
            _ensure_parent(settings.error_path),
            level=0,
            filter=_error_filter,
            rotation=settings.rotation,
            retention=settings.retention,
            backtrace=True,
            diagnose=False,
        )

        if settings.trace_enabled:
            _add_sink_with_fallback(
                _ensure_parent(settings.trace_path),
                level=0,
                serialize=True,
                filter=lambda r: "evt" in r["extra"],
                rotation=settings.rotation,
                retention=settings.retention,
                backtrace=False,
                diagnose=False,
            )

    if effective_level != "NONE":
        default_no = logger.level(effective_level).no
        main_filter = _main_filter(settings.channels, settings.channel_levels, default_no)

        if settings.console and settings.console_stream is not None:
            _add_sink_with_fallback(
                settings.console_stream, level=0, filter=main_filter,
                backtrace=False, diagnose=False,
            )
        if settings.file_enabled:
            _add_sink_with_fallback(
                _ensure_parent(settings.file_path), level=0, filter=main_filter,
                rotation=settings.rotation, retention=settings.retention,
                backtrace=False, diagnose=False,
            )

    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)

    for logger_name in ("markdown_it", "httpcore", "httpx", "openai", "anthropic"):
        logging.getLogger(logger_name).setLevel(logging.INFO)

    _configured = True
    _current_level = effective_level
    return effective_level


def is_logging_configured() -> bool:
    """Return whether logging has been configured for this process."""
    return _configured


def get_effective_log_level() -> str:
    """Return the active log level."""
    return _current_level
