"""Controls for the log-argument census gate (CONTRACTS §C12, step 5-03).

One file, one harness. Every subprocess result is checked for a crash before it
is interpreted - a gate that dies must never read as a clean run - and every
control asserts the exit code, not just the text, because the gate encodes its
verdict there.

Every fail-closed branch carries a mutation control: a synthetic tree that the
branch must reject, so weakening the branch turns a passing suite red rather
than quietly widening what the gate lets through.
"""
import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# tests/scripts/<this>.py -> repository root. Never cwd-relative: pytest may be
# invoked from anywhere, and a wrong root is how a gate "passes" over nothing.
REPO = Path(__file__).resolve().parents[2]
GATE = REPO / "scripts" / "check_log_arguments.py"
BASELINE = REPO / "scripts" / "log_argument_baseline.txt"
SRC_ROOT = REPO / "src" / "ayder_cli"

NEW_ROW = re.compile(r"^NEW unclassified argument at \S+: (\{.*\})$", re.M)

# A logger binding whose right-hand side proves it is one.
PRELUDE = "from ayder_cli.log import get_logger\nlogger = get_logger('core')\n"


def _live_py_count() -> int:
    return len(list(SRC_ROOT.rglob("*.py")))


def _run(*args, cwd: Path = REPO):
    """Run the gate; return (exit code, stdout+stderr). Never let a crash pass."""
    r = subprocess.run([sys.executable, str(GATE), *args],
                       capture_output=True, text=True, cwd=cwd)
    out = r.stdout + r.stderr
    assert "Traceback" not in out, f"gate crashed:\n{out}"
    return r.returncode, out


def _tree(tmp_path: Path, src: str, name: str = "sample.py") -> Path:
    target = tmp_path / "src" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent(src))
    return tmp_path / "src"


def _baseline(tmp_path: Path, rows, name: str = "baseline.txt") -> Path:
    path = tmp_path / name
    path.write_text("".join(
        (row if isinstance(row, str) else json.dumps(
            row, sort_keys=True, ensure_ascii=True, separators=(",", ":"))) + "\n"
        for row in rows))
    return path


def _scan(tmp_path: Path, src: str, rows=None, name: str = "sample.py"):
    """Run the gate over one synthetic module against `rows` (default: empty)."""
    root = _tree(tmp_path, src, name)
    base = _baseline(tmp_path, rows if rows is not None else ["# placeholder"])
    return _run("--root", str(root), "--baseline", str(base))


def _sites(tmp_path: Path, src: str, name: str = "sample.py") -> list[dict]:
    """Every live site the gate finds, read back off its own NEW report."""
    _code, out = _scan(tmp_path, src, name=name)
    return [json.loads(m) for m in NEW_ROW.findall(out)]


def _classified(tmp_path: Path, src: str, tag: str = "R-name",
                name: str = "sample.py"):
    """Run the gate with every live site classified as `tag`."""
    sites = _sites(tmp_path, src, name=name)
    rows = [{"site": s, "class": tag} for s in sites]
    root = tmp_path / "src"
    base = _baseline(tmp_path, rows, name="classified.txt")
    return _run("--root", str(root), "--baseline", str(base)) + (sites,)


# -- coverage: the gate may never report success over nothing -----------------

def test_missing_root_aborts():
    code, out = _run("--root", "src/does-not-exist", "--baseline", str(BASELINE))
    assert code == 2, out
    assert "source root does not exist" in out, out


def test_empty_root_aborts(tmp_path):
    (tmp_path / "empty").mkdir()
    code, out = _run("--root", str(tmp_path / "empty"),
                     "--baseline", str(BASELINE))
    assert code == 2, out
    assert "no Python files" in out, out


def test_missing_baseline_aborts(tmp_path):
    root = _tree(tmp_path, PRELUDE)
    code, out = _run("--root", str(root),
                     "--baseline", str(tmp_path / "absent.txt"))
    assert code == 2, out
    assert "baseline does not exist" in out, out


def test_blank_baseline_aborts(tmp_path):
    """A blank file is not "nothing to check": it is an unreviewed tree."""
    root = _tree(tmp_path, PRELUDE)
    blank = tmp_path / "blank.txt"
    blank.write_text("\n   \n\n")
    code, out = _run("--root", str(root), "--baseline", str(blank))
    assert code == 2, out
    assert "baseline is empty" in out, out


def test_default_root_and_baseline_resolve_from_the_script(tmp_path):
    """With no arguments and a cwd that has no `src/ayder_cli`, the gate must
    still scan the package against the committed baseline."""
    code, out = _run(cwd=tmp_path)
    assert code == 0, out
    assert f"scanned {_live_py_count()} file(s)" in out, out
    assert str(BASELINE) in out, out


def test_unparseable_file_is_a_finding(tmp_path):
    """A file that hides arguments behind a SyntaxError must fail the gate."""
    root = _tree(tmp_path, PRELUDE)
    (root / "broken.py").write_text("def broken(\n")
    code, out = _run("--root", str(root), "--baseline", str(BASELINE))
    assert code == 1, out
    assert "UNPARSEABLE" in out, out
    assert "broken.py" in out, out


