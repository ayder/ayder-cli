"""Compatibility controls for the private Loguru shapes the sinks depend on.

Mask-after-render needs Loguru's own file-sink machinery - rotation parsing,
the rename on rotate, retention pruning - and that machinery is private. §F5-R6
accepts the dependency against an explicit `loguru>=0.7,<0.8` bound PLUS a loud
guard that runs before anything is torn down.

These controls are the other half of that bargain. They pin the exact shapes
`logging_config` reads, so a Loguru upgrade that moves any of them turns this
file red with a named reason instead of silently producing unmasked log files.

Nothing here writes to a repository-owned path, and every test restores the
process-global logging state it touches, so the module passes serially and
under `-n auto` alike.
"""
import inspect
import re
import tempfile
from io import StringIO
from pathlib import Path

import pytest
from loguru import logger

from ayder_cli import logging_config
from ayder_cli.logging_config import (
    LoggingSettings,
    MaskingFileSink,
    _core_handlers,
    _loguru_private,
    _shape_guard,
    setup_logging,
)

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _restore_logging_state():
    """Every test here reconfigures process-global logging. Put it back.

    Loguru cannot re-add a removed handler, so "restore" means: return to the
    known-empty state and clear the three published values. That is exactly the
    safe state `setup_logging` itself publishes on failure, so no later test
    inherits a half-configured process.
    """
    root_handlers = logging_config.logging.root.handlers[:]
    try:
        yield
    finally:
        logger.remove()
        logging_config._sink_spec = None
        logging_config._configured = False
        logging_config._current_level = "NONE"
        logging_config.logging.root.handlers[:] = root_handlers


def _settings(tmp_path: Path, **kw) -> LoggingSettings:
    base = dict(
        file_path=str(tmp_path / "ayder.log"),
        error_path=str(tmp_path / "errors.log"),
        trace_path=str(tmp_path / "trace.jsonl"),
    )
    base.update(kw)
    return LoggingSettings(**base)


# -- the declared bound -------------------------------------------------------

def test_version_bound():
    """The private dependency is only defensible with the bound written down."""
    import loguru

    declared = [ln for ln in (REPO / "pyproject.toml").read_text().splitlines()
                if ln.strip().startswith('"loguru')]
    assert declared == ['    "loguru>=0.7,<0.8",'], declared

    major, minor = (int(p) for p in loguru.__version__.split(".")[:2])
    assert (major, minor) >= (0, 7), loguru.__version__
    assert (major, minor) < (0, 8), loguru.__version__


# -- the shapes themselves ----------------------------------------------------

def test_filesink_signature():
    """Every keyword the wrapper forwards, and the ones it relies on defaulting."""
    file_sink, _message, _stream = _loguru_private()
    params = set(inspect.signature(file_sink.__init__).parameters)
    assert logging_config._REQUIRED_FILE_SINK_PARAMS <= params, sorted(params)


def test_sink_protocol():
    file_sink, _message, _stream = _loguru_private()
    assert callable(getattr(file_sink, "write", None))
    assert callable(getattr(file_sink, "stop", None))


def test_message_shape():
    """`Message` is a str carrying `.record`; the wrapper rebuilds one per write."""
    _file_sink, message_cls, _stream = _loguru_private()
    assert issubclass(message_cls, str)
    assert message_cls.__slots__ == ("record",)
    out = message_cls("text")
    out.record = {"marker": 1}
    assert str(out) == "text" and out.record == {"marker": 1}


def test_streamsink_dispatch_flags():
    """The console shim's entire safety argument, asserted against the real class.

    `_MaskingStream` has no `stop`, and THAT is what stops `logger.remove()`
    from closing a stream the caller owns. If StreamSink ever stopped deriving
    the flag from the attribute, the shim would start closing somebody's stdout.
    """
    _file_sink, _message, stream_sink = _loguru_private()

    class _Stoppable:
        def write(self, text): pass
        def stop(self): pass

    class _Bare:
        def write(self, text): pass

    assert stream_sink(_Bare())._stoppable is False
    assert stream_sink(_Stoppable())._stoppable is True
    assert stream_sink(_Bare())._flushable is False
    assert stream_sink(StringIO())._flushable is True


def test_core_handlers_shape():
    """`would_reach_prose` reads this dict directly in the pre/failed state."""
    handlers = _core_handlers()
    assert isinstance(handlers, dict)
    logger.remove()
    sink_id = logger.add(StringIO(), level="WARNING")
    try:
        live = _core_handlers()
        assert sink_id in live
        assert all(isinstance(h.levelno, int) for h in live.values())
    finally:
        logger.remove(sink_id)


def test_write_roundtrip_with_rotation(tmp_path):
    """Rotation is the reason the wrapper delegates instead of reimplementing."""
    _file_sink, message_cls, _stream = _loguru_private()
    target = tmp_path / "rotating.log"
    sink = MaskingFileSink(str(target), rotation="1 KB", retention="7 days")
    try:
        for index in range(200):
            message = message_cls(f"line {index} token=abc123 " + "x" * 40 + "\n")
            message.record = {}
            sink.write(message)
    finally:
        sink.stop()

    produced = sorted(tmp_path.glob("rotating*.log"))
    assert len(produced) > 1, [p.name for p in produced]
    for path in produced:
        text = path.read_text()
        assert "token=abc123" not in text, path.name
        assert "<redacted:kv>" in text, path.name


