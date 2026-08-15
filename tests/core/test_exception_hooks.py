import asyncio
import sys
from pathlib import Path

import pytest
from loguru import logger

from ayder_cli.diagnostics import install_asyncio_handler, install_exception_hooks
from ayder_cli.logging_config import LoggingSettings, setup_logging


@pytest.fixture(autouse=True)
def _reset_hook_state():
    """`install_exception_hooks` mutates process-global state. Restore ALL of it.

    Resetting only the two flags is not enough. Each install wraps
    `sys.excepthook` and both signal handlers; leaving the wrappers in place
    while clearing the flags lets the next test wrap them *again*, nesting one
    layer per test until a single exception logs N times. And without the flag
    reset, the first test's `_hooks_installed = True` makes every later install
    a no-op, so the idempotency test would pass vacuously against a hook that
    was never wrapped.

    Snapshot the three globals, reset the flags, and put all three back.
    """
    import signal

    import ayder_cli.diagnostics as d

    saved_hook = sys.excepthook
    saved_sigint = signal.getsignal(signal.SIGINT)
    saved_sigterm = signal.getsignal(signal.SIGTERM)
    d._hooks_installed = False
    d._signals_installed = False
    try:
        yield
    finally:
        sys.excepthook = saved_hook
        signal.signal(signal.SIGINT, saved_sigint)
        signal.signal(signal.SIGTERM, saved_sigterm)
        d._hooks_installed = False
        d._signals_installed = False


def _setup(tmp_path: Path) -> None:
    setup_logging(
        LoggingSettings(
            level="NONE",
            file_path=str(tmp_path / "ayder.log"),
            error_path=str(tmp_path / "errors.log"),
            trace_path=str(tmp_path / "trace.jsonl"),
        )
    )


def test_excepthook_logs_and_chains(tmp_path, monkeypatch):
    _setup(tmp_path)
    called = []
    monkeypatch.setattr(sys, "excepthook", lambda *a: called.append(a))

    install_exception_hooks()
    try:
        raise ValueError("unhandled boom")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    logger.complete()

    assert "unhandled boom" in (tmp_path / "errors.log").read_text()
    assert called, "the original excepthook must still run"


def test_excepthook_install_is_idempotent(tmp_path, monkeypatch):
    """Three installs must still log the failure exactly once.

    Count RECORDS, not text. A single Loguru traceback contains the message
    twice — once in the rendered source line `raise ValueError("once only")`
    and once in the final exception line — so `read_text().count(...) == 1`
    can never hold for one record.
    """
    monkeypatch.chdir(tmp_path)
    setup_logging(
        LoggingSettings(
            level="NONE",
            file_path=str(tmp_path / "a.log"),
            error_path=str(tmp_path / "errors.log"),
        )
    )
    install_exception_hooks()
    install_exception_hooks()
    install_exception_hooks()

    seen = []
    sink = logger.add(lambda m: seen.append(m.record), level=0, format="{message}")
    try:
        try:
            raise ValueError("once only")
        except ValueError:
            sys.excepthook(*sys.exc_info())
    finally:
        logger.remove(sink)

    hits = [r for r in seen if "Unhandled exception" in r["message"]]
    assert len(hits) == 1, [r["message"] for r in seen]
    assert hits[0]["exception"] is not None
    assert "once only" in (tmp_path / "errors.log").read_text()


def test_asyncio_handler_logs(tmp_path):
    _setup(tmp_path)

    async def _main():
        install_asyncio_handler(asyncio.get_running_loop())
        asyncio.get_running_loop().call_exception_handler(
            {
                "message": "task blew up",
                "exception": RuntimeError("async boom"),
            }
        )

    asyncio.run(_main())
    logger.complete()

    text = (tmp_path / "errors.log").read_text()
    assert "task blew up" in text or "async boom" in text


def test_asyncio_handler_chains_and_installs_once(tmp_path):
    """A previously installed handler belongs to someone; do not replace it."""
    _setup(tmp_path)
    prior = []

    async def _main():
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(lambda lp, ctx: prior.append(ctx["message"]))
        install_asyncio_handler(loop)
        install_asyncio_handler(loop)  # must not nest
        loop.call_exception_handler(
            {"message": "chained", "exception": RuntimeError("x")}
        )

    asyncio.run(_main())
    logger.complete()

    assert prior == ["chained"], "the pre-existing handler must still run, exactly once"
    # The custom handler receives the ORIGINAL context (asserted above), while
    # our own record carries the B2-prime normalized message - `chained` is an
    # unknown string, so it degrades to type/length metadata.
    text = (tmp_path / "errors.log").read_text()
    assert text.count("Unhandled asyncio exception") == 1, text
    assert "<str, 7 chars>" in text, text


