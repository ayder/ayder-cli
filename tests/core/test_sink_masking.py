"""Credential masking in every rendered prose sink, and the setup state machine.

Two halves, both required by §F5-R6.

The first half pins `mask()` itself against the frozen 62-case vector table -
the exact inputs and outputs the rule order was designed against. Masking is
ordered (url -> auth -> bearer -> sk -> kv) and the order is load-bearing, so
the table is the contract, not an illustration.

The second half asserts the property that actually matters: credentials do not
appear in the BYTES of ayder.log, errors.log or the console, including the
places a naive `mask(str(exc))` would miss - exception notes, an SDK object's
`__str__`, and the source lines Loguru renders inside a traceback. Trace JSONL
is asserted to stay RAW: it is machine-read structured output, and masking it
would corrupt the schema.

The state-machine tests then pin the transactional guarantee: every setup
failure converges either to the previous configuration fully intact, or to the
explicit None/False/NONE safe state - never to a half-configured process that
silently drops records.
"""
import json
import os
import time
from io import StringIO
from pathlib import Path

import pytest
from loguru import logger

from ayder_cli import logging_config
from ayder_cli.log import emit_event, flush, get_logger, level_no
from ayder_cli.logging_config import (
    LoggingSettings,
    MaskingFileSink,
    _core_handlers,
    _loguru_private,
    _MaskingStream,
    setup_logging,
    would_reach_prose,
)
from ayder_cli.masking import MASK_RULES, mask

# The exact table from the executed round-4 probe, transcribed verbatim. Every
# row is `mask()`'s real output under the frozen rule order; all 62 are
# idempotent and preserve newline counts.
MASK_VECTORS: tuple[tuple[str, str], ...] = (
    ('Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.PAYLOAD.SIG', 'Authorization: <redacted:auth>'),
    ('https://user:token=abc@host/path', 'https://user:<redacted:url>@host/path'),
    ('deauthorization: xyz', 'deauthorization: xyz'),
    ('https://token:pw@host/path', 'https://token:<redacted:url>@host/path'),
    ('Bearer abc123', '<redacted:bearer>'),
    ('bearer abc123', '<redacted:bearer>'),
    ('BEARER eyJhbGciOiJIUzI1NiJ9.PAYLOAD.SIG', '<redacted:bearer>'),
    ("Bearer 'quoted.tok'", '<redacted:bearer>'),
    ('Bearer\tabc', '<redacted:bearer>'),
    ('Bearer\nnextline', 'Bearer\nnextline'),
    ('Bearer \r\nnext', 'Bearer \r\nnext'),
    ('Bearer abc123, then prose', '<redacted:bearer>, then prose'),
    ('(Bearer abc.123) t', '(<redacted:bearer>) t'),
    ('unbearable torch-bearer here', 'unbearable torch-bearer here'),
    ('Bearerabc', 'Bearerabc'),
    ('Bearer', 'Bearer'),
    ('Bearer  ', 'Bearer  '),
    ('The Bearer of bad news', 'The <redacted:bearer> bad news'),
    ('Authorization: Basic dXNlcjpwdw==', 'Authorization: <redacted:auth>'),
    ('authorization=Basic dXNlcjpwdw==', 'authorization=<redacted:auth>'),
    ('Authorization: Digest username="u", response="abc"', 'Authorization: <redacted:auth>'),
    ('Proxy-Authorization: Bearer tok123', 'Proxy-Authorization: <redacted:auth>'),
    ('de-authorization: xyz', 'de-authorization: <redacted:auth>'),
    ('reauthorization: xyz', 'reauthorization: xyz'),
    ('AUTHORIZATION:  Token abc123', 'AUTHORIZATION:  <redacted:auth>'),
    ('Authorization: https://u:pw@h/x', 'Authorization: <redacted:auth>'),
    ('Authorization: Basic abc\nnext line', 'Authorization: <redacted:auth>\nnext line'),
    ('sk-abcdefgh', '<redacted:sk>'),
    ('sk-proj-abc123def456', '<redacted:sk>'),
    ('sk-ant-api03-xyzXYZ_-089', '<redacted:sk>'),
    ('api_key=sk-proj-abc123def456', 'api_key=<redacted:sk>'),
    ('prefix:sk-abcdefghij', 'prefix:<redacted:sk>'),
    ('(sk-abcdefghij)', '(<redacted:sk>)'),
    ('sk-abcdefghij.suffix', '<redacted:sk>.suffix'),
    ('sk-abcdefghij/next', '<redacted:sk>/next'),
    ('task-force-12345678', 'task-force-12345678'),
    ('risk-management-plan', 'risk-management-plan'),
    ('disk-usage-report-01', 'disk-usage-report-01'),
    ('desk-assignment-42x9', 'desk-assignment-42x9'),
    ('ask-followup-question', 'ask-followup-question'),
    ('brisk-walking-routine', 'brisk-walking-routine'),
    ('sk-short', 'sk-short'),
    ('api_key= abc123', 'api_key= <redacted:kv>'),
    ('API-KEY: abc123', 'API-KEY: <redacted:kv>'),
    ('aPiKeY = abc123', 'aPiKeY = <redacted:kv>'),
    ('apikey:v', 'apikey:<redacted:kv>'),
    ('token: abc123', 'token: <redacted:kv>'),
    ("secret='s3cr3t'", 'secret=<redacted:kv>'),
    ('password="hunter 2"', 'password=<redacted:kv>'),
    ('passwd=abc', 'passwd=<redacted:kv>'),
    ('refresh_token=abc123', 'refresh_token=<redacted:kv>'),
    ('token=abc@host/path', 'token=<redacted:kv>'),
    ('the token:\nnext line', 'the token:\nnext line'),
    ('The token: concept explained', 'The token: <redacted:kv> explained'),
    ('token = ', 'token = '),
    ('a token appears in prose', 'a token appears in prose'),
    ('https://user:password@host/path', 'https://user:<redacted:url>@host/path'),
    ('postgres://u:p@h/db', 'postgres://u:<redacted:url>@h/db'),
    ('https://host/path?q=1', 'https://host/path?q=1'),
    ('http://user@host/', 'http://user@host/'),
    ('X-Auth: token=sk-abcdefghijkl then Authorization: Bearer zz9', 'X-Auth: token=<redacted:sk> then Authorization: <redacted:auth>'),
    ('line1 ok\nAuthorization: Basic abc\nline3 ok', 'line1 ok\nAuthorization: <redacted:auth>\nline3 ok'),
)