def test_live_tree_is_clean_and_fully_reconciled():
    """Exit 0 alone proves nothing; the census totals prove the corpus was read
    and that the committed baseline covers exactly it."""
    code, out = _run()
    assert code == 0, out
    assert f"scanned {_live_py_count()} file(s)" in out, out
    assert "210 logging call site(s): 205 level-method + 5 emit_event" in out, out
    assert "137 call site(s) with >=1 interpolated argument" in out, out
    assert "276 interpolated argument(s) after static splat expansion" in out, out
    assert "(264 raw, 4 splat(s) -> 16 key(s))" in out, out
    assert "2 dynamic message row(s)" in out, out
    assert "278 baseline row(s)" in out, out
    assert "0 findings" in out, out


def test_committed_baseline_is_ordered_and_collision_free():
    """Deterministic order, by the canonical JSON of the identity alone."""
    lines = [ln for ln in BASELINE.read_text().splitlines() if ln.strip()]
    canon = [json.dumps(json.loads(ln)["site"], sort_keys=True,
                        ensure_ascii=True, separators=(",", ":"))
             for ln in lines]
    assert canon == sorted(canon), "baseline is not sorted by canonical site"
    assert len(set(canon)) == len(canon), "baseline identity collision"
    assert not any("line" in json.loads(ln)["site"] for ln in lines)


FROZEN_TALLY = {
    "R-name": 93, "R-id": 36, "R-count": 88, "R-status": 25, "R-class": 10,
    "R-path": 22, "content-deferred:5-04": 2, "dynamic-trusted": 1,
    "dynamic-deferred:5-04": 1,
}


@pytest.mark.parametrize("invocation", [
    pytest.param((), id="default-path"),
    pytest.param(("--root", str(SRC_ROOT), "--baseline", str(BASELINE)),
                 id="explicit-resolved-path"),
])
def test_gate_itself_enforces_the_frozen_tally(tmp_path, invocation):
    """Row-by-row diffing cannot see a silent retag: the identity is unchanged,
    so NEW/REMOVED/CHANGED all stay quiet. Only the composition catches it -
    and the gate, not a test, has to be the one that catches it."""
    original = BASELINE.read_bytes()
    rows = [json.loads(ln) for ln in original.decode().splitlines() if ln.strip()]
    victim = next(i for i, r in enumerate(rows) if r["class"] == "R-path")
    rows[victim]["class"] = "R-name"          # allowed tag, wrong provenance
    try:
        BASELINE.write_bytes("".join(
            json.dumps(r, sort_keys=True, ensure_ascii=True,
                       separators=(",", ":")) + "\n" for r in rows).encode())
        code, out = _run(*invocation)
        assert code == 1, out
        assert "CLASS-TALLY" in out, out
        assert "94 'R-name'" in out and "is 93" in out, out
        assert "21 'R-path'" in out and "is 22" in out, out
        # The retag is invisible to every row-level report - that is the point.
        assert "NEW unclassified" not in out, out
        assert "REMOVED" not in out, out
        assert "CHANGED" not in out, out
    finally:
        BASELINE.write_bytes(original)
    assert BASELINE.read_bytes() == original
    code, out = _run()
    assert code == 0, out


def test_caller_supplied_baselines_are_exempt_from_the_frozen_tally(tmp_path):
    """The tally is a fact about one committed file, not about the format."""
    code, out, _ = _classified(tmp_path, PRELUDE + "logger.info('a {}', x)\n")
    assert code == 0, out
    assert "CLASS-TALLY" not in out, out


def test_committed_baseline_classification_tally():
    """The seeded classes reconcile with the frozen census arithmetic:
    252 retained non-path + 22 paths + 2 deferred + 2 dynamic."""
    rows = [json.loads(ln) for ln in BASELINE.read_text().splitlines()
            if ln.strip()]
    tally: dict[str, int] = {}
    for row in rows:
        tally[row["class"]] = tally.get(row["class"], 0) + 1
    assert tally == FROZEN_TALLY, tally
    retained = sum(tally.get(t, 0) for t in
                   ("R-name", "R-id", "R-count", "R-status", "R-class"))
    assert retained == 252, tally
    assert sum(tally.values()) == 278, tally
    assert "ident" not in tally, "the forbidden generic tag is in the baseline"


# -- receiver resolution ------------------------------------------------------

def test_get_logger_import_binding_is_a_logger(tmp_path):
    sites = _sites(tmp_path, PRELUDE + "logger.info('a {}', x)\n")
    assert [s["expr"] for s in sites] == ["x"]


def test_import_alias_is_resolved(tmp_path):
    """The binding is a logger because of its right-hand side, not its name."""
    sites = _sites(tmp_path, """
        from ayder_cli.log import get_logger as make
        audit = make('core')
        audit.warning('a {}', x)
    """)
    assert [s["expr"] for s in sites] == ["x"]
    assert sites[0]["method"] == "warning"


def test_loguru_import_binding_is_resolved(tmp_path):
    sites = _sites(tmp_path, """
        from loguru import logger as lg
        lg.error('a {}', x)
    """)
    assert [s["expr"] for s in sites] == ["x"]