def test_keyboard_interrupt_is_not_logged_as_a_crash(tmp_path, monkeypatch):
    _setup(tmp_path)
    monkeypatch.setattr(sys, "excepthook", lambda *a: None)
    install_exception_hooks()

    try:
        raise KeyboardInterrupt()
    except KeyboardInterrupt:
        sys.excepthook(*sys.exc_info())
    logger.complete()

    p = tmp_path / "errors.log"
    assert "KeyboardInterrupt" not in (p.read_text() if p.exists() else "")


def test_diagnostics_does_not_import_loguru():
    """Phase 5's import gate rejects it; use the facade helpers."""
    src = Path("src/ayder_cli/diagnostics.py").read_text()
    assert "from loguru" not in src
    assert "import loguru" not in src


def test_sigterm_wrapper_logs_warning_flushes_then_chains(tmp_path, monkeypatch):
    """A signal is a termination request, not a failure.

    Four things must hold, and each is asserted against state this test owns:
    WARNING level, no attached traceback, `flush()` **before** the previous
    handler runs, and the record reaching this test's own `errors.log`.

    `flush` is spied via a delegating wrapper, not replaced. A capture sink
    alone proves nothing about flushing — a synchronous sink succeeds even if
    `flush()` is deleted — so ordering is recorded explicitly.
    """
    import signal

    import ayder_cli.diagnostics as diag

    _setup(tmp_path)  # this test owns its logging state

    order: list[str] = []
    real_flush = diag.flush

    def _spy_flush():
        order.append("flush")
        real_flush()  # delegate; do not stub it out

    monkeypatch.setattr(diag, "flush", _spy_flush)

    def _prior(signum, frame):
        order.append("prior")

    saved = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, _prior)
    try:
        install_exception_hooks()
        wrapper = signal.getsignal(signal.SIGTERM)
        assert wrapper is not _prior, "hooks did not wrap SIGTERM"
        wrapper(signal.SIGTERM, None)  # direct call — never signal the process
    finally:
        signal.signal(signal.SIGTERM, saved)

    # flush must happen BEFORE the previous handler, which may terminate us.
    assert order == ["flush", "prior"], order

    text = (tmp_path / "errors.log").read_text()
    assert "Received signal" in text, text
    assert "SIGTERM" in text, text
    assert "WARNING" in text, text
    assert "Traceback" not in text, "a signal must not attach a traceback"


def _ast_of(rel):
    import ast

    root = Path(__file__).resolve().parents[2] / "src" / "ayder_cli"
    return ast.parse((root / rel).read_text())


def _direct_calls(body):
    """`(index, name)` for calls that are DIRECT statements of `body`.

    Deliberately not `ast.walk`: a call inside `if False:`, or inside a nested
    function nobody calls, is not on the production path. Walking the tree
    accepts exactly those placements.
    """
    import ast

    out = []
    for i, stmt in enumerate(body):
        node = stmt.value if isinstance(stmt, ast.Expr) else stmt
        if isinstance(node, ast.Await):
            node = node.value
        if isinstance(node, ast.Call):
            out.append(
                (i, getattr(node.func, "id", "") or getattr(node.func, "attr", ""))
            )
    return out


def _find(tree, name, cls=None):
    """The function `name`, optionally required to be a method of class `cls`."""
    import ast

    if cls is not None:
        for n in ast.walk(tree):
            if isinstance(n, ast.ClassDef) and n.name == cls:
                for m in n.body:
                    if (
                        isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and m.name == name
                    ):
                        return m
        return None
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    return None


def test_cli_installs_hooks_directly_in_main_after_setup_logging():
    """Both calls must be adjacent direct statements of `main()`.

    Hooks installed before the sinks exist log nowhere; hooks installed inside
    an uncalled nested function never run at all. The step says *immediately
    after*, so adjacency is asserted, not merely order.
    """
    main = _find(_ast_of("cli.py"), "main")
    assert main is not None, "cli.py has no main()"
    calls = dict((nm, i) for i, nm in _direct_calls(main.body))
    assert "setup_logging" in calls, "setup_logging is not a direct statement of main()"
    assert "install_exception_hooks" in calls, (
        "install_exception_hooks is not a direct statement of main()"
    )
    assert calls["install_exception_hooks"] == calls["setup_logging"] + 1, (
        "hooks must be installed immediately after setup_logging: "
        f"setup at {calls['setup_logging']}, install at {calls['install_exception_hooks']}"
    )


