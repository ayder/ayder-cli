"""Controls for the loguru_caplog fixture itself.

Every control is self-contained: no shared module state, no ordering
dependence, no inspection of loguru's private handler table, and no path
discovery. Leakage is proven behaviourally — emit after teardown and show the
capture did not grow.

The context manager is handed over by the `capture_loguru` fixture rather than
imported: `tests/` is a package, so pytest does not put it on `sys.path` and
`from conftest import ...` raises ModuleNotFoundError from any subdirectory.
"""
import pytest

from ayder_cli.log import get_logger


def test_captures_facade_records(loguru_caplog):
    get_logger("tool").info("hello {}", "world")
    assert loguru_caplog.text == "hello world"
    assert loguru_caplog.levels == ["INFO"]
    assert loguru_caplog.channels == {"tool"}


def test_exposes_native_record_fields(loguru_caplog):
    get_logger("llm").warning("boom")
    r = loguru_caplog.records[0]
    assert r["name"] == __name__
    assert r["level"].name == "WARNING"
    assert r["extra"]["channel"] == "llm"
    assert r["exception"] is None


def test_captures_exception_payload(loguru_caplog):
    try:
        raise ValueError("kaboom")
    except ValueError:
        get_logger("core").exception("failed")
    r = loguru_caplog.records[0]
    assert r["exception"] is not None
    assert r["exception"].type is ValueError


def test_trace_is_captured(loguru_caplog):
    get_logger("agent").trace("fine detail")
    assert loguru_caplog.levels == ["TRACE"]


def test_explicit_level_filtering(loguru_caplog):
    log = get_logger("core")
    log.debug("d"); log.info("i"); log.error("e")
    assert loguru_caplog.at_level("INFO").messages == ["i", "e"]
    assert loguru_caplog.only("ERROR").messages == ["e"]
    assert loguru_caplog.from_channel("core").messages == ["d", "i", "e"]
    assert loguru_caplog.from_channel("llm").messages == []


# -- isolation controls: each stands alone -----------------------------------

def test_sink_is_removed_on_normal_exit(capture_loguru):
    with capture_loguru() as cap:
        get_logger("ui").info("inside")
    assert cap.messages == ["inside"]
    before = len(cap)
    get_logger("ui").info("after")
    assert len(cap) == before, "sink survived normal exit"


def test_sink_is_removed_when_the_body_raises(capture_loguru):
    """This is the control that detects a missing `finally`.

    An exception propagating *through* the context manager is the only path
    where the `finally` matters; on every other path the cleanup line is
    reached anyway.
    """
    with pytest.raises(RuntimeError):
        with capture_loguru() as cap:
            get_logger("ui").info("inside")
            raise RuntimeError("boom")
    assert cap.messages == ["inside"]
    before = len(cap)
    get_logger("ui").info("after")
    assert len(cap) == before, "sink survived an exception"


def test_two_captures_do_not_bleed_into_each_other(capture_loguru):
    with capture_loguru() as outer:
        get_logger("core").info("a")
        with capture_loguru() as inner:
            get_logger("core").info("b")
        get_logger("core").info("c")
    assert inner.messages == ["b"]
    assert outer.messages == ["a", "b", "c"]