def test_guard_no_side_effects(tmp_path, monkeypatch):
    """The guard probes in a temp dir and leaves neither files nor handlers."""
    monkeypatch.chdir(tmp_path)
    logger.remove()
    sink_id = logger.add(StringIO(), level="INFO")
    try:
        before = dict(_core_handlers())
        _shape_guard()
        assert dict(_core_handlers()) == before
    finally:
        logger.remove(sink_id)
    assert list(tmp_path.iterdir()) == []


# -- drift fails BEFORE the teardown boundary ---------------------------------

class _DriftedFileSink:
    """A FileSink whose constructor lost most of its keywords."""

    def __init__(self, path, rotation=None, retention=None):
        self._path = path

    def write(self, message): pass

    def stop(self): pass


class _DriftedMessage(str):
    __slots__ = ("record", "extra")


@pytest.mark.parametrize("drift, marker", [
    pytest.param("filesink", "FileSink.__init__ lost", id="filesink-signature"),
    pytest.param("message", "Message.__slots__", id="message-slots"),
])
def test_simulated_drift_raises_before_remove(tmp_path, monkeypatch, drift, marker):
    """Drift must be loud AND harmless: the previous sinks keep working.

    This is the ordering the guard exists for. Detecting drift after
    `logger.remove()` would leave the process with no sinks at all - the exact
    silent failure the no-silent-failure guarantee forbids.
    """
    file_sink, message_cls, stream_sink = _loguru_private()
    logger.remove()
    stream = StringIO()
    sink_id = logger.add(stream, level="INFO", format="{message}")

    if drift == "filesink":
        fake = (_DriftedFileSink, message_cls, stream_sink)
    else:
        fake = (file_sink, _DriftedMessage, stream_sink)
    monkeypatch.setattr(logging_config, "_loguru_private", lambda: fake)

    try:
        with pytest.raises(RuntimeError, match="Loguru drift") as excinfo:
            setup_logging(_settings(tmp_path, level="INFO"))
        assert marker in str(excinfo.value)

        # The old sink is still attached and still receiving records.
        assert sink_id in _core_handlers()
        logger.info("still alive")
        assert "still alive" in stream.getvalue()
    finally:
        logger.remove(sink_id)


def test_ordinary_path_failure_preserves_old_config(tmp_path):
    """A bad path is a configuration error, not a compatibility error - and it
    fails at construction, which is also before the teardown boundary."""
    logger.remove()
    stream = StringIO()
    sink_id = logger.add(stream, level="INFO", format="{message}")
    blocker = tmp_path / "blocker"
    blocker.write_text("I am a file, not a directory")

    try:
        with pytest.raises(OSError):
            setup_logging(_settings(tmp_path, level="INFO",
                                    error_path=str(blocker / "nested" / "errors.log")))
        assert sink_id in _core_handlers()
        logger.info("survivor")
        assert "survivor" in stream.getvalue()
        assert logging_config._sink_spec is None or logging_config._configured
    finally:
        logger.remove(sink_id)


def test_guard_rejects_a_sink_that_stops_masking(tmp_path, monkeypatch):
    """The round trip is the only check that proves masking still HAPPENS.

    Signatures and slots can all match while the rendered bytes go out raw, so
    the guard writes a credential through a real sink and reads it back.
    """
    file_sink, message_cls, stream_sink = _loguru_private()
    real_mask = logging_config.mask
    monkeypatch.setattr(logging_config, "mask", lambda text: text)
    try:
        with pytest.raises(RuntimeError, match="wrote raw text"):
            _shape_guard()
    finally:
        monkeypatch.setattr(logging_config, "mask", real_mask)
    assert (file_sink, message_cls, stream_sink) == _loguru_private()


def test_guard_wraps_unexpected_failures_as_named_drift(monkeypatch):
    """Anything the probe raises becomes one actionable RuntimeError."""
    def _boom():
        raise ImportError("loguru._file_sink is gone")

    monkeypatch.setattr(logging_config, "_loguru_private", _boom)
    with pytest.raises(RuntimeError, match="private sink probe failed with ImportError"):
        _shape_guard()


def test_no_temp_probe_files_survive():
    """`tempfile` cleanup is part of the contract: the guard runs on every setup."""
    before = set(Path(tempfile.gettempdir()).glob("probe.log"))
    _shape_guard()
    assert set(Path(tempfile.gettempdir()).glob("probe.log")) == before


def test_shape_guard_runs_on_every_setup(tmp_path, monkeypatch):
    """A guard that only ran once would not protect a re-configuration."""
    calls = []
    real = logging_config._shape_guard
    monkeypatch.setattr(logging_config, "_shape_guard",
                        lambda: (calls.append(1), real())[1])
    setup_logging(_settings(tmp_path, level="INFO"))
    setup_logging(_settings(tmp_path, level="DEBUG"))
    assert len(calls) == 2


def test_private_imports_are_confined_to_one_function():
    """One place to fix when Loguru moves, and one place for the guard to check."""
    source = (REPO / "src" / "ayder_cli" / "logging_config.py").read_text()
    private = re.findall(r"^\s*from loguru\.\S+ import .*$", source, re.M)
    assert len(private) == 3, private
    body = source.split("def _loguru_private()")[1].split("\ndef ")[0]
    for line in private:
        assert line in body, line