class _SinkBoom(RuntimeError):
    """Raised only by fixture sinks, never by production code."""


@pytest.fixture(autouse=True)
def _restore_logging_state():
    """Return the process to the safe state after every test.

    Loguru cannot re-add a removed handler, so restoration means converging on
    the same None/False/NONE state a failed setup publishes. Without this, a
    lifecycle test that deliberately leaves a broken configuration would leak
    it into every test that follows in this worker.
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


def _setup(tmp_path: Path, **kw) -> str:
    return setup_logging(_settings(tmp_path, **kw))


# ============================================================ the mask contract

def test_mask_final_order_table():
    """All 62 frozen vectors, exact input -> exact output."""
    wrong = [(i, mask(i), o) for i, o in MASK_VECTORS if mask(i) != o]
    assert not wrong, wrong
    assert len(MASK_VECTORS) == 62


def test_mask_idempotent_battery():
    """Masking a masked string must be a no-op: sinks may render more than once,
    and the `(?!<redacted:)` lookahead is what guarantees it."""
    for text, expected in MASK_VECTORS:
        once = mask(text)
        assert mask(once) == once == expected, text


def test_mask_preserves_newline_counts():
    """Line structure is never altered - a mask that ate a newline would merge
    two log lines into one and corrupt every downstream reader."""
    for text, _expected in MASK_VECTORS:
        out = mask(text)
        assert out.count("\n") == text.count("\n"), repr(text)
        assert out.count("\r") == text.count("\r"), repr(text)


def test_rule_order_is_frozen():
    """The order IS the contract; a reordering silently changes every output."""
    assert [name for name, _p, _r in MASK_RULES] == [
        "url", "auth", "bearer", "sk", "kv"]


def test_url_before_kv_preserves_authority():
    """The ordering bug this fixes: `kv` seeing a URL password first would eat
    the authority and leave the host unreadable."""
    assert mask("https://user:token=abc@host/path") == \
        "https://user:<redacted:url>@host/path"
    # A `token` USERNAME must not tempt kv into re-masking an already-masked
    # value; the lookahead blocks it.
    assert mask("https://token:pw@host/path") == \
        "https://token:<redacted:url>@host/path"


def test_proxy_authorization_masked():
    assert mask("Proxy-Authorization: Bearer tok123") == \
        "Proxy-Authorization: <redacted:auth>"


def test_deauthorization_untouched():
    """The left boundary excludes `_` and alphanumerics but NOT `-`, so a real
    `Proxy-Authorization` header masks while an English word does not."""
    assert mask("deauthorization: xyz") == "deauthorization: xyz"
    assert mask("reauthorization: xyz") == "reauthorization: xyz"


def test_sk_family_masks_and_boundaries():
    for text in ("sk-abcdefgh", "sk-proj-abc123def456", "sk-ant-api03-xyzXYZ_-089"):
        assert mask(text) == "<redacted:sk>", text
    assert mask("sk-abcdefghij.suffix") == "<redacted:sk>.suffix"
    assert mask("(sk-abcdefghij)") == "(<redacted:sk>)"
    assert mask("sk-short") == "sk-short"


def test_sk_near_miss_words_survive():
    """Ordinary English must not be shredded by the `sk-` family."""
    for word in ("task-force-12345678", "risk-management-plan",
                 "disk-usage-report-01", "desk-assignment-42x9",
                 "ask-followup-question", "brisk-walking-routine"):
        assert mask(word) == word, word


def test_bearer_case_insensitive_and_boundary():
    for text in ("Bearer abc123", "bearer abc123", "BEARER abc123"):
        assert mask(text) == "<redacted:bearer>", text
    assert mask("unbearable torch-bearer here") == "unbearable torch-bearer here"
    assert mask("Bearerabc") == "Bearerabc"


def test_bearer_newline_near_miss_safe():
    """LF and CRLF both terminate the glue, so a bare `Bearer` at end of line
    cannot swallow the next line's content."""
    assert mask("Bearer\nnextline") == "Bearer\nnextline"
    assert mask("Bearer \r\nnext") == "Bearer \r\nnext"