def test_module_alias_factory_is_resolved(tmp_path):
    sites = _sites(tmp_path, """
        from ayder_cli import log
        handle = log.get_logger('core')
        handle.debug('a {}', x)
    """)
    assert [s["expr"] for s in sites] == ["x"]


def test_local_factory_function_is_resolved(tmp_path):
    """A function that returns a logger makes its call sites loggers - and the
    function's own NAME is not one."""
    sites = _sites(tmp_path, """
        from ayder_cli.log import get_logger

        def _channel():
            return get_logger('core').bind(area='x')

        sink = _channel()
        sink.info('a {}', x)
    """)
    assert [s["expr"] for s in sites] == ["x"]


def test_class_attribute_and_instance_attribute_are_resolved(tmp_path):
    sites = _sites(tmp_path, """
        from ayder_cli.log import get_logger

        class Worker:
            shared = get_logger('core')

            def __init__(self):
                self.own = get_logger('core').bind(w=1)

            def run(self, a, b):
                self.shared.info('one {}', a)
                self.own.warning('two {}', b)
    """)
    assert sorted(s["expr"] for s in sites) == ["a", "b"]
    assert {s["qualname"] for s in sites} == {"Worker.run"}


def test_bind_opt_patch_chain_is_traversed(tmp_path):
    sites = _sites(tmp_path, PRELUDE + textwrap.dedent("""
        logger.bind(a=1).opt(lazy=True).patch(lambda r: r).error('x {}', v)
    """))
    assert [s["expr"] for s in sites] == ["v"]


def test_chain_keywords_are_not_argument_rows(tmp_path):
    """`.bind()` populates record['extra'], not record['message']."""
    sites = _sites(tmp_path, PRELUDE + "logger.bind(lib=name).info('flat')\n")
    assert sites == []


def test_stdlib_bridge_shaped_chain_is_a_dynamic_row(tmp_path):
    """The exact `_InterceptHandler.emit` shape: bind -> opt -> positional log."""
    sites = _sites(tmp_path, """
        from loguru import logger

        class Bridge:
            def emit(self, record, level, depth):
                logger.bind(channel='external', lib=record.name).opt(
                    depth=depth, exception=record.exc_info
                ).log(level, record.getMessage())
    """)
    assert len(sites) == 1, sites
    assert sites[0]["method"] == "log"
    assert sites[0]["message"] is None
    assert sites[0]["arg_index"] is None
    assert sites[0]["expr"] == "record.getMessage()"


def test_trusted_dynamic_trace_facade_shape(tmp_path):
    """The exact `emit_event` shape: the event name doubles as the message."""
    sites = _sites(tmp_path, """
        from ayder_cli.log import get_logger

        def emit_event(channel, evt, **fields):
            return get_logger(channel).bind(evt=evt, **fields).trace(evt)
    """)
    assert len(sites) == 1, sites
    assert sites[0]["method"] == "trace"
    assert sites[0]["message"] is None
    assert sites[0]["expr"] == "evt"


def test_non_logger_with_a_level_named_method_is_not_counted(tmp_path):
    """Resolution, not name-matching: `.error()` on a locally built object is
    somebody else's method, and counting it would be a false row."""
    code, out = _scan(tmp_path, """
        class Printer:
            def error(self, msg, *a):
                return msg

        printer = Printer()
        printer.error('failed {}', reason)
    """)
    assert code == 1, out            # only the placeholder-baseline complaint
    assert "NEW unclassified" not in out, out
    assert "UNRESOLVED-RECEIVER" not in out, out


def test_a_binding_named_logger_that_is_not_one_is_not_counted(tmp_path):
    """The inverse of name-matching: the name says logger, the value does not."""
    code, out = _scan(tmp_path, """
        class Printer:
            def info(self, msg, *a):
                return msg

        logger = Printer()
        logger.info('failed {}', reason)
    """)
    assert code == 1, out
    assert "NEW unclassified" not in out, out
    assert "UNRESOLVED-RECEIVER" not in out, out


def test_unresolvable_logger_like_chain_fails_closed(tmp_path):
    """A `.bind(...).opt(...)` chain over an unknown base could be a logger.
    Guessing "no" would silently drop its arguments from the census."""
    code, out = _scan(tmp_path, """
        def emit(thing, value):
            thing.bind(a=1).opt(lazy=True).error('x {}', value)
    """)
    assert code == 1, out
    assert "UNRESOLVED-RECEIVER" in out, out
    assert "logger-like chain" in out, out


def test_unresolvable_bare_receiver_fails_closed(tmp_path):
    code, out = _scan(tmp_path, """
        def emit(thing, value):
            thing.error('x {}', value)
    """)
    assert code == 1, out
    assert "UNRESOLVED-RECEIVER" in out, out


@pytest.mark.parametrize("level", sorted(
    {"trace", "debug", "info", "success", "warning", "error", "exception",
     "critical"}))
def test_every_level_method_is_covered(tmp_path, level):
    sites = _sites(tmp_path, PRELUDE + f"logger.{level}('a {{}}', x)\n")
    assert [s["method"] for s in sites] == [level]


# -- `.log(level, message, ...)` ---------------------------------------------

