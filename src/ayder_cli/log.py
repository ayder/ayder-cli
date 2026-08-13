"""Channel-scoped loguru accessors and level constants. Imports only loguru."""
from __future__ import annotations

from loguru import logger

LOG_LEVELS: tuple[str, ...] = ("NONE", "ERROR", "WARNING", "INFO", "DEBUG", "TRACE")

CHANNELS: tuple[str, ...] = ("llm", "tool", "agent", "context", "plugin", "ui", "core")
RESERVED_CHANNELS: tuple[str, ...] = ("external",)
SELECTABLE_CHANNELS: tuple[str, ...] = CHANNELS + RESERVED_CHANNELS


def get_logger(channel: str):
    """Return a logger bound to *channel*. Rejects reserved channels."""
    if channel not in CHANNELS:
        raise ValueError(
            f"Unknown log channel {channel!r}. Expected one of: {', '.join(CHANNELS)}"
        )
    return logger.bind(channel=channel)


def level_no(name: str) -> int:
    """Numeric severity for a level name. Avoids importing loguru elsewhere."""
    return logger.level(name).no


def flush() -> None:
    """Drain queued records. Required before asserting on sink contents,
    and before process exit — sinks use enqueue=True."""
    logger.complete()
