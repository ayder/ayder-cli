#!/usr/bin/env python3
"""Gate: only log.py and logging_config.py may touch a logging library.

Every other module reaches logging through the CONTRACTS C8 facade. Both
`logging` and `loguru` are rejected, in both import forms, and by dotted ROOT
PREFIX - `import logging.handlers` and `from loguru._logger import Logger` are
the same violation as `import logging`, and an exact-name match would wave both
straight through.

The exemption is by exact ROOT-RELATIVE path, not by file name: `log.py` and
`logging_config.py` directly under the scanned root are allowed, while a
`tools/log.py` is not. A name-only allowlist lets any subpackage opt itself out
by choosing the right filename.

Coverage is fail-closed: a missing root, an empty root and an unparseable file
are each a nonzero exit, and every run prints the number of files it scanned so
that a silent pass cannot be mistaken for coverage.

A relative `from .logging import x` is also reported. No such module exists in
the package, and erring toward a false positive is the correct direction for a
gate whose only failure mode of consequence is a false negative.
"""
from __future__ import annotations

import argparse
import ast
import pathlib
import sys

# Exact root-relative paths, POSIX-normalised. NOT bare file names.
ALLOWED = {"log.py", "logging_config.py"}
BANNED_ROOTS = {"logging", "loguru"}

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


def _banned(dotted: str) -> bool:
    """Match by dotted root: `logging.handlers` is `logging`."""
    return dotted.split(".")[0] in BANNED_ROOTS


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
    exempt = 0
    for p in py_files:
        try:
            tree = ast.parse(p.read_text(), filename=str(p))
        except SyntaxError as e:
            # Never skip silently - an unparseable file is a hole in coverage,
            # and the import it hides is exactly what this gate exists to find.
            problems.append(f"UNPARSEABLE {_display(p)}: {e}")
            continue
        scanned += 1
        # Parse first, exempt second: the allowlist excuses a file from the
        # import RULE, never from being read. An unparseable log.py is still a
        # coverage hole and must still fail.
        if p.relative_to(root).as_posix() in ALLOWED:
            exempt += 1
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if _banned(a.name):
                        hits.append(f"{_display(p)}:{node.lineno} import {a.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module is not None and _banned(node.module):
                    hits.append(
                        f"{_display(p)}:{node.lineno} from {node.module} import ...")

    for h in hits:
        print(h)
    for x in problems:
        print(f"  {x}")
    print(f"scanned {scanned} file(s) of {len(py_files)} discovered under {root} "
          f"({exempt} exempt from the import rule)")
    print(f"{len(hits)} disallowed logging import(s)")
    if problems:
        print(f"FAIL - {len(problems)} unparseable file(s)")
        return 1
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