def test_log_positional_form_is_analyzed(tmp_path):
    sites = _sites(tmp_path, PRELUDE + "logger.log('INFO', 'a {}', x)\n")
    assert [s["expr"] for s in sites] == ["x"]
    assert sites[0]["message"] == "a {}"


def test_log_level_argument_is_not_an_interpolated_row(tmp_path):
    """`level` sits before the message; it is routing, not interpolation."""
    sites = _sites(tmp_path, PRELUDE + "logger.log(chosen, 'flat')\n")
    assert sites == []


@pytest.mark.parametrize("call", [
    pytest.param("logger.log(level='INFO', message='a {}')", id="both-keyword"),
    pytest.param("logger.log('a {}', level='INFO')", id="level-keyword"),
    pytest.param("logger.log('INFO', message='a {}')", id="message-keyword"),
])
def test_log_keyword_forms_fail_closed(tmp_path, call):
    """This version verifies the positional form only. Reading a keyword form
    as if it were positional would mis-locate the message."""
    code, out = _scan(tmp_path, PRELUDE + call + "\n")
    assert code == 1, out
    assert "UNSUPPORTED" in out, out
    assert ".log() keyword form" in out, out


def test_log_without_a_message_fails_closed(tmp_path):
    code, out = _scan(tmp_path, PRELUDE + "logger.log('INFO')\n")
    assert code == 1, out
    assert "no positional message argument" in out, out


def test_level_call_without_a_message_fails_closed(tmp_path):
    code, out = _scan(tmp_path, PRELUDE + "logger.info()\n")
    assert code == 1, out
    assert "no positional message argument" in out, out


# -- placeholder arity --------------------------------------------------------

@pytest.mark.parametrize("message,args", [
    pytest.param("'{} {}'", "a, b", id="automatic"),
    pytest.param("'{1} {0}'", "a, b", id="numbered"),
    pytest.param("'{0} {0}'", "a", id="repeated-numbered"),
    pytest.param("'{} {}'", "a, a", id="repeated-argument"),
    pytest.param("'{!r}'", "a", id="conversion"),
    pytest.param("'{:>10}'", "a", id="format-spec"),
    pytest.param("'{:{}}'", "a, b", id="nested-spec-field"),
    pytest.param("'{:{width}.{prec}f}'", "a, width=w, prec=p",
                 id="nested-named-spec-fields"),
    pytest.param("'{user.name}'", "user=u", id="attribute-base-key"),
    pytest.param("'{0[1]}'", "pair", id="subscript-base-key"),
    pytest.param("'{{literal}} {}'", "a", id="escaped-braces"),
    pytest.param("'{a} and {}'", "b, a=x", id="named-plus-automatic"),
])
def test_matching_arity_is_accepted(tmp_path, message, args):
    code, out = _scan(tmp_path, PRELUDE + f"logger.info({message}, {args})\n")
    assert "ARITY" not in out, out
    assert "BAD-FORMAT" not in out, out
    assert code == 1, out        # NEW rows only - the baseline is a placeholder


@pytest.mark.parametrize("message,args,verb", [
    pytest.param("'{} {}'", "a", "missing", id="missing-automatic"),
    pytest.param("'{}'", "a, b", "surplus", id="surplus-automatic"),
    pytest.param("'{2}'", "a, b", "missing", id="missing-numbered"),
    pytest.param("'{0}'", "a, b", "surplus", id="surplus-numbered"),
    pytest.param("'{:{}}'", "a", "missing", id="missing-nested-spec-field"),
    pytest.param("'flat'", "a", "surplus", id="surplus-no-placeholder"),
])
def test_arity_mismatch_is_a_finding(tmp_path, message, args, verb):
    code, out = _scan(tmp_path, PRELUDE + f"logger.info({message}, {args})\n")
    assert code == 1, out
    assert "ARITY" in out, out
    assert verb in out, out


def test_named_field_without_an_argument_is_a_finding(tmp_path):
    code, out = _scan(tmp_path, PRELUDE + "logger.info('{who} left', b)\n")
    assert code == 1, out
    assert "named field(s) with no argument: ['who']" in out, out


def test_named_arguments_that_match_their_fields_are_accepted(tmp_path):
    """The non-vacuous half of the surplus rule: an exactly-matching set of
    named arguments must stay clean, so the rule cannot be satisfied by simply
    rejecting every keyword."""
    src = PRELUDE + "logger.info('{who} left at {when}', who=name, when=t)\n"
    code, out = _scan(tmp_path, src)
    assert "ARITY" not in out, out
    code, out, sites = _classified(tmp_path, src)
    assert code == 0, out
    assert sorted(s["arg_index"] for s in sites) == ["kw:when", "kw:who"], sites


def test_surplus_explicit_keyword_is_a_finding(tmp_path):
    """Loguru captures an unused kwarg into record['extra'], where it reaches
    the trace sink without ever appearing in the message a reviewer reads."""
    code, out = _scan(tmp_path,
                      PRELUDE + "logger.info('{who}', who=name, secret=secret)\n")
    assert code == 1, out
    assert "surplus keyword argument(s) with no named field: ['secret']" in out, out