def test_authorization_line_schemes():
    for scheme in ("Basic dXNlcjpwdw==", "Token abc123",
                   'Digest username="u", response="abc"'):
        assert mask(f"Authorization: {scheme}") == "Authorization: <redacted:auth>"


def test_kv_spellings_and_suffix_keys():
    assert mask("api_key= abc123") == "api_key= <redacted:kv>"
    assert mask("API-KEY: abc123") == "API-KEY: <redacted:kv>"
    assert mask("aPiKeY = abc123") == "aPiKeY = <redacted:kv>"
    assert mask("secret='s3cr3t'") == "secret=<redacted:kv>"
    assert mask('password="hunter 2"') == "password=<redacted:kv>"
    # A leaked refresh token is a credential, so the SUFFIX key fires too - and
    # the key text is preserved, exactly like the other kv spellings.
    assert mask("refresh_token=abc123") == "refresh_token=<redacted:kv>"


def test_kv_newline_glue_safe():
    """Prose ending in `token:` must not consume the following line."""
    assert mask("the token:\nnext line") == "the token:\nnext line"
    assert mask("token = ") == "token = "
    assert mask("a token appears in prose") == "a token appears in prose"


def test_url_userinfo_masked():
    assert mask("https://user:password@host/path") == \
        "https://user:<redacted:url>@host/path"
    assert mask("postgres://u:p@h/db") == "postgres://u:<redacted:url>@h/db"
    assert mask("https://host/path?q=1") == "https://host/path?q=1"
    assert mask("http://user@host/") == "http://user@host/"


def test_mask_linear_time_bound():
    """Every pattern is single-quantifier; hostile input cannot make it backtrack.

    The bound is deliberately loose - this catches catastrophic backtracking
    (which would take minutes), not a slow machine.
    """
    hostile = ("sk-" * 20000) + ("bearer " * 30000) + ("token= " * 30000) + ("x" * 1_000_000)
    start = time.perf_counter()
    mask(hostile)
    assert time.perf_counter() - start < 10.0


