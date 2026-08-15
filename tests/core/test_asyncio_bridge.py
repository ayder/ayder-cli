"""Asyncio diagnostics normalization, the stdlib bridge, and the last resort.

Three separable contracts, tested separately because they fail separately.

**B2-prime.** An asyncio `context["message"]` looks like framework text, but the
framework interpolates callback reprs into some of them - `Exception in callback
Handle(<function f at 0x…>, ('sk-…',))` is a real shape. So the allowlist is
EXACT: known constants pass verbatim, known prefixes keep the prefix and elide
the tail to a length, and anything else degrades to type/length metadata. A
message a newer Python adds degrades safely until it is reviewed in.

**Chaining.** Our handler logs a normalized record. A previous CUSTOM handler
then receives the ORIGINAL context and its own stdlib records stay visible - it
belongs to someone else. With no previous handler we call CPython's default one,
flagged, so the bridge can drop exactly that one raw copy instead of printing
unnormalized context reprs beside our normalized record.

**Last resort.** A DIAGNOSTIC record - WARNING+ or one carrying an exception -
that no prose sink would receive goes to stderr through a fixed project
formatter, masked. Records below that bar which nothing accepts are deliberately
silent: level NONE, a channel allowlist and per-channel thresholds are the
operator turning output OFF, not output going missing. That path exists because
logging is already broken, so it is exception-total: hostile messages, hostile
tracebacks, a closed stderr and a reentrant record all degrade to fixed safe
text.
"""
import asyncio
import io
import logging
import sys
from pathlib import Path

import pytest
from loguru import logger

from ayder_cli import diagnostics, logging_config
from ayder_cli.diagnostics import (
    _ASYNCIO_MESSAGES,
    _ASYNCIO_PREFIXES,
    _normalize_asyncio_message,
    _safe_type_name,
    install_asyncio_handler,
)
from ayder_cli.log import flush, level_no
from ayder_cli.logging_config import (
    LoggingSettings,
    _bound_label,
    _bound_token,
    _in_default_asyncio_handler,
    _InterceptHandler,
    _REENTRANT_NOTICE,
    _stderr_fallback,
    setup_logging,
    would_reach_prose,
)


@pytest.fixture(autouse=True)
def _restore_logging_state():
    """Converge on the safe state after every test, exactly as a failed setup
    would, so no test inherits another's sinks or bridge."""
    root_handlers = logging.root.handlers[:]
    try:
        yield
    finally:
        logger.remove()
        logging_config._sink_spec = None
        logging_config._configured = False
        logging_config._current_level = "NONE"
        logging.root.handlers[:] = root_handlers


def _settings(tmp_path: Path, **kw) -> LoggingSettings:
    base = dict(
        file_path=str(tmp_path / "ayder.log"),
        error_path=str(tmp_path / "errors.log"),
        trace_path=str(tmp_path / "trace.jsonl"),
    )
    base.update(kw)
    return LoggingSettings(**base)


def _all_off() -> None:
    """The state the fallback exists for: no sinks, nothing published."""
    logger.remove()
    logging_config._sink_spec = None
    logging_config._configured = False
    logging_config._current_level = "NONE"


# ================================================================== B2-prime

def test_b2prime_constants_pass_verbatim():
    """Reviewed framework text is worth keeping - it is what makes the log
    readable - so all twenty pass through unchanged."""
    assert len(_ASYNCIO_MESSAGES) == 20
    for message in _ASYNCIO_MESSAGES:
        assert _normalize_asyncio_message(message) == message, message


def test_b2prime_prefix_elides_tail():
    """The prefix is framework text; the tail is the repr that leaks."""
    leaky = "Exception in callback Handle(<function f at 0x7f>, ('sk-abcdefghij',))"
    out = _normalize_asyncio_message(leaky)
    assert out == "Exception in callback <48 chars elided>", out
    assert "sk-abcdefghij" not in out


@pytest.mark.parametrize("prefix", _ASYNCIO_PREFIXES)
def test_b2prime_every_prefix_elides(prefix):
    out = _normalize_asyncio_message(prefix + "secret-tail")
    assert out == f"{prefix}<11 chars elided>", out


def test_b2prime_unknown_string_metadata():
    """Length is a diagnostic; the text is not trusted."""
    assert _normalize_asyncio_message("token=abc123") == "<str, 12 chars>"


def test_b2prime_none_uses_default():
    assert _normalize_asyncio_message(None) == "asyncio error"


