from pathlib import Path

from loguru import logger

from ayder_cli.log import get_logger
from ayder_cli.logging_config import LoggingSettings, setup_logging


def test_benign_debug_exception_still_reaches_error_log(tmp_path: Path):
    """Level and traceback are independent: DEBUG + exception still lands."""
    setup_logging(LoggingSettings(
        level="NONE",
        file_path=str(tmp_path / "ayder.log"),
        error_path=str(tmp_path / "errors.log"),
        trace_path=str(tmp_path / "trace.jsonl"),
    ))
    log = get_logger("tool")
    try:
        raise RuntimeError("benign but recorded")
    except RuntimeError:
        log.opt(exception=True).debug("recovered")
    logger.complete()

    text = (tmp_path / "errors.log").read_text()
    assert "benign but recorded" in text
    assert "RuntimeError" in text
