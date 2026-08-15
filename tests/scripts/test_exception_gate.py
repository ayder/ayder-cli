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
    out = _verdict(tmp_path, """
        try:
            x()
        except Exception:
            raise
    """)
    assert "sample.py" not in out
    # An absence-of-finding assertion alone can't tell "correctly satisfied"
    # apart from "invisible to the walker" — pin the census too.
    assert "broad=1" in out, out


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
    out = _verdict(tmp_path, """
        try:
            x()
        except Exception:
            logger.opt(exception=True).warning("failed")
    """)
    assert "FAIL" not in out
    assert "broad=1" in out, out


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
    out = _verdict(tmp_path, """
        try:
            x()
        except FileNotFoundError:
            pass
    """)
    assert "sample.py" not in out
    # Confirms it's excluded by policy (still counted, never broad) — not
    # merely absent from the walk.
    assert "broad=0" in out, out


def test_noqa_marker_suppresses(tmp_path):
    out = _verdict(tmp_path, """
        try:
            x()
        except Exception:  # noqa: AYDER-EXC plugin boundary
            pass
    """)
    assert "FAIL" not in out
    # Suppressed findings are still counted broad — only the finding is hidden.
    assert "broad=1" in out, out


def test_allowlisted_failure_return_passes(tmp_path):
    out = _verdict(tmp_path, """
        try:
            x()
        except Exception as e:
            return ToolError(str(e))
    """)
    assert "FAIL" not in out
    assert "broad=1" in out, out


def test_logger_exception_shorthand_passes(tmp_path):
    """ruff TRY400 pushes code to this form; the gate must accept it."""
    out = _verdict(tmp_path, """
        try:
            x()
        except Exception:
            logger.exception("failed")
    """)
    assert "FAIL" not in out
    assert "broad=1" in out, out


def test_success_execution_result_does_not_satisfy(tmp_path):
    """ExecutionResult(success=True) is a success return, not a failure."""
    assert "FAIL" in _verdict(tmp_path, """
        try:
            x()
        except Exception:
            return ExecutionResult(success=True)
    """)


def test_failure_execution_result_passes(tmp_path):
    out = _verdict(tmp_path, """
        try:
            x()
        except Exception as e:
            return ExecutionResult(success=False, error=e)
    """)
    assert "FAIL" not in out
    assert "broad=1" in out, out


def test_bare_marker_without_reason_does_not_suppress(tmp_path):
    assert "FAIL" in _verdict(tmp_path, """
        try:
            x()
        except Exception:  # noqa: AYDER-EXC
            pass
    """)


def test_bare_except_is_out_of_scope(tmp_path):
    """CONTRACTS C10 scopes the gate to Exception/BaseException only."""
    out = _verdict(tmp_path, """
        try:
            x()
        except:
            pass
    """)
    assert "sample.py" not in out
    assert "broad=0" in out, out


# -- exception-group coverage: `except*` parses to ast.TryStar, not ast.Try ---
#
# A NodeVisitor that implements only visit_Try walks straight past a TryStar
# node via generic_visit and into its ExceptHandler children, so the handler
# is never counted. That is not a policy miss, it is invisibility: the gate
# reports the frozen census and exits green over a construct it never saw.
# "sample.py not in output" or "FAIL not in output" would both be satisfied
# by this hole too — an absence-of-finding assertion is not a coverage
# assertion, so both controls below pin the broad-handler census as well.

def test_star_silent_pass_fails(tmp_path):
    """`except* Exception: pass` must be found, counted, and flagged."""
    (tmp_path / "sample.py").write_text(textwrap.dedent("""
        try:
            x()
        except* Exception:
            pass
    """))
    code, out = _run("--path", str(tmp_path))
    assert "broad=1" in out, out
    assert "FAIL" in out, out
    assert code == 1


def test_star_raise_passes(tmp_path):
    """Not optional: a fix that enumerates TryStar but always reports FAIL
    (skipping policy evaluation entirely) would still satisfy the control
    above. Only a clean `findings=0` alongside `broad=1` proves the verdict
    logic — not just the census — now runs on TryStar handlers too.
    """
    (tmp_path / "sample.py").write_text(textwrap.dedent("""
        try:
            x()
        except* Exception:
            raise
    """))
    code, out = _run("--path", str(tmp_path))
    assert "broad=1" in out, out
    assert "findings=0" in out, out
    assert code == 0


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


# -- plain-marker controls ----------------------------------------------------
#
# `AYDER-EXC` is not a Ruff rule code, so spelling the marker `# noqa: AYDER-EXC`
# makes Ruff emit "Invalid `# noqa` directive" on every run. Step 5-02 normalized
# the one live use (the filesystem temp-file re-raiser) to a plain reasoned
# comment. Both halves of that change need a durable control: the gate must still
# honour the plain form, and Ruff must stay quiet about it.


def test_plain_marker_without_noqa_prefix_suppresses(tmp_path):
    """The C10 marker is the token plus a reason — the `# noqa:` prefix is not
    part of it, and must not be required to suppress."""
    out = _verdict(tmp_path, """
        try:
            x()
        except BaseException:  # AYDER-EXC - cleanup then unconditional re-raise
            pass
    """)
    assert "FAIL" not in out, out
    assert "findings=0" in out, out
    # Suppressed findings are still counted broad — only the finding is hidden.
    assert "broad=1" in out, out


def test_plain_marker_draws_no_ruff_noqa_warning(tmp_path):
    """Ruff must report a real BLE001 violation in the fixture while saying
    nothing about the plain marker. Asserting only "no warning" would also pass
    if Ruff never looked at the file at all, so the violation is the coverage
    proof and the absent warning is the claim under test."""
    (tmp_path / "sample.py").write_text(textwrap.dedent("""
        import contextlib

        def reraiser(cleanup):
            try:
                pass
            except BaseException:  # AYDER-EXC - cleanup then unconditional re-raise
                with contextlib.suppress(OSError):
                    cleanup()
                raise

        def swallower():
            try:
                pass
            except Exception:
                return None
    """))
    r = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--isolated",
         "--select=BLE001", "--output-format=concise", str(tmp_path)],
        capture_output=True, text=True, cwd=REPO,
    )
    out = r.stdout + r.stderr
    assert "panicked" not in out, out
    assert "BLE001" in out, out
    assert "Invalid `# noqa` directive" not in out, out


def test_full_tree_census_is_frozen():
    """119 is the §C10 census. A different number means the gate is reading the
    wrong tree, or the census moved without the plan being updated."""
    code, out = _run()
    assert "broad=119" in out, out
    assert "files=113/113" in out, out
    code, out = _run("--expect-broad", "118")
    assert code == 1
    assert "census: found 119" in out
