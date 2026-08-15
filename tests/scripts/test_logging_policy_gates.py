"""Controls for the %-style and logging-import policy gates (CONTRACTS §C12).

One file, one harness. Every subprocess result is checked for a crash before it
is interpreted - a gate that dies must never read as a clean run - and every
control asserts the exit code, not just the text, because both gates encode
their verdict there.

Deliberately absent, per PHASE5-RULINGS §F5-R2: no control asserts that a known
percent-gate miss (single-argument %-strings, `.log`, non-logger receivers,
dynamic messages) *stays* a miss. Those are step 5-03 work, and a regression
assertion here would make strengthening the rule a test failure.
"""
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# tests/scripts/<this>.py -> repository root. Never cwd-relative: pytest may be
# invoked from anywhere, and a wrong root is how a gate "passes" over nothing.
REPO = Path(__file__).resolve().parents[2]
PCT_GATE = REPO / "scripts" / "find_percent_logging.py"
IMPORT_GATE = REPO / "scripts" / "check_logging_imports.py"
SRC_ROOT = REPO / "src" / "ayder_cli"


def _live_py_count() -> int:
    return len(list(SRC_ROOT.rglob("*.py")))


def _run(gate: Path, *args):
    """Run a gate; return (exit_code, stdout+stderr). Never let a crash pass."""
    r = subprocess.run(
        [sys.executable, str(gate), *args],
        capture_output=True, text=True, cwd=REPO,
    )
    out = r.stdout + r.stderr
    assert "Traceback" not in out, f"gate crashed:\n{out}"
    return r.returncode, out


def _on(gate: Path, tmp_path: Path, src: str, name: str = "sample.py"):
    """Run a gate over a single synthetic module."""
    target = tmp_path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent(src))
    return _run(gate, "--root", str(tmp_path))


GATES = [pytest.param(PCT_GATE, id="percent"),
         pytest.param(IMPORT_GATE, id="imports")]


# -- coverage controls: neither gate may report success over nothing ----------

@pytest.mark.parametrize("gate", GATES)
def test_missing_root_aborts(gate):
    """The fenced version scanned a cwd-relative path and exited 0 over an
    empty rglob. Assert the message too: argparse also exits 2."""
    code, out = _run(gate, "--root", "src/does-not-exist")
    assert code == 2, out
    assert "source root does not exist" in out, out


@pytest.mark.parametrize("gate", GATES)
def test_empty_root_aborts(gate, tmp_path):
    code, out = _run(gate, "--root", str(tmp_path))
    assert code == 2, out
    assert "no Python files" in out, out


@pytest.mark.parametrize("gate", GATES)
def test_default_root_is_resolved_from_the_script_not_the_cwd(gate, tmp_path):
    """Invoked with no --root and a cwd that has no `src/ayder_cli`, the gate
    must still scan the package - not silently find zero files."""
    r = subprocess.run([sys.executable, str(gate)],
                       capture_output=True, text=True, cwd=tmp_path)
    out = r.stdout + r.stderr
    assert "Traceback" not in out, out
    assert r.returncode == 0, out
    assert f"scanned {_live_py_count()} file(s)" in out, out


@pytest.mark.parametrize("gate", GATES)
def test_unparseable_file_is_a_finding(gate, tmp_path):
    """A file that hides a violation behind a SyntaxError must fail the gate,
    not be skipped. Both a %-call and a banned import are present."""
    (tmp_path / "broken.py").write_text(textwrap.dedent("""
        import logging
        logger.info("failed %s", err)
        def broken(
    """))
    code, out = _run(gate, "--root", str(tmp_path))
    assert code == 1, out
    assert "UNPARSEABLE" in out, out
    assert "broken.py" in out, out


@pytest.mark.parametrize("gate", GATES)
def test_recursive_discovery(gate, tmp_path):
    """rglob, not glob: a violation three directories down must be found."""
    code, out = _on(gate, tmp_path, """
        import logging
        logger.info("failed %s", err)
    """, name="a/b/c/deep.py")
    assert code == 1, out
    assert "deep.py" in out, out


@pytest.mark.parametrize("gate", GATES)
def test_live_tree_is_clean_and_fully_scanned(gate):
    """Exit 0 alone proves nothing; the count proves the corpus was read.
    Derived, not frozen, so adding a module does not fail this control."""
    n = _live_py_count()
    assert n > 0
    code, out = _run(gate)
    assert code == 0, out
    assert f"scanned {n} file(s)" in out, out


# -- percent gate ------------------------------------------------------------

def test_percent_clean_message_passes(tmp_path):
    code, out = _on(PCT_GATE, tmp_path, """
        logger.info("loaded {} rows from {}", n, path)
    """)
    assert code == 0, out
    assert "0 %-style logging call(s)" in out, out
    assert "scanned 1 file(s)" in out, out