def test_surplus_splat_key_is_a_finding(tmp_path):
    """Statically expanded `**` keys are held to the same rule as explicit
    ones: expansion is what makes them checkable."""
    code, out = _scan(tmp_path, PRELUDE + textwrap.dedent("""
        def go(who, extra):
            fields = {'who': who, 'leaked': extra}
            logger.info('{who}', **fields)
    """))
    assert code == 1, out
    assert "surplus keyword argument(s) with no named field: ['leaked']" in out, out


def test_surplus_keyword_is_not_suppressible_by_baselining(tmp_path):
    """The row being reviewed says the VALUE is acceptable; it says nothing
    about the keyword having no field to land in."""
    src = PRELUDE + "logger.info('{who}', who=name, secret=secret)\n"
    code, out, _ = _classified(tmp_path, src)
    assert code == 1, out
    assert "NEW unclassified" not in out, out
    assert "surplus keyword argument(s)" in out, out


@pytest.mark.parametrize("message", [
    pytest.param("'{!s}'", id="str-conversion"),
    pytest.param("'{!r}'", id="repr-conversion"),
    pytest.param("'{!a}'", id="ascii-conversion"),
])
def test_valid_conversions_are_accepted(tmp_path, message):
    code, out = _scan(tmp_path, PRELUDE + f"logger.info({message}, a)\n")
    assert "BAD-FORMAT" not in out, out
    assert "ARITY" not in out, out


@pytest.mark.parametrize("message,args", [
    pytest.param("'{!z}'", "a", id="top-level"),
    pytest.param("'{:{width!z}}'", "a, width=w", id="nested-in-spec"),
])
def test_invalid_conversion_is_a_finding(tmp_path, message, args):
    """`str.format` raises "Unknown conversion specifier" at runtime, but
    `Formatter.parse` hands the flag back without complaint - and hands nested
    specs back verbatim, so the check has to recurse."""
    code, out = _scan(tmp_path, PRELUDE + f"logger.info({message}, {args})\n")
    assert code == 1, out
    assert "BAD-FORMAT" in out, out
    assert "unknown conversion specifier(s) ['z']" in out, out


@pytest.mark.parametrize("message", [
    pytest.param("'{} {0}'", id="auto-then-manual"),
    pytest.param("'{0} {}'", id="manual-then-auto"),
])
def test_illegal_field_numbering_mix_is_a_finding(tmp_path, message):
    """Python raises on this at runtime; the gate must not accept it either."""
    code, out = _scan(tmp_path, PRELUDE + f"logger.info({message}, a, b)\n")
    assert code == 1, out
    assert "BAD-FORMAT" in out, out
    assert "automatic and manual field numbering" in out, out


@pytest.mark.parametrize("message", [
    pytest.param("'a { b'", id="unmatched-open"),
    pytest.param("'a } b'", id="unmatched-close"),
])
def test_malformed_format_string_is_a_finding(tmp_path, message):
    code, out = _scan(tmp_path, PRELUDE + f"logger.info({message}, a)\n")
    assert code == 1, out
    assert "BAD-FORMAT" in out, out
    assert "malformed format string" in out, out


def test_star_args_is_unverifiable_until_it_is_classified(tmp_path):
    """`*args` hides the argument count. The row still exists: classifying it
    is the reviewer's explicit acceptance of the gap, and nothing else is."""
    src = PRELUDE + "logger.info('a {} {}', *values)\n"
    code, out = _scan(tmp_path, src)
    assert code == 1, out
    assert "UNVERIFIABLE-ARITY" in out, out
    star = [s for s in _sites(tmp_path, src) if s["arg_index"] == "star:0"]
    assert star and star[0]["expr"] == "*values", star

    code, out, _sites_seen = _classified(tmp_path, src, tag="R-count")
    assert code == 0, out
    assert "UNVERIFIABLE-ARITY" not in out, out


# -- message shapes -----------------------------------------------------------

def test_percent_placeholder_is_a_legacy_format_violation(tmp_path):
    """Its own category, and reported even with no trailing arguments - the
    single-argument miss that step 5-01 documented as a known hole."""
    code, out = _scan(tmp_path, PRELUDE + "logger.info('loaded %s rows', n)\n")
    assert code == 1, out
    assert "LEGACY-FORMAT" in out, out

    code, out = _scan(tmp_path, PRELUDE + "logger.info('100% done')\n")
    assert code == 1, out
    assert "LEGACY-FORMAT" in out, out


def test_escaped_percent_is_not_a_legacy_violation(tmp_path):
    code, out = _scan(tmp_path, PRELUDE + "logger.info('{:.0f}%% done', pct)\n")
    assert "LEGACY-FORMAT" not in out, out


@pytest.mark.parametrize("message,expr", [
    pytest.param("f'run {rid} done'", "f'run {rid} done'", id="fstring"),
    pytest.param("'run ' + rid", "'run ' + rid", id="binop"),
])
def test_dynamic_messages_are_their_own_rows(tmp_path, message, expr):
    sites = _sites(tmp_path, PRELUDE + f"logger.info({message})\n")
    assert len(sites) == 1, sites
    assert sites[0]["message"] is None
    assert sites[0]["arg_index"] is None
    assert sites[0]["expr"] == expr


