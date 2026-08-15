#!/usr/bin/env python3
"""Gate: no %-style logging calls. Loguru does not interpolate them.

Loguru formats with `str.format`, so a `%`-style template reaches the sink
uninterpolated and its arguments are dropped without a word. This gate walks
every module under the source root and reports every logging call whose first
argument is a literal string carrying a `%` conversion while further positional
arguments follow.

Coverage is fail-closed: a missing root, an empty root and an unparseable file
are each a nonzero exit, and every run prints the number of files it scanned so
that a silent pass cannot be mistaken for coverage.

Known limitations - assigned to step 5-03, and deliberately NOT pinned by any
test, so that strengthening the rule later is never blocked by a regression
assertion:

  * single-argument %-strings. `logger.info("100% done")` carries no trailing
    arguments, so the arity check that makes this rule precise also hides it.
  * `logger.log(level, "...", arg)`. The message sits at `args[1]`, not
    `args[0]`, so `.log` calls are invisible here.
  * non-logger receivers. Any object exposing a same-named method matches;
    the receiver is not checked against the CONTRACTS C8 bindings.
  * dynamic messages. Anything that is not a literal `str` constant - an
    f-string, a name, a concatenation, a `.format` chain - is skipped.
"""
from __future__ import annotations

import argparse
import ast
import pathlib
import re
import sys

LEVELS = {"trace", "debug", "info", "success", "warning", "error",
          "exception", "critical"}
# Covers %s %d %r %f, mapping keys %(name)s, and %c
PCT = re.compile(r"%(?:\([^)]*\))?[-#0 +]*[\d.*]*[hlL]?[scdrfgeixXou]")

# Resolved from this file, never from the caller's cwd: scripts/<this>.py ->
# repo root. A cwd-relative root is how a gate "passes" over an empty tree.
REPO = pathlib.Path(__file__).resolve().parent.parent
SRC_ROOT = REPO / "src" / "ayder_cli"


def _display(p: pathlib.Path) -> str:
    """Repo-relative when the file lives in the repo, absolute otherwise."""
    try:
        return str(p.resolve().relative_to(REPO))
    except ValueError:
        return str(p)


def _is_percent_log(node: ast.AST) -> bool:
    return (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in LEVELS
            and len(node.args) > 1
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and bool(PCT.search(node.args[0].value)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(SRC_ROOT),
                    help="directory to scan (default: the package source root)")
    args = ap.parse_args()

    root = pathlib.Path(args.root)
    if not root.is_dir():
        print(f"ABORT: source root does not exist: {root}", file=sys.stderr)
        return 2
    py_files = sorted(root.rglob("*.py"))
    if not py_files:
        print(f"ABORT: no Python files under {root}", file=sys.stderr)
        return 2

    hits: list[str] = []
    problems: list[str] = []
    scanned = 0
    for p in py_files:
        try:
            tree = ast.parse(p.read_text(), filename=str(p))
        except SyntaxError as e:
            # Never skip silently - an unparseable file is a hole in coverage,
            # and the %-call it hides is exactly what this gate exists to find.
            problems.append(f"UNPARSEABLE {_display(p)}: {e}")
            continue
        scanned += 1
        for node in ast.walk(tree):
            if _is_percent_log(node):
                hits.append(f"{_display(p)}:{node.lineno}")

    for h in hits:
        print(h)
    for x in problems:
        print(f"  {x}")
    print(f"scanned {scanned} file(s) of {len(py_files)} discovered under {root}")
    print(f"{len(hits)} %-style logging call(s)")
    if problems:
        print(f"FAIL - {len(problems)} unparseable file(s)")
        return 1
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