def _installs_running_loop(call):
    """True only for `install_asyncio_handler(asyncio.get_running_loop())`.

    The argument is not decoration: `install_asyncio_handler(None)` compiles,
    satisfies a name-and-placement check, and crashes at runtime. The direct
    hook tests supply a real loop themselves, so only this guard can catch a
    production call site that does not.
    """
    import ast

    if call.keywords or len(call.args) != 1:
        return False
    arg = call.args[0]
    return (
        isinstance(arg, ast.Call)
        and not arg.args
        and not arg.keywords
        and isinstance(arg.func, ast.Attribute)
        and arg.func.attr == "get_running_loop"
        and isinstance(arg.func.value, ast.Name)
        and arg.func.value.id == "asyncio"
    )


def _attr_call_line(node, receiver, method):
    """Line of `receiver.method(...)` anywhere inside `node`, else None.

    Walks deliberately: the statements the install must *precede* legitimately
    sit inside conditionals — `agent_registry.set_loop(...)` is guarded by
    `if agent_registry is not None:` — so a direct-statement scan would miss
    them and the guard would fail for the correctly wired form.
    """
    import ast

    for n in ast.walk(node):
        if (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == method
            and isinstance(n.func.value, ast.Name)
            and n.func.value.id == receiver
        ):
            return n.lineno
    return None


def _awaited_attr_call_line(node, receiver, method):
    """Line of `await receiver.method(...)`, else None.

    The receiver and the `await` both matter: a bare `loop.run()` never runs the
    loop, and another object's `run()` is a different operation entirely.
    """
    import ast

    for n in ast.walk(node):
        if not isinstance(n, ast.Await) or not isinstance(n.value, ast.Call):
            continue
        f = n.value.func
        if (
            isinstance(f, ast.Attribute)
            and f.attr == method
            and isinstance(f.value, ast.Name)
            and f.value.id == receiver
        ):
            return n.lineno
    return None


def test_cli_runner_installs_handler_first_in_drive():
    """The handler attaches to a RUNNING loop, so it must be `_drive()`'s very
    first statement, must be handed the running loop, and must precede both
    loop operations."""
    import ast

    drive = _find(_ast_of("cli_runner.py"), "_drive")
    assert drive is not None, "cli_runner.py has no nested _drive()"
    assert drive.body, "_drive() is empty"

    first = drive.body[0]
    assert isinstance(first, ast.Expr) and isinstance(first.value, ast.Call), (
        f"_drive()'s first statement is {type(first).__name__}, not a call"
    )
    fname = getattr(first.value.func, "id", "") or getattr(first.value.func, "attr", "")
    assert fname == "install_asyncio_handler", (
        f"_drive()'s first statement calls {fname!r}, not install_asyncio_handler"
    )
    assert _installs_running_loop(first.value), (
        "_drive() must call install_asyncio_handler(asyncio.get_running_loop())"
    )

    set_loop = _attr_call_line(drive, "agent_registry", "set_loop")
    run = _awaited_attr_call_line(drive, "loop", "run")
    assert set_loop is not None, "_drive() never calls agent_registry.set_loop(...)"
    assert run is not None, "_drive() never awaits loop.run()"
    assert first.lineno < set_loop, "the handler must be installed before set_loop"
    assert first.lineno < run, "the handler must be installed before loop.run()"


def test_ayder_app_on_mount_installs_handler_directly():
    """Must be a direct statement of `AyderApp.on_mount`, handed the running
    loop — not any class's `on_mount`, not a nested helper nobody calls, and
    not `install_asyncio_handler(None)`."""
    import ast

    on_mount = _find(_ast_of("tui/app.py"), "on_mount", cls="AyderApp")
    assert on_mount is not None, "AyderApp.on_mount not found"
    installs = [
        s.value
        for s in on_mount.body
        if isinstance(s, ast.Expr)
        and isinstance(s.value, ast.Call)
        and (getattr(s.value.func, "id", "") or getattr(s.value.func, "attr", ""))
        == "install_asyncio_handler"
    ]
    assert installs, (
        "AyderApp.on_mount does not install the handler as a direct statement"
    )
    assert _installs_running_loop(installs[0]), (
        "AyderApp.on_mount must pass asyncio.get_running_loop()"
    )