def test_adjacent_string_literals_are_one_literal_message(tmp_path):
    """The parser folds them; a folded message is not a dynamic message."""
    sites = _sites(tmp_path, PRELUDE + "logger.info('a ' 'b {}', v)\n")
    assert [s["message"] for s in sites] == ["a b {}"]
    assert [s["arg_index"] for s in sites] == ["pos:0"]


def test_constant_positional_argument_is_a_row(tmp_path):
    """The hardcoded-secret shape. A literal is the ONE argument whose value a
    reviewer can read off the diff, so it is the last thing that may
    auto-pass: it is enumerated, and unclassified until someone says what it
    is."""
    src = PRELUDE + "logger.info('credential={}', 'sk-hardcoded-secret')\n"
    code, out = _scan(tmp_path, src)
    assert code == 1, out
    assert "NEW unclassified" in out, out
    assert "ARITY" not in out, out

    sites = _sites(tmp_path, src)
    assert [s["expr"] for s in sites] == ["'sk-hardcoded-secret'"], sites
    assert [s["arg_index"] for s in sites] == ["pos:0"], sites

    code, out, _ = _classified(tmp_path, src, tag="R-status")
    assert code == 0, out


def test_constant_keyword_argument_is_a_row(tmp_path):
    src = PRELUDE + "logger.info('token={token}', token='sk-hardcoded')\n"
    code, out = _scan(tmp_path, src)
    assert code == 1, out
    assert "NEW unclassified" in out, out

    sites = _sites(tmp_path, src)
    assert [s["arg_index"] for s in sites] == ["kw:token"], sites
    assert [s["expr"] for s in sites] == ["'sk-hardcoded'"], sites

    code, out, _ = _classified(tmp_path, src, tag="R-status")
    assert code == 0, out


def test_constant_arguments_still_count_towards_arity(tmp_path):
    """Being a row and being an argument are different questions."""
    code, out = _scan(tmp_path, PRELUDE + "logger.info('a {} {}', 'lit', v)\n")
    assert "ARITY" not in out, out
    sites = _sites(tmp_path, PRELUDE + "logger.info('a {} {}', 'lit', v)\n")
    assert sorted(s["expr"] for s in sites) == ["'lit'", "v"], sites


def test_constant_expressions_are_deterministic(tmp_path):
    """`ast.unparse` normalises the literal, so re-formatting the source does
    not invalidate the classification."""
    first = _sites(tmp_path, PRELUDE + 'logger.info("v={}", "lit")\n')
    second = _sites(tmp_path, PRELUDE + "logger.info('v={}', 'lit')\n")
    assert first == second, (first, second)


# -- `**` splat expansion -----------------------------------------------------

def test_dict_literal_splat_expands(tmp_path):
    sites = _sites(tmp_path, """
        from ayder_cli.log import emit_event
        emit_event('core', 'evt', **{'a': one, 'b': two})
    """)
    assert sorted(s["arg_index"].rsplit(":", 1)[-1] for s in sites) == ["a", "b"]


def test_named_dict_splat_expands_including_conditional_keys(tmp_path):
    """The live `fields[...] = ...` shape: a literal plus constant subscript
    additions. Missing the conditional key would under-count the census."""
    sites = _sites(tmp_path, """
        from ayder_cli.log import emit_event

        def go(self, before, after):
            fields = {'before': before, 'after': after}
            if after is not None:
                fields['run_id'] = after
            emit_event('core', 'evt', **fields)
    """)
    keys = sorted(s["arg_index"].rsplit(":", 1)[-1] for s in sites)
    assert keys == ["after", "before", "run_id"], sites
    assert all(s["expr"].startswith("fields[") for s in sites), sites


def test_simple_method_splat_expands(tmp_path):
    """The live `**self._correlation()` shape."""
    sites = _sites(tmp_path, """
        from ayder_cli.log import emit_event

        class Loop:
            def _correlation(self):
                envelope = {'session_id': self.sid}
                if self.rid is not None:
                    envelope['run_id'] = self.rid
                return envelope

            def go(self):
                emit_event('core', 'evt', n=self.n, **self._correlation())
    """)
    keys = sorted(s["arg_index"].rsplit(":", 1)[-1] for s in sites)
    assert keys == ["n", "run_id", "session_id"], sites


@pytest.mark.parametrize("body,reason", [
    pytest.param("emit_event('core', 'evt', **kwargs)",
                 "not a statically readable dict literal", id="signature-kwargs"),
    pytest.param("fields = {key: 1}\n    emit_event('core', 'evt', **fields)",
                 "not a statically readable dict literal", id="dynamic-key"),
    pytest.param("fields = {'a': 1}\n    fields.update(other)\n"
                 "    emit_event('core', 'evt', **fields)",
                 "not a statically readable dict literal", id="mutated-dict"),
    pytest.param("emit_event('core', 'evt', **build())",
                 "cannot be expanded", id="opaque-call"),
])
def test_unresolvable_splat_fails_closed(tmp_path, body, reason):
    code, out = _scan(tmp_path, "from ayder_cli.log import emit_event\n\n"
                                "def go(key, other, **kwargs):\n    " + body + "\n")
    assert code == 1, out
    assert "UNSUPPORTED" in out, out
    assert reason in out, out