@pytest.mark.parametrize("message", [
    pytest.param('"loaded %s rows"', id="pct-s"),
    pytest.param('"loaded %d rows"', id="pct-d"),
    pytest.param('"loaded %r rows"', id="pct-r"),
    pytest.param('"user %(name)s signed in"', id="mapping-form"),
    pytest.param('"separator %c here"', id="pct-c"),
    pytest.param('"padded %-10.4f value"', id="flags-and-precision"),
])
def test_percent_forms_are_detected(tmp_path, message):
    """`%(name)s` and `%c` are the mutation-sensitive halves of the frozen
    regex: neither appears in the tree today, so only a behaviour control
    stops the pattern being "simplified" back to plain %s/%d."""
    code, out = _on(PCT_GATE, tmp_path, f"""
        logger.warning({message}, value)
    """)
    assert code == 1, out
    assert "1 %-style logging call(s)" in out, out
    assert "sample.py:2" in out, out


@pytest.mark.parametrize("level", ["trace", "debug", "info", "success",
                                   "warning", "error", "exception", "critical"])
def test_every_level_is_covered(tmp_path, level):
    code, out = _on(PCT_GATE, tmp_path, f"""
        logger.{level}("failed %s", err)
    """)
    assert code == 1, out


def test_percent_reports_every_site(tmp_path):
    code, out = _on(PCT_GATE, tmp_path, """
        logger.info("a %s", x)
        logger.error("b %(k)s", y)
        logger.debug("c {}", z)
    """)
    assert code == 1, out
    assert "2 %-style logging call(s)" in out, out
    assert "sample.py:2" in out and "sample.py:3" in out, out


def test_percent_gate_ignores_non_logging_names(tmp_path):
    """`.format`-alike methods outside LEVELS are not this gate's business."""
    code, out = _on(PCT_GATE, tmp_path, """
        printer.render("failed %s", err)
    """)
    assert code == 0, out


# -- import gate -------------------------------------------------------------

def test_import_clean_module_passes(tmp_path):
    code, out = _on(IMPORT_GATE, tmp_path, """
        import os
        from ayder_cli.log import get_logger
    """)
    assert code == 0, out
    assert "0 disallowed logging import(s)" in out, out
    assert "scanned 1 file(s)" in out, out


@pytest.mark.parametrize("stmt", [
    pytest.param("import logging", id="import-logging"),
    pytest.param("import logging.handlers", id="import-logging-dotted"),
    pytest.param("import logging.handlers as h", id="import-logging-dotted-as"),
    pytest.param("from logging import getLogger", id="from-logging"),
    pytest.param("from logging.handlers import RotatingFileHandler",
                 id="from-logging-dotted"),
    pytest.param("import loguru", id="import-loguru"),
    pytest.param("import loguru._logger", id="import-loguru-dotted"),
    pytest.param("from loguru import logger", id="from-loguru"),
    pytest.param("from loguru._logger import Logger", id="from-loguru-dotted"),
])
def test_banned_imports_are_detected(tmp_path, stmt):
    """Dotted submodules are the mutation-sensitive half: an exact-name test
    (`a.name == "logging"`, `node.module == "loguru"`) waves every one of the
    dotted forms through while still passing a naive control."""
    code, out = _on(IMPORT_GATE, tmp_path, f"""
        {stmt}
    """)
    assert code == 1, out
    assert "1 disallowed logging import(s)" in out, out
    assert "sample.py:2" in out, out


@pytest.mark.parametrize("name", ["log.py", "logging_config.py"])
def test_root_level_allowlist_is_exempt(tmp_path, name):
    code, out = _on(IMPORT_GATE, tmp_path, """
        import logging
        from loguru import logger
    """, name=name)
    assert code == 0, out
    assert "0 disallowed logging import(s)" in out, out
    # Exempt from the RULE, still read: a broken log.py must still fail.
    assert "scanned 1 file(s)" in out, out


@pytest.mark.parametrize("name", ["tools/log.py", "core/logging_config.py",
                                  "a/b/log.py"])
def test_allowlist_is_by_exact_root_relative_path(tmp_path, name):
    """A name-only allowlist lets any subpackage opt itself out by filename."""
    code, out = _on(IMPORT_GATE, tmp_path, """
        import logging
    """, name=name)
    assert code == 1, out
    assert name in out, out
    assert "1 disallowed logging import(s)" in out, out


def test_allowlisted_file_is_still_parsed(tmp_path):
    """Exemption excuses a file from the rule, never from being read."""
    (tmp_path / "log.py").write_text("def broken(\n")
    code, out = _run(IMPORT_GATE, "--root", str(tmp_path))
    assert code == 1, out
    assert "UNPARSEABLE" in out, out


def test_relative_import_of_a_local_module_is_not_flagged(tmp_path):
    """`from . import helpers` has module=None; it must not crash or match."""
    code, out = _on(IMPORT_GATE, tmp_path, """
        from . import helpers
        from .util import thing
    """)
    assert code == 0, out


def test_import_reports_every_site(tmp_path):
    code, out = _on(IMPORT_GATE, tmp_path, """
        import logging
        import os
        from loguru._logger import Logger
    """)
    assert code == 1, out
    assert "2 disallowed logging import(s)" in out, out
    assert "sample.py:2" in out and "sample.py:4" in out, out


def test_similarly_named_packages_are_not_flagged(tmp_path):
    """Root-prefix matching, not substring: `logging_config` is not `logging`."""
    code, out = _on(IMPORT_GATE, tmp_path, """
        import logging_config
        from ayder_cli.logging_config import setup_logging
        from loguru_extras import thing
    """)
    assert code == 0, out