def test_b2prime_falsy_nonstring():
    """`0` is falsy but not absent: it must not be mistaken for a missing key."""
    assert _normalize_asyncio_message(0) == "<int, 1 chars>"


def test_b2prime_hostile_str_raises_degrades():
    class _Hostile:
        def __str__(self): raise RuntimeError("nope")

    assert _normalize_asyncio_message(_Hostile()) == "<_Hostile, unprintable>"


def test_b2prime_near_match_degrades():
    """Exact membership, not `startswith`: a near-match is not the constant."""
    near = "Task was destroyed but it is pending! extra sk-abcdefghij"
    out = _normalize_asyncio_message(near)
    assert out == f"<str, {len(near)} chars>"
    assert "sk-abcdefghij" not in out


def test_b2prime_hostile_class_name_and_str():
    """A crafted class name is caller-reachable text: bound it, do not print it."""
    class _Evil:
        def __str__(self): raise RuntimeError("nope")

    _Evil.__qualname__ = "evil\nsk-abcdefgh123 injected"
    out = _normalize_asyncio_message(_Evil())
    assert out == "<_Evil, unprintable>", out
    assert "\n" not in out
    assert "sk-abcdefgh123" not in out


@pytest.mark.parametrize("name, expected", [
    pytest.param("Ordinary", "Ordinary", id="identifier"),
    pytest.param("has space", "object", id="not-an-identifier"),
    pytest.param("x" * 65, "object", id="too-long"),
])
def test_safe_type_name_bounds(name, expected):
    class _Probe:
        pass

    _Probe.__name__ = name
    assert _safe_type_name(_Probe()) == expected


def test_callback_repr_leak_masked(tmp_path):
    """The naive-B2 defeater, end to end: a credential inside a callback repr
    must not reach the log even though the message LOOKS like framework text."""
    setup_logging(_settings(tmp_path, level="NONE"))
    diagnostics._handle_asyncio(None, {
        "message": "Exception in callback Handle(<f>, ('api_key=sk-abcdefghij',))",
    })
    flush()

    text = (tmp_path / "errors.log").read_text()
    assert "sk-abcdefghij" not in text
    assert "Exception in callback <" in text


def test_asyncio_levels_and_stack_are_unchanged(tmp_path):
    """Normalization changes the MESSAGE only: level and traceback survive."""
    setup_logging(_settings(tmp_path, level="NONE"))
    diagnostics._handle_asyncio(None, {"message": "boom",
                                       "exception": RuntimeError("inner")})
    flush()

    text = (tmp_path / "errors.log").read_text()
    assert "CRITICAL" in text
    assert "RuntimeError" in text and "inner" in text


# ================================================================== chaining

def test_default_copy_deduplicated_exactly(tmp_path, capsys):
    """CPython's default handler emits a raw copy of an event we already logged
    in normalized form. Exactly that record is dropped."""
    setup_logging(_settings(tmp_path, level="DEBUG"))
    capsys.readouterr()

    async def _main():
        loop = asyncio.get_running_loop()
        install_asyncio_handler(loop)
        loop.call_exception_handler({"message": "token=abc123leaked"})

    asyncio.run(_main())
    flush()

    main = (tmp_path / "ayder.log").read_text()
    errors = (tmp_path / "errors.log").read_text()
    assert "abc123leaked" not in main + errors
    # One record per sink - and NOT a second, unnormalized one from CPython's
    # default handler, which is the copy the flag identifies and drops.
    assert main.count("Unhandled asyncio error") == 1, main
    assert errors.count("Unhandled asyncio error") == 1, errors


def test_custom_handler_receives_original_context():
    """A previous handler belongs to someone else: it gets the real context."""
    seen = []

    async def _main():
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(lambda lp, ctx: seen.append(ctx))
        install_asyncio_handler(loop)
        loop.call_exception_handler({"message": "raw text", "custom": 7})

    asyncio.run(_main())
    flush()

    assert len(seen) == 1
    assert seen[0]["message"] == "raw text", "the custom handler must not be normalized"
    assert seen[0]["custom"] == 7


