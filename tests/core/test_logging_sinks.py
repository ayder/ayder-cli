import logging
from pathlib import Path

from loguru import logger

from ayder_cli.logging_config import LoggingSettings, setup_logging


def _settings(tmp_path: Path, **kw) -> LoggingSettings:
    base = dict(
        file_path=str(tmp_path / "ayder.log"),
        error_path=str(tmp_path / "errors.log"),
        trace_path=str(tmp_path / "trace.jsonl"),
    )
    base.update(kw)
    return LoggingSettings(**base)


def test_debug_with_exception_reaches_error_log(tmp_path):
    setup_logging(_settings(tmp_path, level="NONE"))
    try:
        raise ValueError("boom")
    except ValueError:
        logger.bind(channel="core").opt(exception=True).debug("benign")
    logger.complete()
    assert "boom" in (tmp_path / "errors.log").read_text()


def test_plain_debug_does_not_reach_error_log(tmp_path):
    setup_logging(_settings(tmp_path, level="NONE"))
    logger.bind(channel="core").debug("just narrative")
    logger.complete()
    p = tmp_path / "errors.log"
    assert "just narrative" not in (p.read_text() if p.exists() else "")


def test_file_enabled_false_writes_nothing(tmp_path):
    setup_logging(_settings(tmp_path, level="DEBUG", file_enabled=False))
    logger.bind(channel="core").error("should not be written")
    logger.complete()
    assert not (tmp_path / "errors.log").exists()
    assert not (tmp_path / "ayder.log").exists()


def test_third_party_records_get_external_channel(tmp_path):
    setup_logging(_settings(tmp_path, level="DEBUG"))
    seen = []
    sid = logger.add(lambda m: seen.append(m.record["extra"]), level=0)
    try:
        logging.getLogger("httpx").warning("third party message")
    finally:
        logger.remove(sid)
    assert seen and seen[0].get("channel") == "external"
    assert seen[0].get("lib") == "httpx"


def test_unbound_record_does_not_break_the_filter(tmp_path):
    """A raw loguru record has empty extra. The filter must not raise."""
    setup_logging(_settings(tmp_path, level="DEBUG"))
    logger.warning("unbound record")      # no channel bound
    logger.complete()
    assert "unbound record" in (tmp_path / "ayder.log").read_text()


def test_event_records_are_excluded_from_main_log(tmp_path):
    setup_logging(_settings(tmp_path, level="TRACE"))
    logger.bind(channel="llm", evt="iteration", n=1).trace("llm iteration")
    logger.complete()
    assert "llm iteration" not in (tmp_path / "ayder.log").read_text()


def test_trace_sink_writes_events_and_only_events(tmp_path):
    """Exclusion from ayder.log is half the contract; this is the other half."""
    import json

    setup_logging(_settings(tmp_path, level="TRACE", trace_enabled=True))
    logger.bind(channel="llm", evt="iteration", n=7).trace("llm iteration")
    logger.bind(channel="llm").trace("ordinary prose, not an event")
    logger.complete()

    lines = [l for l in (tmp_path / "trace.jsonl").read_text().splitlines() if l.strip()]
    assert len(lines) == 1, f"expected exactly one event line, got {len(lines)}"
    extra = json.loads(lines[0])["record"]["extra"]
    assert extra["evt"] == "iteration"
    assert extra["n"] == 7
    assert extra["channel"] == "llm"


def test_trace_file_is_absent_when_trace_is_disabled(tmp_path):
    setup_logging(_settings(tmp_path, level="TRACE", trace_enabled=False))
    logger.bind(channel="llm", evt="iteration", n=1).trace("llm iteration")
    logger.complete()
    assert not (tmp_path / "trace.jsonl").exists()


def test_allowlist_beats_permissive_channel_level(tmp_path):
    setup_logging(_settings(
        tmp_path, level="DEBUG",
        channels=frozenset({"llm"}),
        channel_levels={"tool": logger.level("TRACE").no},
    ))
    logger.bind(channel="tool").warning("tool record")
    logger.bind(channel="llm").warning("llm record")
    logger.complete()
    text = (tmp_path / "ayder.log").read_text()
    assert "tool record" not in text
    assert "llm record" in text


def test_channel_level_none_disables_that_channel(tmp_path):
    setup_logging(_settings(tmp_path, level="DEBUG", channel_levels={"ui": None}))
    logger.bind(channel="ui").error("ui record")
    logger.bind(channel="core").error("core record")
    logger.complete()
    text = (tmp_path / "ayder.log").read_text()
    assert "ui record" not in text
    assert "core record" in text


def test_error_log_ignores_channel_selection(tmp_path):
    setup_logging(_settings(tmp_path, level="DEBUG", channels=frozenset({"llm"})))
    logger.bind(channel="tool").error("tool failure")
    logger.complete()
    assert "tool failure" in (tmp_path / "errors.log").read_text()


import argparse
import sys
from unittest.mock import MagicMock

import pytest

from ayder_cli.cli import build_logging_settings


def _args(**kw) -> argparse.Namespace:
    base = dict(logging_level=None, log_channel=None, trace=False, verbose=False)
    base.update(kw)
    return argparse.Namespace(**base)


def _cfg(**kw):
    cfg = MagicMock()
    cfg.logging_level = None
    cfg.logging_channels = {}
    cfg.logging_trace_enabled = False
    cfg.logging_file_enabled = True
    cfg.logging_file_path = ".ayder/log/ayder.log"
    cfg.logging_error_path = ".ayder/log/errors.log"
    cfg.logging_trace_path = ".ayder/log/trace.jsonl"
    cfg.logging_rotation = "10 MB"
    cfg.logging_retention = "7 days"
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


def test_build_settings_accepts_trace():
    assert build_logging_settings(_args(), _cfg(logging_level="TRACE")).level == "TRACE"


def test_channel_level_none_compiles_to_none_not_zero():
    """§C2: `"NONE"` in config becomes None in channel_levels — never 0."""
    s = build_logging_settings(_args(), _cfg(logging_channels={"ui": "NONE"}))
    assert s.channel_levels["ui"] is None         # `is None`, not `== 0`
    assert s.channels is None                     # the allowlist is a different field


def test_unknown_cli_channel_exits_one():
    """`--log-channel` is free text, so this is where a bad name must be caught.

    A bad channel in *config* never reaches here — Config's validator (step 03)
    rejects it at load time.
    """
    with pytest.raises(SystemExit) as exc:
        build_logging_settings(_args(log_channel="bogus"), _cfg())
    assert exc.value.code == 1


def test_verbose_without_a_level_resolves_to_info():
    s = build_logging_settings(_args(verbose=True), _cfg(logging_level=None))
    assert s.level == "INFO"
    assert s.console is True
    assert s.console_stream is sys.stdout


def test_cli_flag_beats_config():
    s = build_logging_settings(_args(logging_level="TRACE"), _cfg(logging_level="ERROR"))
    assert s.level == "TRACE"
