"""Shared pytest fixtures.

`loguru_caplog` replaces pytest's `caplog` for code that logs through the
Loguru facade. Loguru records never reach pytest's stdlib capture — the handler
chain runs the other way — so `caplog.text` is silently empty for any module
bound with `ayder_cli.log.get_logger`.
"""
from __future__ import annotations

import contextlib
import pathlib
import sys

import pytest
from loguru import logger

# The `-S` severity tests import the §C14 resolver from scripts/. Insert it here
# rather than in each test file: conftest is loaded before collection and this
# path is derived from the file, so it does not depend on pytest's cwd.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))


class LoguruCapture:
    """Captured Loguru records, with the native record dict preserved."""

    def __init__(self, records: list[dict] | None = None) -> None:
        self.records: list[dict] = records if records is not None else []

    @property
    def text(self) -> str:
        return "\n".join(r["message"] for r in self.records)

    @property
    def messages(self) -> list[str]:
        return [r["message"] for r in self.records]

    @property
    def levels(self) -> list[str]:
        return [r["level"].name for r in self.records]

    @property
    def channels(self) -> set[str]:
        return {r["extra"].get("channel") for r in self.records}

    def at_level(self, level: str) -> "LoguruCapture":
        """Records at `level` or above. Explicit, and never touches propagation."""
        floor = logger.level(level.upper()).no
        return LoguruCapture([r for r in self.records if r["level"].no >= floor])

    def only(self, level: str) -> "LoguruCapture":
        want = level.upper()
        return LoguruCapture([r for r in self.records if r["level"].name == want])

    def from_channel(self, channel: str) -> "LoguruCapture":
        return LoguruCapture(
            [r for r in self.records if r["extra"].get("channel") == channel]
        )

    def __len__(self) -> int:
        return len(self.records)

    def __bool__(self) -> bool:
        return bool(self.records)


@contextlib.contextmanager
def loguru_capture():
    """Install a capture sink; always remove it, including on an exception.

    Factored out of the fixture so the exceptional-exit path can be exercised
    directly, without depending on test ordering or module globals.
    """
    cap = LoguruCapture()
    sink_id = logger.add(
        lambda m: cap.records.append(m.record),
        level=0,
        format="{message}",
        catch=False,
        diagnose=False,
        backtrace=False,
    )
    try:
        yield cap
    finally:
        logger.remove(sink_id)


@pytest.fixture
def loguru_caplog():
    """Capture every Loguru record emitted during the test. Not autouse."""
    with loguru_capture() as cap:
        yield cap


@pytest.fixture
def capture_loguru():
    """The raw context manager, for controls that drive it directly.

    Handed over as a fixture rather than imported: `tests/` is a package, so
    pytest does not put it on `sys.path` and `from conftest import ...` raises
    ModuleNotFoundError from any subdirectory.
    """
    return loguru_capture