def test_mask_is_pure_text_and_never_logs():
    """A logging call inside `mask` would recurse through the sink calling it."""
    source = (Path(logging_config.__file__).parent / "masking.py").read_text()
    for forbidden in ("import logging", "from loguru", "logger.", "print("):
        assert forbidden not in source, forbidden


# ====================================================== rendered sink contents

def test_masked_ayder_log_rendered_output(tmp_path):
    _setup(tmp_path, level="DEBUG")
    get_logger("core").info("calling with Authorization: Bearer {}", "eyJab.PAY.SIG")
    flush()

    text = (tmp_path / "ayder.log").read_text()
    assert "<redacted:auth>" in text
    assert "eyJab.PAY.SIG" not in text


def test_masked_errors_log_rendered_output(tmp_path):
    _setup(tmp_path, level="NONE")
    get_logger("core").error("upstream rejected api_key=sk-abcdefghijkl")
    flush()

    text = (tmp_path / "errors.log").read_text()
    assert "<redacted:sk>" in text
    assert "sk-abcdefghijkl" not in text


def test_masked_console_rendered_output(tmp_path):
    stream = StringIO()
    _setup(tmp_path, level="INFO", console=True, console_stream=stream)
    get_logger("core").info("token: {}", "abc123secret")
    flush()

    out = stream.getvalue()
    assert "<redacted:kv>" in out
    assert "abc123secret" not in out


def _raise_with_credential():
    raise RuntimeError("upstream rejected token=abc123secret")


def test_exception_string_and_notes_masked(tmp_path):
    """The vector a naive `mask(message)` misses entirely: the credential is in
    the exception's own text and in a note, not in the format string."""
    _setup(tmp_path, level="NONE")
    try:
        _raise_with_credential()
    except RuntimeError as e:
        e.add_note("retry with Authorization: Bearer zzz999")
        get_logger("core").opt(exception=True).error("call failed")
    flush()

    text = (tmp_path / "errors.log").read_text()
    assert "abc123secret" not in text
    assert "zzz999" not in text
    assert "<redacted:kv>" in text


def test_traceback_source_line_masked(tmp_path):
    """Loguru renders SOURCE LINES inside a backtrace. A credential written in
    the source therefore reaches the log without ever being an argument."""
    _setup(tmp_path, level="NONE")
    try:
        _raise_with_credential()
    except RuntimeError:
        get_logger("core").opt(exception=True).error("boom")
    flush()

    text = (tmp_path / "errors.log").read_text()
    assert "_raise_with_credential" in text, "the frame must still be visible"
    assert "abc123secret" not in text


class _SdkResponse:
    """An SDK object whose repr carries the credential, as they routinely do."""

    def __str__(self) -> str:
        return "Response(headers={'authorization': 'Bearer leaked-token-value'})"


def test_sdk_attribute_str_masked(tmp_path):
    _setup(tmp_path, level="DEBUG")
    get_logger("core").info("response {}", _SdkResponse())
    flush()

    text = (tmp_path / "ayder.log").read_text()
    assert "leaked-token-value" not in text
    assert "<redacted:" in text


def test_benign_records_byte_intact(tmp_path):
    """Masking must be invisible to ordinary output: no truncation, no rewrite."""
    _setup(tmp_path, level="DEBUG")
    message = "compacted 12 messages into 3 (ratio 0.25) in 41ms"
    get_logger("core").info(message)
    flush()

    assert message in (tmp_path / "ayder.log").read_text()


def test_types_and_frames_retained(tmp_path):
    """Masking removes credentials, not diagnostics: type and frames survive."""
    _setup(tmp_path, level="NONE")
    try:
        _raise_with_credential()
    except RuntimeError:
        get_logger("core").opt(exception=True).error("failed")
    flush()

    text = (tmp_path / "errors.log").read_text()
    assert "RuntimeError" in text
    assert "Traceback" in text
    assert "test_sink_masking.py" in text