def test_custom_handler_own_stdlib_log_visible(tmp_path):
    """The de-dup flag is narrow ON PURPOSE: a custom handler's own stdlib
    records are not ours to suppress."""
    setup_logging(_settings(tmp_path, level="DEBUG"))

    def _previous(lp, ctx):
        logging.getLogger("embedder").error("custom handler still speaks")

    async def _main():
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(_previous)
        install_asyncio_handler(loop)
        loop.call_exception_handler({"message": "whatever"})

    asyncio.run(_main())
    flush()

    assert "custom handler still speaks" in (tmp_path / "ayder.log").read_text()


def test_asyncio_default_call_skipped_before_setup(capsys):
    """Pre-setup there is no bridge to identify the raw copy, so calling the
    default handler would print unnormalized reprs through `lastResort`."""
    _all_off()
    called = []

    async def _main():
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(None)
        install_asyncio_handler(loop)
        original = loop.default_exception_handler
        loop.default_exception_handler = lambda ctx: called.append(ctx)
        try:
            loop.call_exception_handler({"message": "token=abc123leaked"})
        finally:
            loop.default_exception_handler = original

    asyncio.run(_main())
    assert called == [], "the default handler must not run before setup"
    assert "abc123leaked" not in capsys.readouterr().err


def test_flag_is_cleared_after_the_default_call(tmp_path):
    """A leaked flag would silently drop every later bridge record."""
    setup_logging(_settings(tmp_path, level="DEBUG"))

    async def _main():
        loop = asyncio.get_running_loop()
        install_asyncio_handler(loop)
        loop.call_exception_handler({"message": "boom"})

    asyncio.run(_main())
    assert _in_default_asyncio_handler.get() is False

    logging.getLogger("after").error("still bridged")
    flush()
    assert "still bridged" in (tmp_path / "ayder.log").read_text()


# ============================================================== the last resort

def test_all_off_sanitized_stderr_fallback(capsys):
    """Every sink off: the diagnostic still surfaces, normalized and masked."""
    _all_off()
    diagnostics._handle_asyncio(None, {"message": "token=abc123leaked"})

    err = capsys.readouterr().err
    assert "ERROR ayder.core: <str, 18 chars>" in err, err
    assert "abc123leaked" not in err


def test_fallback_masks_known_shapes(capsys):
    """The fallback renders, then masks - same order as the file sinks."""
    _all_off()
    _stderr_fallback("ERROR", "ayder.core", "Authorization: Bearer zz9", None)

    err = capsys.readouterr().err
    assert "<redacted:auth>" in err
    assert "zz9" not in err


def test_fallback_carries_exception_type_and_traceback(capsys):
    """Stack visibility is preserved when there are no sinks to preserve it."""
    _all_off()
    try:
        raise ValueError("credential token=abc123leaked")
    except ValueError as e:
        _stderr_fallback("CRITICAL", "ayder.core", "asyncio error",
                         (type(e), e, e.__traceback__))

    err = capsys.readouterr().err
    assert "ValueError" in err and "Traceback" in err
    assert "abc123leaked" not in err


def test_fallback_traceback_render_failure_degrades(capsys):
    """A hostile traceback object must not take the last resort down with it."""
    _all_off()
    _stderr_fallback("ERROR", "ayder.core", "asyncio error",
                     (ValueError, ValueError("x"), "not-a-traceback"))

    err = capsys.readouterr().err
    assert "<traceback unavailable>" in err, err
    assert "ERROR ayder.core: asyncio error" in err


def test_fallback_build_failure_emits_fixed_last_resort(capsys):
    """If even building the line fails, emit fixed text rather than nothing."""
    class _Hostile:
        def __str__(self): raise RuntimeError("nope")

    _all_off()
    _stderr_fallback("ERROR", "ayder.core", _Hostile(), None)
    assert capsys.readouterr().err == "ayder logging: diagnostic record unavailable\n"


@pytest.mark.parametrize("failure", [
    pytest.param(ValueError("I/O operation on closed file"), id="closed-stream"),
    pytest.param(UnicodeEncodeError("utf-8", "x", 0, 1, "bad"), id="encoding"),
    pytest.param(OSError("device gone"), id="oserror"),
])
def test_fallback_write_failures_are_swallowed(monkeypatch, failure):
    """Diagnostics never crash the process they are diagnosing."""
    class _Broken(io.StringIO):
        def write(self, text): raise failure

    _all_off()
    monkeypatch.setattr(sys, "stderr", _Broken())
    _stderr_fallback("ERROR", "ayder.core", "asyncio error", None)   # must not raise


