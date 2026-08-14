"""Controls for the broad-exception policy gate (CONTRACTS §C10).

One file, one harness. Every subprocess result is checked for a crash before it
is interpreted — a gate that dies must never read as a clean run.
"""
import subprocess
import sys
import textwrap
from pathlib import Path

# tests/scripts/<this>.py -> repository root. Never cwd-relative: pytest may be
# invoked from anywhere, and a wrong root is how a gate "passes" over nothing.
REPO = Path(__file__).resolve().parents[2]
GATE = REPO / "scripts" / "check_exception_handlers.py"


def _run(*args):
    """Run the gate; return (exit_code, stdout+stderr). Never let a crash pass."""
    r = subprocess.run(
        [sys.executable, str(GATE), *args],
        capture_output=True, text=True, cwd=REPO,
    )
    out = r.stdout + r.stderr
    assert "Traceback" not in out, f"gate crashed:\n{out}"
    return r.returncode, out


def _verdict(tmp_path: Path, src: str) -> str:
    """Verdict output for a single synthetic module."""
    (tmp_path / "sample.py").write_text(textwrap.dedent(src))
    _code, out = _run("--path", str(tmp_path))
    return out


def test_bare_raise_passes(tmp_path):
    assert "sample.py" not in _verdict(tmp_path, """
        try:
            x()
        except Exception:
            raise
    """)


def test_silent_pass_fails(tmp_path):
    assert "FAIL" in _verdict(tmp_path, """
        try:
            x()
        except Exception:
            pass
    """)


def test_log_without_exception_flag_fails(tmp_path):
    assert "FAIL" in _verdict(tmp_path, """
        try:
            x()
        except Exception as e:
            logger.warning("failed: {}", e)
    """)


def test_opt_exception_log_passes(tmp_path):
    assert "FAIL" not in _verdict(tmp_path, """
        try:
            x()
        except Exception:
            logger.opt(exception=True).warning("failed")
    """)


def test_conditional_raise_is_reported_not_passed(tmp_path):
    """The defect a naive ast.walk misses."""
    out = _verdict(tmp_path, """
        try:
            x()
        except Exception:
            if cond:
                raise
            pass
    """)
    assert "REPORT" in out


def test_narrow_handler_is_ignored(tmp_path):
    assert "sample.py" not in _verdict(tmp_path, """
        try:
            x()
        except FileNotFoundError:
            pass
    """)


def test_noqa_marker_suppresses(tmp_path):
    assert "FAIL" not in _verdict(tmp_path, """
        try:
            x()
        except Exception:  # noqa: AYDER-EXC plugin boundary
            pass
    """)


def test_allowlisted_failure_return_passes(tmp_path):
    assert "FAIL" not in _verdict(tmp_path, """
        try:
            x()
        except Exception as e:
            return ToolError(str(e))
    """)


def test_logger_exception_shorthand_passes(tmp_path):
    """ruff TRY400 pushes code to this form; the gate must accept it."""
    assert "FAIL" not in _verdict(tmp_path, """
        try:
            x()
        except Exception:
            logger.exception("failed")
    """)


def test_success_execution_result_does_not_satisfy(tmp_path):
    """ExecutionResult(success=True) is a success return, not a failure."""
    assert "FAIL" in _verdict(tmp_path, """
        try:
            x()
        except Exception:
            return ExecutionResult(success=True)
    """)


def test_failure_execution_result_passes(tmp_path):
    assert "FAIL" not in _verdict(tmp_path, """
        try:
            x()
        except Exception as e:
            return ExecutionResult(success=False, error=e)
    """)


def test_bare_marker_without_reason_does_not_suppress(tmp_path):
    assert "FAIL" in _verdict(tmp_path, """
        try:
            x()
        except Exception:  # noqa: AYDER-EXC
            pass
    """)


def test_bare_except_is_out_of_scope(tmp_path):
    """CONTRACTS C10 scopes the gate to Exception/BaseException only."""
    assert "sample.py" not in _verdict(tmp_path, """
        try:
            x()
        except:
            pass
    """)


# -- receiver controls: only the §C8 bindings satisfy the policy --------------

def test_non_logger_exception_call_does_not_satisfy(tmp_path):
    """`future.exception()` is not logging — it must not pass the handler."""
    assert "FAIL" in _verdict(tmp_path, """
        try:
            x()
        except Exception:
            future.exception()
    """)


def test_non_logger_opt_call_does_not_satisfy(tmp_path):
    """`.opt(exception=True)` on an unrelated object must not pass either."""
    assert "FAIL" in _verdict(tmp_path, """
        try:
            x()
        except Exception:
            widget.opt(exception=True).error("nope")
    """)


# -- coverage controls: the gate must not report success over nothing --------

def test_missing_root_aborts():
    code, out = _run("--path", "src/does-not-exist")
    assert code == 2
    assert "source root does not exist" in out


def test_empty_root_aborts(tmp_path):
    code, out = _run("--path", str(tmp_path))
    assert code == 2
    assert "no Python files" in out


def test_unparseable_file_is_a_finding(tmp_path):
    (tmp_path / "broken.py").write_text("def broken(\n")
    code, out = _run("--path", str(tmp_path), "--expect-broad", "0")
    assert code == 1
    assert "UNPARSEABLE" in out


def test_full_tree_census_is_frozen():
    """119 is the §C10 census. A different number means the gate is reading the
    wrong tree, or the census moved without the plan being updated."""
    code, out = _run()
    assert "broad=119" in out, out
    assert "files=112/112" in out, out
    code, out = _run("--expect-broad", "118")
    assert code == 1
    assert "census: found 119" in out