def test_trace_jsonl_not_masked(tmp_path):
    """Trace JSONL is machine-read structured output, NOT prose. Masking it
    would corrupt the schema, so it is written raw - by design."""
    _setup(tmp_path, level="NONE", trace_enabled=True)
    emit_event("core", "probe", detail="api_key=sk-abcdefghijkl")
    flush()

    lines = [ln for ln in (tmp_path / "trace.jsonl").read_text().splitlines() if ln]
    payload = [json.loads(ln)["record"]["extra"] for ln in lines]
    assert any(e.get("detail") == "api_key=sk-abcdefghijkl" for e in payload), payload


def test_events_never_reach_the_masked_prose_sinks(tmp_path):
    """The routing that makes the exemption safe: events go to trace ONLY."""
    _setup(tmp_path, level="DEBUG", trace_enabled=True)
    emit_event("core", "probe", detail="api_key=sk-abcdefghijkl")
    flush()

    assert "sk-abcdefghijkl" not in (tmp_path / "ayder.log").read_text()
    errors = tmp_path / "errors.log"
    assert "sk-abcdefghijkl" not in (errors.read_text() if errors.exists() else "")


def test_rotation_retention_with_wrapper(tmp_path):
    """Rotation runs INSIDE the wrapped sink, so it must still fire - and every
    rotated file must be masked, not just the live one."""
    _setup(tmp_path, level="DEBUG", rotation="1 KB", retention="7 days")
    for index in range(400):
        get_logger("core").info("row {} token=abc123 {}", index, "y" * 40)
    flush()
    logger.remove()

    produced = sorted(tmp_path.glob("ayder*.log"))
    assert len(produced) > 1, [p.name for p in produced]
    for path in produced:
        text = path.read_text()
        assert "token=abc123" not in text, path.name


def test_enqueue_complete_drains(tmp_path):
    """Sinks are enqueue=True, so `flush()` is what makes assertions legal."""
    _setup(tmp_path, level="DEBUG")
    for index in range(200):
        get_logger("core").info("drain {}", index)
    flush()

    text = (tmp_path / "ayder.log").read_text()
    assert text.count("drain ") == 200


def test_repeated_setup_fd_hygiene(tmp_path):
    """Reconfiguring must close what it replaces; a leak here exhausts the
    process's descriptors over a long TUI session."""
    fd_dir = "/proc/self/fd" if os.path.isdir("/proc/self/fd") else "/dev/fd"

    _setup(tmp_path, level="DEBUG")
    flush()
    baseline = len(os.listdir(fd_dir))
    for _ in range(10):
        _setup(tmp_path, level="DEBUG")
        flush()
    assert len(os.listdir(fd_dir)) <= baseline + 4


def test_console_isatty_passthrough():
    """Colorize autodetection reads `isatty`, so the shim must not hide it."""
    class _Tty(StringIO):
        def isatty(self): return True

    assert _MaskingStream(_Tty()).isatty() is True
    assert _MaskingStream(StringIO()).isatty() is False


def test_console_shim_never_closed_on_remove(tmp_path):
    """The shim has no `stop`, so `logger.remove()` cannot close a stream the
    caller owns - proven against the real dispatch, not against the source."""
    stream = StringIO()
    _setup(tmp_path, level="INFO", console=True, console_stream=stream)
    logger.remove()

    assert not stream.closed
    stream.write("still usable")
    assert "still usable" in stream.getvalue()


def test_trace_sink_preconstructed_object(tmp_path):
    """Trace is a RAW FileSink object, constructed before the teardown boundary
    like every other sink - not a path string handed to `add()`."""
    file_sink, _message, _stream = _loguru_private()
    _setup(tmp_path, level="NONE", trace_enabled=True)

    streams = [h._sink._stream for h in _core_handlers().values()
               if hasattr(h._sink, "_stream")]
    assert any(isinstance(s, file_sink) for s in streams), streams
    assert any(isinstance(s, MaskingFileSink) for s in streams), streams

    emit_event("core", "probe", n=1)
    flush()
    lines = [ln for ln in (tmp_path / "trace.jsonl").read_text().splitlines() if ln]
    assert lines and all(json.loads(ln)["record"]["extra"].get("evt") for ln in lines)


# ================================================ the transactional lifecycle