def test_dict_literal_splat_with_a_dynamic_key_fails_closed(tmp_path):
    code, out = _scan(tmp_path, """
        from ayder_cli.log import emit_event
        emit_event('core', 'evt', **{key: 1})
    """)
    assert code == 1, out
    assert "dict literal with a dynamic key" in out, out


def test_emit_event_schema_selectors_are_not_rows_but_fields_are(tmp_path):
    """`channel` and `evt` select the frozen C11 schema; everything after them
    is payload. A CONSTANT field is payload too - that is exactly where a
    hardcoded secret would sit unreviewed."""
    src = ("from ayder_cli.log import emit_event\n"
           "emit_event('core', 'evt', run_id=rid, ok=True, note='fixed-text')\n")
    sites = _sites(tmp_path, src)
    assert sorted(s["arg_index"] for s in sites) == [
        "kw:note", "kw:ok", "kw:run_id"], sites
    assert {s["method"] for s in sites} == {"emit_event"}
    assert "'core'" not in [s["expr"] for s in sites], sites
    assert "'evt'" not in [s["expr"] for s in sites], sites

    code, out = _scan(tmp_path, src)
    assert code == 1, out
    assert "NEW unclassified" in out, out
    code, out, _ = _classified(tmp_path, src, tag="R-status")
    assert code == 0, out


def test_emit_event_computed_schema_selector_is_a_row(tmp_path):
    """The exemption is for constants, not for the position: a computed
    channel or event name is a runtime value like any other."""
    sites = _sites(tmp_path, """
        from ayder_cli.log import emit_event

        def go(channel, rid):
            emit_event(channel, 'evt', run_id=rid)
    """)
    assert sorted(s["arg_index"] for s in sites) == ["kw:run_id", "pos:0"], sites


def test_emit_event_exemption_stops_after_the_two_schema_positions(tmp_path):
    """The exemption is bounded by position as well as by constness: a third
    positional is not part of the schema, constant or not."""
    sites = _sites(tmp_path, """
        from ayder_cli.log import emit_event
        emit_event('core', 'evt', 'stray-constant')
    """)
    assert [s["arg_index"] for s in sites] == ["pos:2"], sites
    assert [s["expr"] for s in sites] == ["'stray-constant'"], sites


# -- baseline integrity -------------------------------------------------------

def _one_site(tmp_path) -> dict:
    return _sites(tmp_path, PRELUDE + "logger.info('a {}', x)\n")[0]


def test_classified_tree_passes(tmp_path):
    code, out, sites = _classified(tmp_path, PRELUDE + "logger.info('a {}', x)\n")
    assert code == 0, out
    assert "0 findings" in out, out
    assert len(sites) == 1


@pytest.mark.parametrize("row,marker", [
    pytest.param("{not json", "MALFORMED", id="not-json"),
    pytest.param('{"site": {}}', "MALFORMED", id="missing-class-key"),
    pytest.param('{"site": {}, "class": "R-name", "extra": 1}', "MALFORMED",
                 id="surplus-key"),
    pytest.param('["site", "class"]', "MALFORMED", id="not-an-object"),
])
def test_malformed_baseline_rows_fail_closed(tmp_path, row, marker):
    code, out = _scan(tmp_path, PRELUDE, rows=[row])
    assert code == 1, out
    assert marker in out, out


def test_baseline_site_must_carry_exactly_the_identity_keys(tmp_path):
    site = _one_site(tmp_path)
    short = dict(site)
    short.pop("expr")
    code, out = _scan(tmp_path, PRELUDE + "logger.info('a {}', x)\n",
                      rows=[{"site": short, "class": "R-name"}])
    assert code == 1, out
    assert "site must carry exactly" in out, out

    wide = dict(site)
    wide["line"] = 3
    code, out = _scan(tmp_path, PRELUDE + "logger.info('a {}', x)\n",
                      rows=[{"site": wide, "class": "R-name"}])
    assert code == 1, out
    assert "site must carry exactly" in out, out


@pytest.mark.parametrize("field,value,marker", [
    pytest.param("path", 7, "must be strings", id="path-not-string"),
    pytest.param("qualname", None, "must be strings", id="qualname-null"),
    pytest.param("method", [], "must be strings", id="method-list"),
    pytest.param("expr", 1.5, "must be strings", id="expr-float"),
    pytest.param("message", 3, "message must be a string or null",
                 id="message-int"),
    pytest.param("arg_index", 0, "arg_index must be a string or null",
                 id="arg-index-int"),
])
def test_baseline_field_types_fail_closed(tmp_path, field, value, marker):
    site = dict(_one_site(tmp_path))
    site[field] = value
    code, out = _scan(tmp_path, PRELUDE + "logger.info('a {}', x)\n",
                      rows=[{"site": site, "class": "R-name"}])
    assert code == 1, out
    assert marker in out, out


@pytest.mark.parametrize("tag", ["ident", "", "R-Name", "content-deferred"])
def test_unknown_classification_tag_fails_closed(tmp_path, tag):
    """`ident` above all: a generic tag would make the review meaningless."""
    site = _one_site(tmp_path)
    code, out = _scan(tmp_path, PRELUDE + "logger.info('a {}', x)\n",
                      rows=[{"site": site, "class": tag}])
    assert code == 1, out
    assert "UNKNOWN-CLASS" in out, out