def test_fallback_never_calls_stdlib_logging():
    """A logging call on this path would recurse straight back into the bridge."""
    import ast

    source = Path(logging_config.__file__).read_text()
    tree = ast.parse(source)
    target = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "_stderr_fallback")
    for node in ast.walk(target):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"debug", "info", "warning", "error",
                                          "critical", "exception", "log"}, \
                ast.unparse(node)
        if isinstance(node, ast.Name):
            assert node.id not in {"logging", "logger"}, ast.unparse(node)


# ================================================================ the bridge

def test_bridge_forwards_and_bounds(tmp_path):
    """The ordinary path is unchanged: stdlib records still reach the sinks."""
    setup_logging(_settings(tmp_path, level="DEBUG"))
    logging.getLogger("httpx").error("upstream said no")
    flush()
    assert "upstream said no" in (tmp_path / "ayder.log").read_text()


def _record(name="evil.logger", level=logging.ERROR, msg="m", args=()):
    return logging.LogRecord(name, level, __file__, 1, msg, args, None)


def test_hostile_getmessage_degrades_fixed_content(capsys):
    """A record whose formatter raises degrades to fixed text - and the payload
    it wanted to print never reaches stderr."""
    _all_off()

    class _Hostile(logging.LogRecord):
        def getMessage(self):
            raise RuntimeError("token=abc123leaked")

    _InterceptHandler().emit(_Hostile("evil.logger", logging.ERROR, __file__, 1,
                                      "x", (), None))
    err = capsys.readouterr().err
    assert "ERROR evil.logger: <unformattable stdlib record>" in err, err
    assert "abc123leaked" not in err


def test_getmessage_called_at_most_once(tmp_path):
    """The forward and the fallback share ONE computed value; calling twice
    would run a hostile formatter twice and could yield two different texts."""
    setup_logging(_settings(tmp_path, level="NONE"))
    calls = []

    class _Counting(logging.LogRecord):
        def getMessage(self):
            calls.append(1)
            return "counted"

    _InterceptHandler().emit(_Counting("lib", logging.INFO, __file__, 1, "x",
                                       (), None))
    flush()
    assert len(calls) == 1, calls


def test_reentrancy_latch_drops_with_safe_notice(capsys):
    """A sink that logs through stdlib would recurse forever. The re-entrant
    record is dropped and the notice carries NO record content at all."""
    _all_off()
    handler = _InterceptHandler()

    class _Reentrant(logging.LogRecord):
        def getMessage(self):
            handler.emit(_record(name="inner.secret", msg="token=abc123leaked"))
            return "outer"

    handler.emit(_Reentrant("outer.logger", logging.ERROR, __file__, 1, "x",
                            (), None))
    err = capsys.readouterr().err
    assert _REENTRANT_NOTICE in err, err
    assert "abc123leaked" not in err
    assert "inner.secret" not in err, "the notice must be content-free"


def test_latch_is_released_after_a_drop(capsys):
    """A latch that stuck would silently drop every later stdlib record."""
    _all_off()
    handler = _InterceptHandler()

    class _Reentrant(logging.LogRecord):
        def getMessage(self):
            handler.emit(_record())
            return "outer"

    handler.emit(_Reentrant("outer", logging.ERROR, __file__, 1, "x", (), None))
    capsys.readouterr()

    handler.emit(_record(name="later", msg="visible again"))
    assert "visible again" in capsys.readouterr().err


@pytest.mark.parametrize("name, expected", [
    pytest.param("ERROR", "ERROR", id="standard"),
    pytest.param("SHOUTY", "LEVEL 55", id="custom-level-name"),
])
def test_fallback_label_is_bounded(name, expected):
    record = _record()
    record.levelname = name
    record.levelno = 55 if name == "SHOUTY" else record.levelno
    assert _bound_label(record) == expected


def test_fallback_name_is_bounded():
    """A logger name is arbitrary caller text; it may not forge a second line."""
    assert "\n" not in _bound_token("evil\nERROR fake: injected")
    assert _bound_token("evil\nx") == "evil?x"
    assert len(_bound_token("y" * 500)) == 200