def _fake_private(*, fail_on=None, stop_fails_on=(), attempts=None, raised=None):
    """A `_loguru_private` replacement whose FileSink misbehaves on demand.

    The full parameter list is deliberate: `_shape_guard` checks the signature,
    so a stub that dropped keywords would be rejected as drift before any
    lifecycle branch was ever reached.
    """
    real_file_sink, message_cls, stream_sink = _loguru_private()

    class _FakeFileSink:
        def __init__(self, path, rotation=None, retention=None, compression=None,
                     delay=False, watch=False, mode="a", buffering=1,
                     encoding="utf8", **kwargs):
            self.path = str(path)
            self.stopped = False
            if fail_on is not None and self.path.endswith(fail_on):
                boom = _SinkBoom("constructor refused this path")
                if raised is not None:
                    raised.append(boom)
                raise boom
            self._inner = real_file_sink(path, rotation=rotation,
                                         retention=retention)

        def write(self, message):
            self._inner.write(message)

        def stop(self):
            # `_shape_guard` builds and stops its own probe sink on every setup;
            # that is guard machinery, not a lifecycle event under test.
            if attempts is not None and not self.path.endswith("probe.log"):
                attempts.append(self.path)
            self.stopped = True
            self._inner.stop()
            if any(self.path.endswith(suffix) for suffix in stop_fails_on):
                boom = _SinkBoom("stop refused this sink")
                if raised is not None:
                    raised.append(boom)
                raise boom

    return lambda: (_FakeFileSink, message_cls, stream_sink)


def _assert_safe_state():
    assert _core_handlers() == {}
    assert logging_config._sink_spec is None
    assert logging_config._configured is False
    assert logging_config._current_level == "NONE"


def test_reconfig_failure_at_shape_guard_preserves_old_state(tmp_path, monkeypatch):
    """Compatibility drift is detected before teardown, so nothing is lost."""
    _setup(tmp_path, level="INFO")
    old_spec = logging_config._sink_spec
    old_handlers = dict(_core_handlers())

    monkeypatch.setattr(logging_config, "_loguru_private",
                        lambda: (_ for _ in ()).throw(ImportError("gone")))
    with pytest.raises(RuntimeError, match="Loguru drift"):
        _setup(tmp_path, level="DEBUG")

    assert dict(_core_handlers()) == old_handlers
    assert logging_config._sink_spec is old_spec
    assert logging_config._configured is True
    assert logging_config._current_level == "INFO"


def test_reconfig_failure_at_constructor_preserves_old_state(tmp_path, monkeypatch):
    """A later constructor fails after an earlier sink was built: the built one
    is closed, and the PREVIOUS configuration is still fully published."""
    _setup(tmp_path, level="INFO")
    old_spec = logging_config._sink_spec
    old_handlers = dict(_core_handlers())

    attempts: list[str] = []
    monkeypatch.setattr(logging_config, "_loguru_private",
                        _fake_private(fail_on="trace.jsonl", attempts=attempts))
    with pytest.raises(_SinkBoom):
        _setup(tmp_path, level="INFO", trace_enabled=True)

    assert [Path(p).name for p in attempts] == ["errors.log"]
    assert dict(_core_handlers()) == old_handlers
    assert logging_config._sink_spec is old_spec
    assert logging_config._configured is True
    assert logging_config._current_level == "INFO"
    get_logger("core").info("old sinks still write")
    flush()
    assert "old sinks still write" in (tmp_path / "ayder.log").read_text()


def test_constructor_failure_cleanup_stop_failure_best_effort(tmp_path, monkeypatch):
    """Two owned sinks built, a later constructor fails, and one built sink's
    `stop()` ALSO fails.

    Every constructed sink must still get a cleanup attempt, the raised error
    must be the ORIGINAL constructor failure by identity, and the cleanup error
    may contribute only its stage and type - never its content.
    """
    attempts: list[str] = []
    raised: list[BaseException] = []
    monkeypatch.setattr(logging_config, "_loguru_private",
                        _fake_private(fail_on="ayder.log",
                                      stop_fails_on=("errors.log",),
                                      attempts=attempts, raised=raised))

    with pytest.raises(_SinkBoom) as excinfo:
        _setup(tmp_path, level="INFO", trace_enabled=True)

    # Newest first, and the failing stop did not abort the pass.
    assert [Path(p).name for p in attempts] == ["trace.jsonl", "errors.log"]
    constructor_boom = raised[0]
    assert excinfo.value is constructor_boom, "the original failure must be re-raised"

    notes = getattr(excinfo.value, "__notes__", [])
    assert notes == ["ayder setup cleanup (construct): _SinkBoom stopping a sink"]
    assert "stop refused this sink" not in " ".join(notes), "notes must be content-free"
    assert str(tmp_path) not in " ".join(notes), "notes must not carry paths"


