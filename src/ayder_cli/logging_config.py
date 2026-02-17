"""Centralized Loguru configuration with stdlib logging interception."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, TextIO

from loguru import logger

from ayder_cli.core.config import Config

LOG_LEVELS: tuple[str, ...] = ("NONE", "ERROR", "WARNING", "INFO", "DEBUG")

_configured = False
_current_level = "NONE"


class _InterceptHandler(logging.Handler):
    """Redirect standard logging records to Loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame = logging.currentframe()
        depth = 2
        while frame is not None and frame.f_code.co_filename == logging.__file__:
            depth += 1
            if frame.f_back is None:
                break
            frame = frame.f_back

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


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


def setup_logging(
    config: Config,
    level_override: str | None = None,
    *,
    console_stream: TextIO | None = None,
) -> str:
    """Configure Loguru sinks and intercept stdlib logging."""
    global _configured, _current_level

    effective_level = _normalize_level(
        level_override if level_override is not None else config.logging_level
    )

    logger.remove()

    if effective_level != "NONE":
        if console_stream is not None:
            _add_sink_with_fallback(
                console_stream,
                level=effective_level,
                backtrace=False,
                diagnose=False,
            )
        if config.logging_file_enabled:
            log_path = Path(config.logging_file_path).expanduser()
            log_path.parent.mkdir(parents=True, exist_ok=True)
            _add_sink_with_fallback(
                str(log_path),
                level=effective_level,
                rotation=config.logging_rotation,
                retention=config.logging_retention,
                backtrace=False,
                diagnose=False,
            )

    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    _configured = True
    _current_level = effective_level
    return effective_level


def is_logging_configured() -> bool:
    """Return whether logging has been configured for this process."""
    return _configured


def get_effective_log_level() -> str:
    """Return the active log level."""
    return _current_level