@pytest.mark.parametrize("level, channels", [
    pytest.param("NONE", None, id="level-none"),
    pytest.param("INFO", frozenset({"core"}), id="channel-excluded"),
])
def test_below_warning_external_stays_silent(tmp_path, capsys, level, channels):
    """Deliberate silence stays silent.

    An INFO record the level or the channel allowlist excluded is not a lost
    diagnostic - it is output the operator turned off. Routing it to stderr
    would put httpx's per-request chatter on the terminal of every default run,
    and through Textual's display in the TUI.
    """
    setup_logging(_settings(tmp_path, level=level, channels=channels))
    capsys.readouterr()

    logging.getLogger("httpx").info("routine chatter")
    flush()

    assert "routine chatter" not in capsys.readouterr().err
    main = tmp_path / "ayder.log"
    assert "routine chatter" not in (main.read_text() if main.exists() else "")


def test_excluded_warning_reaches_errors_log_without_duplicating(tmp_path, capsys):
    """A WARNING the allowlist excluded is still a diagnostic - but errors.log
    already takes it, so the fallback must NOT fire and double-report it."""
    setup_logging(_settings(tmp_path, level="INFO", channels=frozenset({"core"})))
    capsys.readouterr()

    logging.getLogger("httpx").warning("upstream degraded")
    flush()

    assert "upstream degraded" in (tmp_path / "errors.log").read_text()
    assert "upstream degraded" not in capsys.readouterr().err


def test_external_warning_with_every_prose_sink_off_falls_back_once(tmp_path, capsys):
    """The state the fallback exists for: nothing configured can take it."""
    setup_logging(LoggingSettings(level="INFO", file_enabled=False, console=False))
    capsys.readouterr()

    logging.getLogger("httpx").warning("degraded token=abc123leaked")
    flush()

    err = capsys.readouterr().err
    assert err.count("WARNING httpx:") == 1, err
    assert "<redacted:kv>" in err
    assert "abc123leaked" not in err


def test_below_warning_with_exception_still_falls_back(capsys):
    """`exc_info` is what makes a record diagnostic, independent of level.

    Every prose sink is off, so nothing can take it: a DEBUG record carrying a
    traceback must still surface rather than being treated as chatter.
    """
    setup_logging(LoggingSettings(level="INFO", file_enabled=False, console=False))
    capsys.readouterr()

    try:
        raise ValueError("inner failure")
    except ValueError:
        # NOT one of _SUPPRESSED_LIBS: those are floored at INFO by stdlib, so
        # a DEBUG record on them never reaches the bridge at all.
        logging.getLogger("some.lib").debug("low severity", exc_info=True)
    flush()

    err = capsys.readouterr().err
    assert "DEBUG some.lib: low severity" in err, err
    assert "ValueError" in err and "inner failure" in err


def test_no_duplicate_when_the_record_does_reach_prose(tmp_path, capsys):
    """The predicate's whole job: no fallback when a sink already has it."""
    setup_logging(_settings(tmp_path, level="DEBUG"))
    capsys.readouterr()

    logging.getLogger("httpx").error("routed normally")
    flush()

    assert "routed normally" in (tmp_path / "ayder.log").read_text()
    assert "routed normally" not in capsys.readouterr().err


def test_failed_setup_state_predicate_false(tmp_path, monkeypatch, capsys):
    """After a failed setup the bridge keeps running against zero handlers, so
    diagnostics survive only because the fallback activates."""
    setup_logging(_settings(tmp_path, level="INFO"))
    monkeypatch.setattr(logging_config.logger, "add",
                        lambda *a, **k: (_ for _ in ()).throw(ValueError("refused")))
    with pytest.raises(ValueError):
        setup_logging(_settings(tmp_path, level="INFO"))
    capsys.readouterr()

    assert would_reach_prose("external", level_no("ERROR"), False) is False
    diagnostics._handle_asyncio(None, {"message": "asyncio error"})
    assert "ERROR ayder.core: asyncio error" in capsys.readouterr().err


@pytest.mark.parametrize("level, channels, has_exc, channel, expected", [
    pytest.param("DEBUG", None, False, "core", True, id="file-on-debug"),
    pytest.param("NONE", None, False, "core", False, id="level-none-plain"),
    pytest.param("NONE", None, True, "core", True, id="level-none-exception"),
    pytest.param("INFO", frozenset({"core"}), False, "external", False,
                 id="channel-excluded"),
    pytest.param("INFO", frozenset({"core"}), True, "external", True,
                 id="channel-excluded-but-exception"),
])
def test_predicate_matrix(tmp_path, level, channels, has_exc, channel, expected):
    setup_logging(_settings(tmp_path, level=level, channels=channels))
    assert would_reach_prose(channel, level_no("INFO"), has_exc) is expected