def test_reconfig_failure_at_add_publishes_safe_state(tmp_path, monkeypatch):
    """After the teardown boundary there is no old configuration to keep, so the
    contract is the explicit safe state - stated truthfully, not faked."""
    _setup(tmp_path, level="INFO")
    attempts: list[str] = []
    monkeypatch.setattr(logging_config, "_loguru_private",
                        _fake_private(attempts=attempts))
    monkeypatch.setattr(logging_config.logger, "add",
                        lambda *a, **k: (_ for _ in ()).throw(ValueError("add refused")))

    with pytest.raises(ValueError, match="add refused"):
        _setup(tmp_path, level="INFO")

    _assert_safe_state()
    assert sorted(Path(p).name for p in attempts) == ["ayder.log", "errors.log"]


def test_reconfig_failure_at_add_leaves_console_stream_open(tmp_path, monkeypatch):
    """`_MaskingStream` is not owned: cleanup must never touch the caller's stream."""
    stream = StringIO()
    monkeypatch.setattr(logging_config.logger, "add",
                        lambda *a, **k: (_ for _ in ()).throw(ValueError("add refused")))
    with pytest.raises(ValueError):
        _setup(tmp_path, level="INFO", console=True, console_stream=stream)

    _assert_safe_state()
    assert not stream.closed


@pytest.mark.parametrize("hostile_first", [
    pytest.param(True, id="hostile-then-bridge"),
    pytest.param(False, id="bridge-then-hostile"),
])
def test_reconfig_failure_at_bridge_install_publishes_safe_state(
        tmp_path, monkeypatch, hostile_first):
    """`basicConfig(force=True)` closes prior root handlers, and a hostile one
    can raise mid-list.

    The surviving root-handler set is therefore ORDERING dependent, so the
    failed state promises only what it can keep: our loguru handlers are gone
    and the safe state is published. Generic stdlib forwarding is observed, not
    promised.
    """
    logging_module = logging_config.logging

    class _Hostile(logging_module.Handler):
        armed = True

        def emit(self, record): pass

        def close(self):
            if self.armed:
                raise _SinkBoom("close refused")

    hostile = _Hostile()
    bridge = logging_config._InterceptHandler()
    order = [hostile, bridge] if hostile_first else [bridge, hostile]
    logging_module.root.handlers[:] = order

    try:
        with pytest.raises(_SinkBoom, match="close refused"):
            _setup(tmp_path, level="INFO")

        _assert_safe_state()
        survivors = list(logging_module.root.handlers)
        if hostile_first:
            # The raise aborted the loop, so the old bridge was never reached.
            assert survivors == [bridge]
        else:
            assert survivors == []
    finally:
        _Hostile.armed = False
        logging_module.root.handlers[:] = []


def test_teardown_stop_failure_best_effort(tmp_path, monkeypatch):
    """An old sink whose `stop()` raises must not strand the sinks behind it.

    Loguru pops a handler and republishes the dict BEFORE calling `stop()`, so
    per-id removal guarantees a fully drained handler dict; only finalization of
    the failing sink is skipped, and that residual is bounded and named.
    """
    class _OldSink:
        def __init__(self, name, fail):
            self.name, self.fail, self.stopped = name, fail, False

        def write(self, message): pass

        def stop(self):
            self.stopped = True
            if self.fail:
                boom = _SinkBoom("old sink refused to stop")
                raised.append(boom)
                raise boom

    raised: list[BaseException] = []
    logger.remove()
    first, second = _OldSink("A", True), _OldSink("B", False)
    logger.add(first, format="{message}")
    logger.add(second, format="{message}")

    attempts: list[str] = []
    monkeypatch.setattr(logging_config, "_loguru_private",
                        _fake_private(attempts=attempts))

    with pytest.raises(_SinkBoom) as excinfo:
        _setup(tmp_path, level="INFO")

    assert first.stopped and second.stopped, "every old handler must be attempted"
    assert excinfo.value is raised[0], "the FIRST teardown failure is the cause"
    _assert_safe_state()
    # The newly constructed sinks were never added, so cleanup closed them.
    assert sorted(Path(p).name for p in attempts) == ["ayder.log", "errors.log"]