def test_duplicate_baseline_identity_fails_closed(tmp_path):
    site = _one_site(tmp_path)
    row = {"site": site, "class": "R-name"}
    code, out = _scan(tmp_path, PRELUDE + "logger.info('a {}', x)\n",
                      rows=[row, row])
    assert code == 1, out
    assert "DUPLICATE baseline row" in out, out


def test_one_identity_under_two_classes_reports_reclassified(tmp_path):
    """Classification lives outside the identity, so a changed tag reads as a
    reclassification rather than as an unrelated NEW/REMOVED pair."""
    site = _one_site(tmp_path)
    code, out = _scan(tmp_path, PRELUDE + "logger.info('a {}', x)\n",
                      rows=[{"site": site, "class": "R-name"},
                            {"site": site, "class": "R-count"}])
    assert code == 1, out
    assert "RECLASSIFIED" in out, out
    assert "'R-name'" in out and "'R-count'" in out, out


@pytest.mark.parametrize("message", [
    pytest.param("a :: b :: c {}", id="double-colon-separator"),
    pytest.param("line one\\nline two {}", id="embedded-newline"),
    pytest.param("caf\\u00e9 na\\u00efve \\u2713 {}", id="unicode"),
    pytest.param('quoted \\"{}\\" and \\\\ backslash', id="quotes-and-backslash"),
])
def test_identity_round_trips_hostile_messages(tmp_path, message):
    """`::` would break a delimiter-joined identity; newlines would break a
    line-oriented one; JSON survives all three."""
    src = PRELUDE + f'logger.info("{message}", x)\n'
    code, out, sites = _classified(tmp_path, src)
    assert code == 0, out
    assert len(sites) == 1, sites
    assert "\n" not in json.dumps(sites[0])


def test_new_row_is_reported_with_an_actionable_location(tmp_path):
    code, out = _scan(tmp_path, PRELUDE + "logger.info('a {}', x)\n")
    assert code == 1, out
    assert "NEW unclassified argument at sample.py:3:" in out, out


def test_stale_baseline_row_is_reported_as_removed(tmp_path):
    site = _one_site(tmp_path)
    code, out = _scan(tmp_path, PRELUDE + "logger.info('flat')\n",
                      rows=[{"site": site, "class": "R-name"}])
    assert code == 1, out
    assert "REMOVED stale baseline row (R-name)" in out, out
    assert "NEW unclassified" not in out, out


def test_edited_message_at_a_live_slot_is_reported_as_changed(tmp_path):
    """One edit must read as one finding, not as an unrelated NEW + REMOVED."""
    site = dict(_one_site(tmp_path))
    site["message"] = "an older wording {}"
    code, out = _scan(tmp_path, PRELUDE + "logger.info('a {}', x)\n",
                      rows=[{"site": site, "class": "R-name"}])
    assert code == 1, out
    assert "CHANGED at sample.py:3" in out, out
    assert "NEW unclassified" not in out, out
    assert "REMOVED" not in out, out
    assert "FAIL - 1 finding(s)" in out, out


def test_edited_expression_at_a_live_slot_is_reported_as_changed(tmp_path):
    site = dict(_one_site(tmp_path))
    site["expr"] = "old_expression"
    code, out = _scan(tmp_path, PRELUDE + "logger.info('a {}', x)\n",
                      rows=[{"site": site, "class": "R-name"}])
    assert code == 1, out
    assert "CHANGED at" in out, out


def test_two_live_arguments_sharing_an_identity_fail_closed(tmp_path):
    """No baseline row could name either one, so the gate refuses to guess."""
    code, out = _scan(tmp_path, PRELUDE + textwrap.dedent("""
        def go(x):
            logger.info('a {}', x)
            logger.info('a {}', x)
    """))
    assert code == 1, out
    assert "AMBIGUOUS" in out, out


def test_same_expression_at_different_messages_is_two_identities(tmp_path):
    """The message is part of the identity: the same value under a different
    wording is a different disclosure."""
    sites = _sites(tmp_path, PRELUDE + textwrap.dedent("""
        def go(x):
            logger.info('one {}', x)
            logger.info('two {}', x)
    """))
    assert len(sites) == 2, sites
    assert {s["message"] for s in sites} == {"one {}", "two {}"}


def test_recursive_discovery(tmp_path):
    """rglob, not glob: an argument three directories down must be found."""
    code, out = _scan(tmp_path, PRELUDE + "logger.info('a {}', x)\n",
                      name="a/b/c/deep.py")
    assert code == 1, out
    assert "a/b/c/deep.py" in out, out


def test_moving_a_call_within_a_file_is_free(tmp_path):
    """Identity carries no line number: adding a comment above a call must not
    make its reviewed classification stale."""
    src = PRELUDE + "logger.info('a {}', x)\n"
    code, out, _ = _classified(tmp_path, src)
    assert code == 0, out

    moved = PRELUDE + "\n# a new comment\n\nlogger.info('a {}', x)\n"
    _tree(tmp_path, moved)
    code, out = _run("--root", str(tmp_path / "src"),
                     "--baseline", str(tmp_path / "classified.txt"))
    assert code == 0, out
