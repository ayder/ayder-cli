import json
from pathlib import Path

import pytest
from loguru import logger

from ayder_cli.log import SCHEMA_VERSION, emit_event
from ayder_cli.logging_config import LoggingSettings, setup_logging


def _setup(tmp_path: Path, **kw) -> None:
    setup_logging(LoggingSettings(
        file_path=str(tmp_path / "ayder.log"),
        error_path=str(tmp_path / "errors.log"),
        trace_path=str(tmp_path / "trace.jsonl"),
        **kw,
    ))


def test_event_lands_in_trace_file(tmp_path):
    _setup(tmp_path, level="NONE", trace_enabled=True)
    emit_event("llm", "iteration", n=3, model="test", session_id="s1")
    logger.complete()

    line = (tmp_path / "trace.jsonl").read_text().splitlines()[0]
    rec = json.loads(line)
    extra = rec["record"]["extra"]
    assert extra["evt"] == "iteration"
    assert extra["channel"] == "llm"
    assert extra["n"] == 3
    assert extra["schema_version"] == SCHEMA_VERSION


def test_event_never_appears_in_main_log(tmp_path):
    _setup(tmp_path, level="TRACE", trace_enabled=True)
    emit_event("llm", "iteration", n=1, session_id="s1")
    logger.complete()
    assert "iteration" not in (tmp_path / "ayder.log").read_text()


def test_trace_file_absent_when_disabled(tmp_path):
    _setup(tmp_path, level="TRACE", trace_enabled=False)
    emit_event("llm", "iteration", n=1, session_id="s1")
    logger.complete()
    assert not (tmp_path / "trace.jsonl").exists()


def test_prose_trace_is_not_an_event(tmp_path):
    _setup(tmp_path, level="TRACE", trace_enabled=True)
    from ayder_cli.log import get_logger

    get_logger("llm").trace("ordinary narrative")
    logger.complete()
    trace = tmp_path / "trace.jsonl"
    body = trace.read_text() if trace.exists() else ""
    assert "ordinary narrative" not in body
    assert "ordinary narrative" in (tmp_path / "ayder.log").read_text()


def test_unknown_channel_rejected():
    with pytest.raises(ValueError):
        emit_event("bogus", "iteration", n=1)