def test_post_add_cleanup_stop_failure(tmp_path, monkeypatch):
    """The install fails after sinks were added, and one added sink's `stop()`
    fails during cleanup: the ORIGINAL install failure still surfaces."""
    attempts: list[str] = []
    raised: list[BaseException] = []
    monkeypatch.setattr(logging_config, "_loguru_private",
                        _fake_private(stop_fails_on=("errors.log",),
                                      attempts=attempts, raised=raised))

    install_boom = _SinkBoom("bridge refused")

    def _explode(*a, **k):
        raise install_boom

    monkeypatch.setattr(logging_config.logging, "basicConfig", _explode)

    with pytest.raises(_SinkBoom) as excinfo:
        _setup(tmp_path, level="INFO")

    assert excinfo.value is install_boom, "the install failure is the cause"
    _assert_safe_state()
    assert sorted(Path(p).name for p in attempts) == ["ayder.log", "errors.log"]
    notes = getattr(excinfo.value, "__notes__", [])
    assert any("ayder setup cleanup (install): _SinkBoom removing handler" in n
               for n in notes), notes
    assert not any("stop refused" in n for n in notes), notes


def test_channel_levels_snapshot_immune_to_caller_mutation(tmp_path):
    """One snapshot feeds both the filter and the published spec, so the sink
    and the predicate can never disagree - and the caller cannot retune either
    by mutating the dict they passed in."""
    levels = {"core": level_no("ERROR")}
    setup_logging(_settings(tmp_path, level="INFO", channel_levels=levels))

    levels["core"] = 0                      # the caller mutates AFTER setup
    assert would_reach_prose("core", level_no("INFO"), False) is False

    get_logger("core").info("below the channel threshold")
    flush()
    assert "below the channel threshold" not in (tmp_path / "ayder.log").read_text()


def test_setup_failure_then_bridge_fallback(tmp_path, monkeypatch):
    """In the failed state the predicate reports False, which is what activates
    the sanitized stderr fallback for diagnostics (wired in commit 2)."""
    _setup(tmp_path, level="INFO")
    assert would_reach_prose("external", level_no("ERROR"), False) is True

    monkeypatch.setattr(logging_config.logger, "add",
                        lambda *a, **k: (_ for _ in ()).throw(ValueError("add refused")))
    with pytest.raises(ValueError):
        _setup(tmp_path, level="INFO")

    _assert_safe_state()
    assert would_reach_prose("external", level_no("ERROR"), False) is False


def test_predicate_pre_setup_sees_loguru_default_handler():
    """Before any setup, Loguru's own stderr handler is live at DEBUG, so a
    record that reaches it must NOT also be duplicated by a fallback."""
    logging_config._sink_spec = None
    logger.remove()
    default_id = logger.add(lambda m: None, level="DEBUG")
    try:
        assert would_reach_prose("core", level_no("DEBUG"), False) is True
        assert would_reach_prose("core", level_no("TRACE"), False) is False
    finally:
        logger.remove(default_id)
    assert would_reach_prose("core", level_no("CRITICAL"), False) is False


def test_predicate_level_none_still_routes_exceptions(tmp_path):
    """At level NONE there is no main sink, but errors.log still exists - so an
    exception record needs no fallback while a plain INFO does."""
    _setup(tmp_path, level="NONE")
    assert would_reach_prose("core", level_no("INFO"), True) is True
    assert would_reach_prose("core", level_no("ERROR"), False) is True
    assert would_reach_prose("core", level_no("INFO"), False) is False


def test_predicate_respects_the_channel_allowlist(tmp_path):
    """`--log-channel` excludes bridge records, which is exactly when the
    fallback has to take over."""
    _setup(tmp_path, level="INFO", channels=frozenset({"core"}))
    assert would_reach_prose("core", level_no("INFO"), False) is True
    assert would_reach_prose("external", level_no("INFO"), False) is False
